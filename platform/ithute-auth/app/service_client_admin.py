from __future__ import annotations

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .account import AuthContext
from .admin import require_admin
from .db import get_db
from .managed_service_models import ManagedServiceClient, ManagedServiceCredential
from .models import Application, AuditEvent, utcnow
from .security_service import record_audit
from .service_client_schemas import (
    AdminServiceClientAuditResponse,
    AdminServiceClientCreateRequest,
    AdminServiceClientCreateResponse,
    AdminServiceClientResponse,
    AdminServiceClientUpdateRequest,
    AdminServiceCredentialResponse,
    AdminServiceSecretResponse,
    AdminServiceSecretRotateRequest,
)
from .service_clients import create_service_credential, decode_capabilities, encode_capabilities


router = APIRouter(prefix="/v1/admin/service-clients", tags=["platform-service-clients"])


def _future_expiry(value: datetime | None, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise HTTPException(status_code=400, detail=f"{field_name} must include a timezone")
    if value <= utcnow():
        raise HTTPException(status_code=400, detail=f"{field_name} must be in the future")
    return value


def _credential_response(row: ManagedServiceCredential) -> AdminServiceCredentialResponse:
    return AdminServiceCredentialResponse(
        id=str(row.id),
        secret_prefix=row.secret_prefix,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        last_used_at=row.last_used_at,
        created_at=row.created_at,
    )


def _client_response(db: Session, row: ManagedServiceClient) -> AdminServiceClientResponse:
    credentials = db.scalars(
        select(ManagedServiceCredential)
        .where(ManagedServiceCredential.service_client_id == row.id)
        .order_by(ManagedServiceCredential.created_at.desc())
    ).all()
    return AdminServiceClientResponse(
        client_id=row.client_id,
        name=row.name,
        description=row.description,
        allowed_audiences=list(decode_capabilities(row.allowed_audiences_json)),
        allowed_scopes=list(decode_capabilities(row.allowed_scopes_json)),
        is_active=row.is_active,
        expires_at=row.expires_at,
        last_used_at=row.last_used_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        credentials=[_credential_response(item) for item in credentials],
    )


def _find_client(db: Session, client_id: str) -> ManagedServiceClient:
    row = db.scalar(select(ManagedServiceClient).where(ManagedServiceClient.client_id == client_id))
    if row is None:
        raise HTTPException(status_code=404, detail="service client not found")
    return row


@router.get("", response_model=list[AdminServiceClientResponse])
def list_service_clients(
    q: str | None = Query(default=None, max_length=160),
    _: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AdminServiceClientResponse]:
    statement = select(ManagedServiceClient).order_by(ManagedServiceClient.name.asc())
    if q and q.strip():
        term = f"%{q.strip()}%"
        statement = select(ManagedServiceClient).where(
            or_(ManagedServiceClient.client_id.ilike(term), ManagedServiceClient.name.ilike(term))
        ).order_by(ManagedServiceClient.name.asc())
    return [_client_response(db, row) for row in db.scalars(statement).all()]


@router.post("", response_model=AdminServiceClientCreateResponse, status_code=201)
def create_service_client(
    payload: AdminServiceClientCreateRequest,
    request: Request,
    context: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminServiceClientCreateResponse:
    if db.scalar(select(ManagedServiceClient).where(ManagedServiceClient.client_id == payload.client_id)) is not None:
        raise HTTPException(status_code=409, detail="service client already exists")
    if db.scalar(select(Application).where(Application.client_id == payload.client_id)) is not None:
        raise HTTPException(status_code=409, detail="client id is already used by an interactive application")
    try:
        audiences_json = encode_capabilities(payload.allowed_audiences)
        scopes_json = encode_capabilities(payload.allowed_scopes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    row = ManagedServiceClient(
        client_id=payload.client_id,
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        allowed_audiences_json=audiences_json,
        allowed_scopes_json=scopes_json,
        is_active=True,
        expires_at=_future_expiry(payload.expires_at, field_name="expires_at"),
    )
    db.add(row)
    db.flush()
    credential, secret = create_service_credential(
        db,
        client=row,
        expires_at=_future_expiry(payload.credential_expires_at, field_name="credential_expires_at"),
    )
    record_audit(
        db,
        event_type="admin_service_client_created",
        user=context.user,
        client_id=row.client_id,
        request=request,
        details={
            "credential_id": str(credential.id),
            "allowed_audiences": list(decode_capabilities(row.allowed_audiences_json)),
            "allowed_scopes": list(decode_capabilities(row.allowed_scopes_json)),
        },
    )
    db.commit()
    db.refresh(row)
    return AdminServiceClientCreateResponse(client=_client_response(db, row), client_secret=secret)


@router.patch("/{client_id}", response_model=AdminServiceClientResponse)
def update_service_client(
    client_id: str,
    payload: AdminServiceClientUpdateRequest,
    request: Request,
    context: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminServiceClientResponse:
    row = _find_client(db, client_id)
    changes: dict[str, object] = {}
    if payload.name is not None and payload.name.strip() != row.name:
        row.name = payload.name.strip()
        changes["name"] = row.name
    if payload.description is not None:
        row.description = payload.description.strip() or None
        changes["description_changed"] = True
    if payload.allowed_audiences is not None:
        try:
            row.allowed_audiences_json = encode_capabilities(payload.allowed_audiences)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        changes["allowed_audiences"] = list(decode_capabilities(row.allowed_audiences_json))
    if payload.allowed_scopes is not None:
        try:
            row.allowed_scopes_json = encode_capabilities(payload.allowed_scopes)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        changes["allowed_scopes"] = list(decode_capabilities(row.allowed_scopes_json))
    if payload.is_active is not None and payload.is_active != row.is_active:
        row.is_active = payload.is_active
        changes["is_active"] = row.is_active
    if payload.clear_expiry:
        row.expires_at = None
        changes["expires_at"] = None
    elif payload.expires_at is not None:
        row.expires_at = _future_expiry(payload.expires_at, field_name="expires_at")
        changes["expires_at"] = row.expires_at.isoformat()

    record_audit(
        db,
        event_type="admin_service_client_updated",
        user=context.user,
        client_id=row.client_id,
        request=request,
        details=changes or {"no_change": True},
    )
    db.commit()
    db.refresh(row)
    return _client_response(db, row)


@router.post("/{client_id}/rotate-secret", response_model=AdminServiceSecretResponse)
def rotate_service_client_secret(
    client_id: str,
    payload: AdminServiceSecretRotateRequest,
    request: Request,
    context: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminServiceSecretResponse:
    row = _find_client(db, client_id)
    now = utcnow()
    revoked_ids: list[str] = []
    if payload.revoke_previous:
        existing = db.scalars(
            select(ManagedServiceCredential).where(
                ManagedServiceCredential.service_client_id == row.id,
                ManagedServiceCredential.revoked_at.is_(None),
            )
        ).all()
        for credential in existing:
            credential.revoked_at = now
            revoked_ids.append(str(credential.id))

    expires_at = _future_expiry(payload.expires_at, field_name="expires_at")
    credential, secret = create_service_credential(db, client=row, expires_at=expires_at)
    record_audit(
        db,
        event_type="admin_service_client_secret_rotated",
        user=context.user,
        client_id=row.client_id,
        request=request,
        details={
            "credential_id": str(credential.id),
            "secret_prefix": credential.secret_prefix,
            "revoke_previous": payload.revoke_previous,
            "revoked_credentials": revoked_ids,
            "expires_at": expires_at.isoformat() if expires_at else None,
        },
    )
    db.commit()
    return AdminServiceSecretResponse(
        client_id=row.client_id,
        credential_id=str(credential.id),
        secret_prefix=credential.secret_prefix,
        client_secret=secret,
        expires_at=credential.expires_at,
    )


@router.post("/{client_id}/credentials/{credential_id}/revoke", response_model=AdminServiceCredentialResponse)
def revoke_service_client_credential(
    client_id: str,
    credential_id: uuid.UUID,
    request: Request,
    context: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminServiceCredentialResponse:
    row = _find_client(db, client_id)
    credential = db.scalar(
        select(ManagedServiceCredential).where(
            ManagedServiceCredential.id == credential_id,
            ManagedServiceCredential.service_client_id == row.id,
        )
    )
    if credential is None:
        raise HTTPException(status_code=404, detail="service credential not found")
    if credential.revoked_at is None:
        credential.revoked_at = utcnow()
    record_audit(
        db,
        event_type="admin_service_client_secret_revoked",
        user=context.user,
        client_id=row.client_id,
        request=request,
        details={"credential_id": str(credential.id), "secret_prefix": credential.secret_prefix},
    )
    db.commit()
    db.refresh(credential)
    return _credential_response(credential)


@router.get("/{client_id}/audit", response_model=list[AdminServiceClientAuditResponse])
def service_client_audit_history(
    client_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    _: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AdminServiceClientAuditResponse]:
    _find_client(db, client_id)
    rows = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.client_id == client_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
    ).all()
    result: list[AdminServiceClientAuditResponse] = []
    for event in rows:
        details: dict[str, object] | None = None
        if event.details_json:
            try:
                parsed = json.loads(event.details_json)
                if isinstance(parsed, dict):
                    details = parsed
            except json.JSONDecodeError:
                details = {"unparsed": True}
        result.append(
            AdminServiceClientAuditResponse(
                id=str(event.id),
                event_type=event.event_type,
                success=event.success,
                client_id=event.client_id,
                ip_address=event.ip_address,
                details=details,
                created_at=event.created_at,
            )
        )
    return result
