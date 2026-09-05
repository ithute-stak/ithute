import hashlib
import json
from datetime import timedelta
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import AuthError, AuthVerifier, ServicePrincipal
from .config import get_settings
from .db import get_db
from .models import Delivery, Message, PushEndpoint, utcnow
from .schemas import DelegatedMessageRequest, MessageResponse

router = APIRouter()
bearer = HTTPBearer(auto_error=False)


@lru_cache
def verifier() -> AuthVerifier:
    return AuthVerifier(get_settings())


def delegated_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> ServicePrincipal:
    if credentials is None:
        raise HTTPException(status_code=401, detail="missing bearer token")
    try:
        principal = verifier().service(credentials.credentials, "push.send.delegated")
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from None
    if principal.client_id not in get_settings().delegated_clients:
        raise HTTPException(status_code=403, detail="delegated push is restricted to approved platform services")
    return principal


def _clean_key(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value or len(value) > 128:
        raise HTTPException(status_code=422, detail="Idempotency-Key must contain 1 to 128 characters")
    return value


def _fingerprint(payload: DelegatedMessageRequest) -> str:
    raw = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _existing(existing: Message, fingerprint: str) -> MessageResponse:
    if existing.request_fingerprint != fingerprint:
        raise HTTPException(status_code=409, detail="Idempotency-Key was already used for a different notification")
    return MessageResponse(id=existing.id, status=existing.status, delivery_count=len(existing.deliveries), deduplicated=True)


@router.post("/v1/platform/messages", response_model=MessageResponse, status_code=202)
def delegated_message(
    payload: DelegatedMessageRequest,
    _: Annotated[ServicePrincipal, Depends(delegated_principal)],
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> MessageResponse:
    settings = get_settings()
    source_client_id = payload.source_client_id.strip()
    if source_client_id not in settings.user_clients:
        raise HTTPException(status_code=422, detail="unapproved target product namespace")
    key = _clean_key(idempotency_key)
    fingerprint = _fingerprint(payload)
    if key:
        existing = db.scalar(
            select(Message).where(
                Message.source_client_id == source_client_id,
                Message.idempotency_key == key,
            )
        )
        if existing is not None:
            return _existing(existing, fingerprint)

    endpoints = list(
        db.scalars(
            select(PushEndpoint).where(
                PushEndpoint.auth_user_id == payload.recipient_sub,
                PushEndpoint.application_id == source_client_id,
                PushEndpoint.active.is_(True),
            )
        )
    )
    message = Message(
        source_client_id=source_client_id,
        recipient_user_id=payload.recipient_sub,
        idempotency_key=key,
        request_fingerprint=fingerprint if key else None,
        title=payload.title,
        body=payload.body,
        route=payload.route,
        sound=payload.sound,
        data_json=json.dumps(payload.data, separators=(",", ":"), ensure_ascii=False),
        status="queued" if endpoints else "no_endpoints",
        expires_at=utcnow() + timedelta(seconds=payload.ttl_seconds),
    )
    db.add(message)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        if not key:
            raise
        existing = db.scalar(
            select(Message).where(
                Message.source_client_id == source_client_id,
                Message.idempotency_key == key,
            )
        )
        if existing is None:
            raise
        return _existing(existing, fingerprint)

    for endpoint in endpoints:
        db.add(Delivery(message_id=message.id, endpoint_id=endpoint.id))
    db.commit()
    db.refresh(message)
    return MessageResponse(id=message.id, status=message.status, delivery_count=len(endpoints))
