import hashlib
import json
import uuid
from collections import Counter
from datetime import timedelta
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import AuthError, AuthVerifier, LifecyclePrincipal, ServicePrincipal, UserPrincipal
from .config import Settings, get_settings
from .crypto import EndpointCipher, endpoint_hash
from .db import get_db
from .models import (
    ApplicationState,
    AuthLifecycleEvent,
    AuthUserState,
    Delivery,
    Message,
    PushEndpoint,
    RevokedAuthSession,
    utcnow,
)
from .schemas import (
    AuthLifecycleEventRequest,
    AuthLifecycleEventResponse,
    DeliveryAckRequest,
    DeliveryAckResponse,
    DeliverySummary,
    DeviceRequest,
    DeviceResponse,
    MessageRequest,
    MessageResponse,
    MessageSummary,
)


bearer = HTTPBearer(auto_error=False)
app = FastAPI(title="!thute Push", version="1.1.0", redoc_url=None)


@lru_cache
def verifier() -> AuthVerifier:
    return AuthVerifier(get_settings())


@lru_cache
def cipher() -> EndpointCipher:
    return EndpointCipher(get_settings().endpoint_encryption_key)


def bearer_token(credentials: HTTPAuthorizationCredentials | None) -> str:
    if credentials is None:
        raise HTTPException(status_code=401, detail="missing bearer token")
    return credentials.credentials


def user_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> UserPrincipal:
    try:
        return verifier().user(bearer_token(credentials))
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from None


def service_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> ServicePrincipal:
    try:
        return verifier().service(bearer_token(credentials))
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from None


def lifecycle_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> LifecyclePrincipal:
    try:
        return verifier().lifecycle(bearer_token(credentials))
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from None


def principal_uuid(principal: UserPrincipal) -> uuid.UUID:
    try:
        return uuid.UUID(principal.sub)
    except ValueError:
        raise HTTPException(status_code=401, detail="central subject is not a UUID") from None


def principal_session_uuid(principal: UserPrincipal) -> uuid.UUID:
    try:
        return uuid.UUID(principal.session_id)
    except ValueError:
        raise HTTPException(status_code=401, detail="central session is not a UUID") from None


def require_live_user_state(db: Session, principal: UserPrincipal) -> tuple[uuid.UUID, uuid.UUID]:
    user_id = principal_uuid(principal)
    session_id = principal_session_uuid(principal)
    user_state = db.get(AuthUserState, user_id)
    if user_state is not None and not user_state.active:
        raise HTTPException(status_code=401, detail="central account disabled")
    app_state = db.get(ApplicationState, principal.client_id)
    if app_state is not None and not app_state.active:
        raise HTTPException(status_code=401, detail="product disabled")
    if db.get(RevokedAuthSession, session_id) is not None:
        raise HTTPException(status_code=401, detail="central session revoked")
    return user_id, session_id


def require_live_service_state(db: Session, principal: ServicePrincipal) -> None:
    state = db.get(ApplicationState, principal.client_id)
    if state is not None and not state.active:
        raise HTTPException(status_code=403, detail="product disabled")


def provider_for(platform: str) -> str:
    return {"android": "fcm", "ios": "apns", "web": "webpush"}[platform]


