from __future__ import annotations

import hashlib
import json
import uuid
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import AuthError, ServicePrincipal, verifier
from .db import get_db
from .models import Notification, NotificationDelivery
from .schemas import DeliveryResponse, NotificationRequest, NotificationResponse

app = FastAPI(title="Ithute Notification", version="1.0.0")
bearer = HTTPBearer(auto_error=False)


def notification_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> ServicePrincipal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="managed Ithute service token required")
    try:
        return verifier().service(credentials.credentials, "notification.send")
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from None


def _key(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized or len(normalized) > 128:
        raise HTTPException(status_code=422, detail="Idempotency-Key must contain 1 to 128 characters")
    return normalized


def _fingerprint(payload: NotificationRequest) -> str:
    raw = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _response(item: Notification, *, deduplicated: bool = False) -> NotificationResponse:
    return NotificationResponse(
        id=item.id,
        status=item.status,
        source_client_id=item.source_client_id,
        deduplicated=deduplicated,
        deliveries=[
            DeliveryResponse(
                channel=delivery.channel,
                status=delivery.status,
                attempt_count=delivery.attempt_count,
                provider_reference=delivery.provider_reference,
                last_error=delivery.last_error,
            )
            for delivery in item.deliveries
        ],
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "ithute-notification"}


@app.get("/readyz")
def readyz(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ready", "service": "ithute-notification"}


@app.post("/v1/notifications", response_model=NotificationResponse, status_code=202)
def create_notification(
    payload: NotificationRequest,
    principal: Annotated[ServicePrincipal, Depends(notification_principal)],
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> NotificationResponse:
    if payload.source_client_id != principal.client_id:
        raise HTTPException(status_code=403, detail="source_client_id must match authenticated service identity")
    key = _key(idempotency_key)
    fingerprint = _fingerprint(payload)
    if key:
        existing = db.scalar(
            select(Notification).where(
                Notification.source_client_id == principal.client_id,
                Notification.idempotency_key == key,
            )
        )
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise HTTPException(status_code=409, detail="Idempotency-Key was already used for a different notification")
            return _response(existing, deduplicated=True)

    item = Notification(
        source_client_id=principal.client_id,
        idempotency_key=key,
        request_fingerprint=fingerprint if key else None,
        recipient_sub=str(payload.recipient_sub) if payload.recipient_sub else None,
        recipient_email=str(payload.recipient_email) if payload.recipient_email else None,
        recipient_phone=payload.recipient_phone.strip() if payload.recipient_phone else None,
        title=payload.title,
        body=payload.body,
        route=payload.route,
        data_json=json.dumps(
            {"data": payload.data, "sound": payload.sound, "ttl_seconds": payload.ttl_seconds},
            separators=(",", ":"),
        ),
        channels_json=json.dumps(payload.channels, separators=(",", ":")),
        status="queued",
    )
    try:
        db.add(item)
        # PostgreSQL can surface the idempotency unique-key race here, before
        # commit. Keep flush and commit in the same IntegrityError boundary so
        # concurrent identical requests deterministically resolve to the row
        # that won the race instead of leaking a 500 response.
        db.flush()
        for channel in payload.channels:
            db.add(NotificationDelivery(notification_id=item.id, channel=channel, status="pending"))
        db.commit()
    except IntegrityError:
        db.rollback()
        if not key:
            raise
        existing = db.scalar(
            select(Notification).where(
                Notification.source_client_id == principal.client_id,
                Notification.idempotency_key == key,
            )
        )
        if existing is None:
            raise
        if existing.request_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency-Key was already used for a different notification")
        return _response(existing, deduplicated=True)
    db.refresh(item)
    return _response(item)


@app.get("/v1/notifications/{notification_id}", response_model=NotificationResponse)
def get_notification(
    notification_id: uuid.UUID,
    principal: Annotated[ServicePrincipal, Depends(notification_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> NotificationResponse:
    item = db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.source_client_id == principal.client_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="notification not found")
    return _response(item)
