from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .db import get_db
from .managed_service_models import ManagedServiceClient
from .managed_service_token_security import create_managed_service_token
from .models import Application
from .schemas import ServiceTokenResponse
from .security import create_service_token
from .security_service import record_audit
from .service_client_schemas import ManagedServiceTokenRequest
from .service_clients import ServiceClientAuthError, authenticate_managed_service_client


router = APIRouter(tags=["service-authentication"])


@router.post("/v1/auth/service-token", response_model=ServiceTokenResponse)
def issue_service_token(
    payload: ManagedServiceTokenRequest,
    request: Request,
    db: Session = Depends(get_db),
    config: Settings = Depends(get_settings),
) -> ServiceTokenResponse:
    managed = db.scalar(
        select(ManagedServiceClient).where(ManagedServiceClient.client_id == payload.client_id)
    )
    if managed is not None:
        try:
            credential, normalized_scope = authenticate_managed_service_client(
                db,
                client=managed,
                client_secret=payload.client_secret,
                audience=payload.audience,
                scope=payload.scope,
            )
        except ServiceClientAuthError as exc:
            record_audit(
                db,
                event_type="service_token_denied",
                success=False,
                client_id=payload.client_id,
                request=request,
                details={"audience": payload.audience, "scope": payload.scope, "reason": exc.detail},
            )
            db.commit()
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None

        token = create_managed_service_token(
            settings=config,
            client_id=managed.client_id,
            credential_id=credential.id,
            audience=payload.audience,
            scope=normalized_scope,
        )
        record_audit(
            db,
            event_type="service_token_issued",
            client_id=managed.client_id,
            request=request,
            details={
                "audience": payload.audience,
                "scope": normalized_scope,
                "credential_id": str(credential.id),
                "secret_prefix": credential.secret_prefix,
            },
        )
        db.commit()
        return ServiceTokenResponse(
            access_token=token,
            expires_in=config.service_token_minutes * 60,
            scope=normalized_scope,
        )

    if not config.allow_legacy_service_secrets:
        record_audit(
            db,
            event_type="legacy_service_token_denied",
            success=False,
            client_id=payload.client_id,
            request=request,
            details={"reason": "legacy service secrets disabled"},
        )
        db.commit()
        raise HTTPException(status_code=401, detail="managed service credentials required")

    # Compatibility bridge for explicitly enabled legacy integrations. New platform
    # clients must be stored in managed_service_clients; these legacy tokens
    # intentionally do not carry the service_auth=managed claim required by
    # new privileged platform APIs.
    application = db.scalar(
        select(Application).where(
            Application.client_id == payload.client_id,
            Application.is_active.is_(True),
        )
    )
    if application is None:
        record_audit(
            db,
            event_type="service_token_denied",
            success=False,
            client_id=payload.client_id,
            request=request,
            details={"reason": "unknown service client"},
        )
        db.commit()
        raise HTTPException(status_code=401, detail="invalid service credentials")

    expected = config.service_client_secrets.get(payload.client_id)
    if expected is None or not hmac.compare_digest(expected, payload.client_secret):
        record_audit(
            db,
            event_type="legacy_service_token_denied",
            success=False,
            client_id=payload.client_id,
            request=request,
            details={"audience": payload.audience, "scope": payload.scope},
        )
        db.commit()
        raise HTTPException(status_code=401, detail="invalid service credentials")

    token = create_service_token(
        settings=config,
        client_id=payload.client_id,
        audience=payload.audience,
        scope=payload.scope,
    )
    record_audit(
        db,
        event_type="legacy_service_token_issued",
        client_id=payload.client_id,
        request=request,
        details={"audience": payload.audience, "scope": payload.scope},
    )
    db.commit()
    return ServiceTokenResponse(
        access_token=token,
        expires_in=config.service_token_minutes * 60,
        scope=payload.scope,
    )
