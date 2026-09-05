from datetime import timedelta
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auth import AdminPrincipal, AuthError, AuthVerifier
from .config import get_settings
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


router = APIRouter(prefix="/v1/admin", tags=["platform-admin"])
bearer = HTTPBearer(auto_error=False)


@lru_cache
def verifier() -> AuthVerifier:
    return AuthVerifier(get_settings())


def admin_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> AdminPrincipal:
    if credentials is None:
        raise HTTPException(status_code=401, detail="missing admin bearer token")
    try:
        return verifier().admin(credentials.credentials)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from None


def require_live_admin(db: Session, principal: AdminPrincipal) -> None:
    import uuid

    user_id = uuid.UUID(principal.sub)
    session_id = uuid.UUID(principal.session_id)
    if db.get(RevokedAuthSession, session_id) is not None:
        raise HTTPException(status_code=401, detail="central admin session revoked")
    user_state = db.get(AuthUserState, user_id)
    if user_state is not None and not user_state.active:
        raise HTTPException(status_code=401, detail="central admin account disabled")
    app_state = db.get(ApplicationState, principal.client_id)
    if app_state is not None and not app_state.active:
        raise HTTPException(status_code=403, detail="platform console disabled")


@router.get("/overview")
def overview(
    principal: Annotated[AdminPrincipal, Depends(admin_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    require_live_admin(db, principal)
    now = utcnow()
    since = now - timedelta(hours=24)
    return {
        "service": "ithute-push",
        "admin": {"sub": principal.sub, "session_id": principal.session_id, "client_id": principal.client_id},
        "endpoints": {
            "total": db.scalar(select(func.count()).select_from(PushEndpoint)) or 0,
            "active": db.scalar(select(func.count()).select_from(PushEndpoint).where(PushEndpoint.active.is_(True))) or 0,
        },
        "messages": {
            "total": db.scalar(select(func.count()).select_from(Message)) or 0,
            "last_24h": db.scalar(select(func.count()).select_from(Message).where(Message.created_at >= since)) or 0,
            "queued": db.scalar(select(func.count()).select_from(Message).where(Message.status == "queued")) or 0,
            "no_endpoints": db.scalar(select(func.count()).select_from(Message).where(Message.status == "no_endpoints")) or 0,
        },
        "deliveries": {
            "queued": db.scalar(select(func.count()).select_from(Delivery).where(Delivery.status == "queued")) or 0,
            "failed": db.scalar(select(func.count()).select_from(Delivery).where(Delivery.status == "failed")) or 0,
            "delivered": db.scalar(select(func.count()).select_from(Delivery).where(Delivery.delivered_at.is_not(None))) or 0,
            "opened": db.scalar(select(func.count()).select_from(Delivery).where(Delivery.opened_at.is_not(None))) or 0,
        },
        "identity_projection": {
            "lifecycle_events": db.scalar(select(func.count()).select_from(AuthLifecycleEvent)) or 0,
            "revoked_sessions": db.scalar(select(func.count()).select_from(RevokedAuthSession)) or 0,
            "disabled_users": db.scalar(select(func.count()).select_from(AuthUserState).where(AuthUserState.active.is_(False))) or 0,
            "disabled_applications": db.scalar(
                select(func.count()).select_from(ApplicationState).where(ApplicationState.active.is_(False))
            ) or 0,
        },
    }


@router.get("/applications")
def applications(
    principal: Annotated[AdminPrincipal, Depends(admin_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict[str, object]]:
    require_live_admin(db, principal)
    endpoint_rows = db.execute(
        select(
            PushEndpoint.application_id,
            func.count(PushEndpoint.id),
            func.count(PushEndpoint.id).filter(PushEndpoint.active.is_(True)),
        ).group_by(PushEndpoint.application_id)
    ).all()
    message_rows = dict(
        db.execute(select(Message.source_client_id, func.count(Message.id)).group_by(Message.source_client_id)).all()
    )
    results: list[dict[str, object]] = []
    for client_id, total_endpoints, active_endpoints in endpoint_rows:
        state = db.get(ApplicationState, client_id)
        results.append(
            {
                "client_id": client_id,
                "active": True if state is None else state.active,
                "endpoints": int(total_endpoints or 0),
                "active_endpoints": int(active_endpoints or 0),
                "messages": int(message_rows.get(client_id, 0)),
            }
        )
    known = {str(row["client_id"]) for row in results}
    for client_id, count in message_rows.items():
        if client_id not in known:
            state = db.get(ApplicationState, client_id)
            results.append(
                {
                    "client_id": client_id,
                    "active": True if state is None else state.active,
                    "endpoints": 0,
                    "active_endpoints": 0,
                    "messages": int(count),
                }
            )
    return sorted(results, key=lambda item: str(item["client_id"]))


@router.get("/messages")
def recent_messages(
    principal: Annotated[AdminPrincipal, Depends(admin_principal)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=25, ge=1, le=100),
) -> list[dict[str, object]]:
    require_live_admin(db, principal)
    rows = db.scalars(select(Message).order_by(Message.created_at.desc()).limit(limit)).all()
    return [
        {
            "id": str(row.id),
            "source_client_id": row.source_client_id,
            "recipient_sub": str(row.recipient_user_id),
            "status": row.status,
            "created_at": row.created_at,
            "expires_at": row.expires_at,
            "delivery_count": len(row.deliveries),
        }
        for row in rows
    ]
