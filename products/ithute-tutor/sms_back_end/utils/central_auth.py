from __future__ import annotations

import uuid
from typing import Any

import jwt
from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from database.config.config import settings
from database.multi_tenant_school_management.models import User
from database.multi_tenant_school_management.models.enum.user_role import UserRole


class CentralAuthError(ValueError):
    pass


def validate_central_access_token(token: str) -> dict[str, Any]:
    try:
        signing_key = jwt.PyJWKClient(settings.auth_jwks_url).get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            issuer=settings.auth_issuer,
            audience=settings.AUTH_AUDIENCE,
            options={"require": ["exp", "iss", "aud", "sub", "token_use"]},
        )
    except jwt.PyJWTError as exc:
        raise CentralAuthError("invalid central auth access token") from exc

    if claims.get("token_use") != "access":
        raise CentralAuthError("central auth token is not an access token")

    subject = claims.get("sub")
    try:
        uuid.UUID(str(subject))
    except (TypeError, ValueError) as exc:
        raise CentralAuthError("central auth token is missing a valid subject") from exc

    return claims


def request_access_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        return authorization[7:].strip() or None
    return request.cookies.get(settings.AUTH_ACCESS_COOKIE_NAME)


def require_central_claims(request: Request) -> dict[str, Any]:
    # AuthContextMiddleware validates the same bearer/cookie token before the
    # route runs. Reuse those verified claims instead of fetching JWKS and
    # validating the JWT twice for every authenticated Tutor request.
    cached_claims = getattr(request.state, "central_claims", None)
    if isinstance(cached_claims, dict):
        return cached_claims

    token = request_access_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing central auth access token",
        )
    try:
        claims = validate_central_access_token(token)
        request.state.central_claims = claims
        return claims
    except CentralAuthError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid central auth access token",
        ) from None


def project_platform_owner(db: Session, claims: dict[str, Any]) -> User:
    """Create/link Tutor's super-admin projection from the signed central claim."""
    subject = uuid.UUID(str(claims["sub"]))
    email = str(claims.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail="central platform owner token is missing an email claim")

    user = db.query(User).filter(User.auth_user_id == subject).first()
    if user is None:
        user = db.query(User).filter(User.email == email).first()
        if user is not None and user.auth_user_id not in (None, subject):
            raise HTTPException(status_code=409, detail="system owner email is linked to another central identity")

    if user is None:
        user = User(
            auth_user_id=subject,
            username="Ithute System Owner",
            email=email,
            password=None,
            channel="system",
            role=UserRole.super_admin,
            school_id=None,
        )
        db.add(user)
    else:
        user.auth_user_id = subject
        user.role = UserRole.super_admin
        if not str(user.username or "").strip():
            user.username = "Ithute System Owner"

    db.commit()
    db.refresh(user)
    return user


def resolve_tutor_user(db: Session, claims: dict[str, Any]) -> User:
    if claims.get("is_platform_admin") is True:
        return project_platform_owner(db, claims)

    subject = uuid.UUID(str(claims["sub"]))
    user = db.query(User).filter(User.auth_user_id == subject).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tutor profile is not linked to this !thute account",
        )
    return user
