from datetime import datetime, timezone
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rbac import has_permission
from app.core.security import ALGORITHM, hash_token
from app.db.session import get_db
from app.models import ApiKey, MembershipStatus, Tenant, TenantMembership, User
from app.services.ithute_auth import (
    IthuteAuthDisabled,
    IthuteAuthUnavailable,
    decode_ithute_access_token,
    ithute_auth_enabled,
)

bearer = HTTPBearer(auto_error=False)


def _decode_local_user(token: str, db: Session) -> User:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "iat", "sub", "type"]},
        )
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = UUID(str(payload.get("sub")))
        token_version = int(payload.get("sv", 0))
    except (InvalidTokenError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    user = db.get(User, user_id)
    if not user or not user.is_active or token_version != user.session_version:
        raise HTTPException(status_code=401, detail="Inactive, expired, or unknown user")
    return user


def _decode_central_user(token: str, db: Session) -> User:
    try:
        claims = decode_ithute_access_token(token)
    except IthuteAuthDisabled as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    except IthuteAuthUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="!thute Auth verification is temporarily unavailable",
        ) from exc
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    auth_user_id = UUID(str(claims["sub"]))
    user = db.scalar(select(User).where(User.auth_user_id == auth_user_id))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "ITHUTE_ACCOUNT_NOT_LINKED",
                "message": "This !thute account is not linked to a Mailbox DNS user.",
            },
        )
    return user


def _token_algorithm(token: str) -> str:
    try:
        header = jwt.get_unverified_header(token)
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    algorithm = str(header.get("alg") or "")
    if algorithm not in {ALGORITHM, "RS256"}:
        raise HTTPException(status_code=401, detail="Invalid token")
    return algorithm


def get_current_local_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    """Require a Mailbox DNS-issued session for sensitive migration actions."""
    token = credentials.credentials if credentials else request.cookies.get(settings.access_cookie_name)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    if _token_algorithm(token) != ALGORITHM:
        raise HTTPException(status_code=401, detail="A current Mailbox DNS session is required")
    return _decode_local_user(token, db)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials if credentials else request.cookies.get(settings.access_cookie_name)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    algorithm = _token_algorithm(token)
    if algorithm == ALGORITHM:
        return _decode_local_user(token, db)
    if algorithm == "RS256" and ithute_auth_enabled():
        return _decode_central_user(token, db)
    raise HTTPException(status_code=401, detail="Invalid token")


def require_platform_owner(current: User = Depends(get_current_user)) -> User:
    if not current.is_platform_owner:
        raise HTTPException(status_code=403, detail="Platform owner required")
    return current


def require_tenant_membership(tenant_id: UUID, db: Session, current: User) -> TenantMembership:
    if not db.get(Tenant, tenant_id):
        raise HTTPException(status_code=404, detail="Tenant not found")
    membership = db.scalar(
        select(TenantMembership).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == current.id,
        )
    )
    if not membership or membership.status != MembershipStatus.active:
        raise HTTPException(status_code=403, detail="Active tenant membership required")
    return membership


def require_tenant_permission(tenant_id: UUID, permission: str, db: Session, current: User) -> TenantMembership | None:
    if not db.get(Tenant, tenant_id):
        raise HTTPException(status_code=404, detail="Tenant not found")
    if current.is_platform_owner:
        return None
    membership = require_tenant_membership(tenant_id, db, current)
    if not has_permission(membership.role, permission):
        raise HTTPException(status_code=403, detail=f"Permission required: {permission}")
    return membership


def authenticate_api_key(raw_key: str, db: Session) -> ApiKey:
    key = db.scalar(select(ApiKey).where(ApiKey.key_hash == hash_token(raw_key)))
    now = datetime.now(timezone.utc)
    if not key or key.revoked_at is not None or (key.expires_at is not None and key.expires_at <= now):
        raise HTTPException(status_code=401, detail="Invalid or expired API key")
    return key
