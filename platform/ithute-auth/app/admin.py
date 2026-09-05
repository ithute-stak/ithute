import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .account import AuthContext, authenticated_context
from .admin_delegation import PUSH_ADMIN_CLIENT_ID, PUSH_ADMIN_TOKEN_MINUTES, create_push_admin_token
from .config import Settings, get_settings
from .db import get_db
from .models import Application, AuditEvent, AuthEventOutbox, AuthSession, User, utcnow
from .schemas import (
    AdminApplicationResponse,
    AdminApplicationUpdateRequest,
    AdminUserResponse,
    AdminUserUpdateRequest,
)
from .security_service import record_audit, revoke_sessions


router = APIRouter(prefix="/v1/admin", tags=["platform-admin"])


def require_admin(context: AuthContext = Depends(authenticated_context)) -> AuthContext:
    if not context.user.is_platform_admin:
        raise HTTPException(status_code=403, detail="platform admin required")
    return context


def _user_response(user: User) -> AdminUserResponse:
    return AdminUserResponse(
        id=str(user.id),
        email=user.email,
        phone=user.phone,
        display_name=user.display_name,
        is_active=user.is_active,
        is_platform_admin=user.is_platform_admin,
        mfa_enabled=user.totp_enabled,
        email_verified=user.email_verified,
        phone_verified=user.phone_verified,
        failed_login_attempts=user.failed_login_attempts,
        locked_until=user.locked_until,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )


@router.get("/overview")
def admin_overview(
    context: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    now = utcnow()
    return {
        "service": "ithute-auth",
        "admin": {
            "sub": str(context.user.id),
            "display_name": context.user.display_name,
            "email": context.user.email,
            "session_id": str(context.session.id),
            "client_id": context.session.client_id,
        },
        "users": {
            "total": db.scalar(select(func.count()).select_from(User)) or 0,
            "active": db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True))) or 0,
            "platform_admins": db.scalar(
                select(func.count()).select_from(User).where(User.is_platform_admin.is_(True), User.is_active.is_(True))
            ) or 0,
            "mfa_enabled": db.scalar(select(func.count()).select_from(User).where(User.totp_enabled.is_(True))) or 0,
            "locked": db.scalar(select(func.count()).select_from(User).where(User.locked_until.is_not(None), User.locked_until > now)) or 0,
        },
        "sessions": {
            "active": db.scalar(
                select(func.count()).select_from(AuthSession).where(
                    AuthSession.revoked_at.is_(None),
                    AuthSession.expires_at > now,
                )
            ) or 0,
            "revoked": db.scalar(select(func.count()).select_from(AuthSession).where(AuthSession.revoked_at.is_not(None))) or 0,
        },
        "applications": {
            "total": db.scalar(select(func.count()).select_from(Application)) or 0,
            "active": db.scalar(select(func.count()).select_from(Application).where(Application.is_active.is_(True))) or 0,
        },
        "security": {
            "audit_events": db.scalar(select(func.count()).select_from(AuditEvent)) or 0,
            "pending_push_events": db.scalar(
                select(func.count()).select_from(AuthEventOutbox).where(AuthEventOutbox.delivered_at.is_(None))
            ) or 0,
        },
    }


@router.post("/push-token")
def issue_push_admin_token(
    request: Request,
    context: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    if context.session.client_id != PUSH_ADMIN_CLIENT_ID:
        raise HTTPException(status_code=403, detail="central admin step-up must originate from the platform console")
    token = create_push_admin_token(
        settings=settings,
        user_id=context.user.id,
        client_id=context.session.client_id,
        session_id=context.session.id,
    )
    record_audit(
        db,
        event_type="admin_push_delegation_issued",
        user=context.user,
        client_id=context.session.client_id,
        request=request,
        details={"audience": "ithute-push", "scope": "push.admin"},
    )
    db.commit()
    return {
        "access_token": token,
        "token_type": "Bearer",
        "scope": "push.admin",
        "expires_in": PUSH_ADMIN_TOKEN_MINUTES * 60,
    }


@router.get("/users", response_model=list[AdminUserResponse])
def list_users(
    q: str | None = Query(default=None, max_length=160),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AdminUserResponse]:
    statement = select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
    if q and q.strip():
        term = f"%{q.strip()}%"
        statement = (
            select(User)
            .where(or_(User.display_name.ilike(term), User.email.ilike(term), User.phone.ilike(term)))
            .order_by(User.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    return [_user_response(user) for user in db.scalars(statement).all()]


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
def update_user_security(
    user_id: uuid.UUID,
    payload: AdminUserUpdateRequest,
    request: Request,
    context: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminUserResponse:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    if user.id == context.user.id and payload.is_active is False:
        raise HTTPException(status_code=400, detail="cannot disable your own admin account")

    changes: dict[str, object] = {}
    if payload.is_active is not None and user.is_active != payload.is_active:
        user.is_active = payload.is_active
        changes["is_active"] = payload.is_active
        if not payload.is_active:
            revoke_sessions(db, user_id=user.id, reason="account disabled by platform admin")
            user.security_version += 1
    if payload.unlock:
        user.failed_login_attempts = 0
        user.locked_until = None
        changes["unlocked"] = True

    record_audit(
        db,
        event_type="admin_user_security_updated",
        user=context.user,
        request=request,
        details={"target_user_id": str(user.id), **changes},
    )
    db.commit()
    db.refresh(user)
    return _user_response(user)


@router.post("/users/{user_id}/revoke-sessions")
def admin_revoke_user_sessions(
    user_id: uuid.UUID,
    request: Request,
    context: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    except_session_id = context.session.id if user.id == context.user.id else None
    count = revoke_sessions(
        db,
        user_id=user.id,
        reason="revoked by platform admin",
        except_session_id=except_session_id,
    )
    record_audit(
        db,
        event_type="admin_sessions_revoked",
        user=context.user,
        request=request,
        details={"target_user_id": str(user.id), "count": count},
    )
    db.commit()
    return {"revoked": count}


@router.get("/applications", response_model=list[AdminApplicationResponse])
def list_applications(
    _: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AdminApplicationResponse]:
    rows = db.scalars(select(Application).order_by(Application.name.asc())).all()
    return [
        AdminApplicationResponse(
            client_id=row.client_id,
            name=row.name,
            is_active=row.is_active,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.patch("/applications/{client_id}", response_model=AdminApplicationResponse)
def update_application(
    client_id: str,
    payload: AdminApplicationUpdateRequest,
    request: Request,
    context: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminApplicationResponse:
    application = db.scalar(select(Application).where(Application.client_id == client_id))
    if application is None:
        raise HTTPException(status_code=404, detail="application not found")
    changes: dict[str, object] = {}
    if payload.name is not None and payload.name.strip() != application.name:
        application.name = payload.name.strip()
        changes["name"] = application.name
    if payload.is_active is not None and payload.is_active != application.is_active:
        application.is_active = payload.is_active
        changes["is_active"] = payload.is_active
        if not payload.is_active:
            rows = db.scalars(
                select(AuthSession).where(
                    AuthSession.client_id == application.client_id,
                    AuthSession.revoked_at.is_(None),
                )
            ).all()
            now = utcnow()
            for row in rows:
                row.revoked_at = now
                row.revoked_reason = "application disabled"

    record_audit(
        db,
        event_type="admin_application_updated",
        user=context.user,
        client_id=application.client_id,
        request=request,
        details=changes or {"no_change": True},
    )
    db.commit()
    db.refresh(application)
    return AdminApplicationResponse(
        client_id=application.client_id,
        name=application.name,
        is_active=application.is_active,
        created_at=application.created_at,
    )