def message_fingerprint(payload: MessageRequest) -> str:
    raw = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def clean_idempotency_key(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value or len(value) > 128:
        raise HTTPException(status_code=422, detail="Idempotency-Key must contain 1 to 128 characters")
    return value


def existing_message_response(existing: Message, fingerprint: str) -> MessageResponse:
    if existing.request_fingerprint != fingerprint:
        raise HTTPException(status_code=409, detail="Idempotency-Key was already used for a different notification")
    return MessageResponse(
        id=existing.id,
        status=existing.status,
        delivery_count=len(existing.deliveries),
        deduplicated=True,
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "ithute-push"}


@app.get("/readyz")
def readyz(response: Response, settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, object]:
    try:
        EndpointCipher(settings.endpoint_encryption_key)
        encryption_ready = True
    except (TypeError, ValueError):
        encryption_ready = False
    providers = settings.provider_readiness()
    missing = settings.missing_required_providers()
    ready = encryption_ready and not missing
    if not ready:
        response.status_code = 503
    return {
        "status": "ready" if ready else "not_ready",
        "service": "ithute-push",
        "endpoint_encryption": encryption_ready,
        "providers": providers,
        "required_providers": sorted(settings.required_provider_set),
        "missing_required_providers": missing,
    }


@app.post("/v1/internal/auth-events", response_model=AuthLifecycleEventResponse)
def apply_auth_event(
    payload: AuthLifecycleEventRequest,
    _: Annotated[LifecyclePrincipal, Depends(lifecycle_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> AuthLifecycleEventResponse:
    existing = db.get(AuthLifecycleEvent, payload.event_id)
    if existing is not None:
        return AuthLifecycleEventResponse(event_id=payload.event_id, applied=True, deduplicated=True)

    db.add(
        AuthLifecycleEvent(
            event_id=payload.event_id,
            event_type=payload.type,
            auth_user_id=payload.sub,
            auth_session_id=payload.sid,
            application_id=payload.client_id,
            occurred_at=payload.occurred_at,
            details_json=json.dumps(payload.details, separators=(",", ":"), sort_keys=True),
        )
    )
    applied = True

    if payload.type == "session.revoked":
        assert payload.sub is not None and payload.sid is not None and payload.client_id is not None
        revoked = db.get(RevokedAuthSession, payload.sid)
        if revoked is None:
            db.add(
                RevokedAuthSession(
                    session_id=payload.sid,
                    auth_user_id=payload.sub,
                    application_id=payload.client_id,
                    revoked_at=payload.occurred_at,
                    event_id=payload.event_id,
                )
            )
        elif payload.occurred_at < revoked.revoked_at:
            applied = False
        endpoints = db.scalars(select(PushEndpoint).where(PushEndpoint.auth_session_id == payload.sid)).all()
        for endpoint in endpoints:
            endpoint.active = False

    elif payload.type in {"account.disabled", "account.enabled"}:
        assert payload.sub is not None
        desired_active = payload.type == "account.enabled"
        state = db.get(AuthUserState, payload.sub)
        if state is None:
            db.add(
                AuthUserState(
                    auth_user_id=payload.sub,
                    active=desired_active,
                    changed_at=payload.occurred_at,
                    event_id=payload.event_id,
                )
            )
        elif payload.occurred_at >= state.changed_at:
            state.active = desired_active
            state.changed_at = payload.occurred_at
            state.event_id = payload.event_id
        else:
            applied = False
        if applied and not desired_active:
            endpoints = db.scalars(select(PushEndpoint).where(PushEndpoint.auth_user_id == payload.sub)).all()
            for endpoint in endpoints:
                endpoint.active = False

    elif payload.type in {"application.disabled", "application.enabled"}:
        assert payload.client_id is not None
        desired_active = payload.type == "application.enabled"
        state = db.get(ApplicationState, payload.client_id)
        if state is None:
            db.add(
                ApplicationState(
                    application_id=payload.client_id,
                    active=desired_active,
                    changed_at=payload.occurred_at,
                    event_id=payload.event_id,
                )
            )
        elif payload.occurred_at >= state.changed_at:
            state.active = desired_active
            state.changed_at = payload.occurred_at
            state.event_id = payload.event_id
        else:
            applied = False
        if applied and not desired_active:
            endpoints = db.scalars(select(PushEndpoint).where(PushEndpoint.application_id == payload.client_id)).all()
            for endpoint in endpoints:
                endpoint.active = False

    db.commit()
    return AuthLifecycleEventResponse(event_id=payload.event_id, applied=applied)


@app.post("/v1/devices", response_model=DeviceResponse)
def register_device(
    payload: DeviceRequest,
    principal: Annotated[UserPrincipal, Depends(user_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> DeviceResponse:
    user_id, session_id = require_live_user_state(db, principal)
    endpoint = db.scalar(
        select(PushEndpoint).where(
            PushEndpoint.auth_user_id == user_id,
            PushEndpoint.application_id == principal.client_id,
            PushEndpoint.device_key == payload.device_key,
        )
    )
    encrypted = cipher().encrypt(payload.provider_endpoint)
    digest = endpoint_hash(payload.provider_endpoint)

    duplicates = list(
        db.scalars(
            select(PushEndpoint).where(
                PushEndpoint.application_id == principal.client_id,
                PushEndpoint.endpoint_hash == digest,
                PushEndpoint.active.is_(True),
            )
        )
    )
    for duplicate in duplicates:
        if endpoint is None or duplicate.id != endpoint.id:
            duplicate.active = False

    if endpoint is None:
        endpoint = PushEndpoint(
            auth_user_id=user_id,
            auth_session_id=session_id,
            application_id=principal.client_id,
            device_key=payload.device_key,
            platform=payload.platform,
            provider=provider_for(payload.platform),
            endpoint_ciphertext=encrypted,
            endpoint_hash=digest,
        )
        db.add(endpoint)
    else:
        endpoint.auth_session_id = session_id
        endpoint.platform = payload.platform
        endpoint.provider = provider_for(payload.platform)
        endpoint.endpoint_ciphertext = encrypted
        endpoint.endpoint_hash = digest
        endpoint.active = True
        endpoint.last_seen_at = utcnow()
    db.commit()
    db.refresh(endpoint)
    return DeviceResponse(
        device_key=endpoint.device_key,
        application_id=endpoint.application_id,
        platform=endpoint.platform,
        active=endpoint.active,
        last_seen_at=endpoint.last_seen_at,
    )


@app.get("/v1/devices", response_model=list[DeviceResponse])
def list_devices(
    principal: Annotated[UserPrincipal, Depends(user_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[DeviceResponse]:
    user_id, _ = require_live_user_state(db, principal)
    endpoints = list(
        db.scalars(
            select(PushEndpoint)
            .where(PushEndpoint.auth_user_id == user_id, PushEndpoint.application_id == principal.client_id)
            .order_by(PushEndpoint.last_seen_at.desc())
        )
    )
    return [
        DeviceResponse(
            device_key=item.device_key,
            application_id=item.application_id,
            platform=item.platform,
            active=item.active,
            last_seen_at=item.last_seen_at,
        )
        for item in endpoints
    ]


@app.delete("/v1/devices/{device_key}", status_code=204)
def revoke_device(
    device_key: str,
    principal: Annotated[UserPrincipal, Depends(user_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    user_id, _ = require_live_user_state(db, principal)
    endpoint = db.scalar(
        select(PushEndpoint).where(
            PushEndpoint.auth_user_id == user_id,
            PushEndpoint.application_id == principal.client_id,
            PushEndpoint.device_key == device_key,
        )
    )
    if endpoint is not None:
        endpoint.active = False
        db.commit()


@app.post("/v1/messages", response_model=MessageResponse, status_code=202)
def queue_message(
    payload: MessageRequest,
    principal: Annotated[ServicePrincipal, Depends(service_principal)],
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> MessageResponse:
    require_live_service_state(db, principal)
    key = clean_idempotency_key(idempotency_key)
    fingerprint = message_fingerprint(payload)
    if key:
        existing = db.scalar(
            select(Message).where(
                Message.source_client_id == principal.client_id,
                Message.idempotency_key == key,
            )
        )
        if existing is not None:
            return existing_message_response(existing, fingerprint)

    user_state = db.get(AuthUserState, payload.recipient_sub)
    user_disabled = user_state is not None and not user_state.active
    endpoints = [] if user_disabled else list(
        db.scalars(
            select(PushEndpoint).where(
                PushEndpoint.auth_user_id == payload.recipient_sub,
                PushEndpoint.application_id == principal.client_id,
                PushEndpoint.auth_session_id.is_not(None),
                PushEndpoint.active.is_(True),
                ~PushEndpoint.auth_session_id.in_(select(RevokedAuthSession.session_id)),
            )
        )
    )
    message = Message(
        source_client_id=principal.client_id,
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
                Message.source_client_id == principal.client_id,
                Message.idempotency_key == key,
            )
        )
        if existing is None:
            raise
        return existing_message_response(existing, fingerprint)

    for endpoint in endpoints:
        db.add(Delivery(message_id=message.id, endpoint_id=endpoint.id))
    db.commit()
    return MessageResponse(id=message.id, status=message.status, delivery_count=len(endpoints))


@app.post("/v1/deliveries/{delivery_id}/ack", response_model=DeliveryAckResponse)
def acknowledge_delivery(
    delivery_id: uuid.UUID,
    payload: DeliveryAckRequest,
    principal: Annotated[UserPrincipal, Depends(user_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> DeliveryAckResponse:
    user_id, _ = require_live_user_state(db, principal)
    delivery = db.get(Delivery, delivery_id)
    if (
        delivery is None
        or delivery.endpoint.auth_user_id != user_id
        or delivery.endpoint.application_id != principal.client_id
        or delivery.message.source_client_id != principal.client_id
    ):
        raise HTTPException(status_code=404, detail="delivery not found")

    now = utcnow()
    if payload.state == "received" and delivery.received_at is None:
        delivery.received_at = now
    if payload.state == "opened":
        if delivery.received_at is None:
            delivery.received_at = now
        if delivery.opened_at is None:
            delivery.opened_at = now
    db.commit()
    return DeliveryAckResponse(
        id=delivery.id,
        state=payload.state,
        received_at=delivery.received_at,
        opened_at=delivery.opened_at,
    )


@app.get("/v1/messages/{message_id}", response_model=MessageSummary)
def message_summary(
    message_id: uuid.UUID,
    principal: Annotated[ServicePrincipal, Depends(service_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> MessageSummary:
    require_live_service_state(db, principal)
    message = db.get(Message, message_id)
    if message is None or message.source_client_id != principal.client_id:
        raise HTTPException(status_code=404, detail="message not found")
    counts = Counter(delivery.status for delivery in message.deliveries)
    return MessageSummary(
        id=message.id,
        source_client_id=message.source_client_id,
        recipient_sub=message.recipient_user_id,
        status=message.status,
        deliveries=[DeliverySummary(status=key, count=value) for key, value in sorted(counts.items())],
        received_count=sum(1 for delivery in message.deliveries if delivery.received_at is not None),
        opened_count=sum(1 for delivery in message.deliveries if delivery.opened_at is not None),
    )
