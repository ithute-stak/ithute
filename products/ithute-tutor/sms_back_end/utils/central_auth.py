from __future__ import annotations

import uuid
from typing import Any

import jwt
from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from database.config.config import settings
from database.multi_tenant_school_management.models import User


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
    token = request_access_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing central auth access token",
        )
    try:
        return validate_central_access_token(token)
    except CentralAuthError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid central auth access token",
        ) from None


def resolve_tutor_user(db: Session, claims: dict[str, Any]) -> User:
    subject = uuid.UUID(str(claims["sub"]))
    user = db.query(User).filter(User.auth_user_id == subject).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tutor profile is not linked to this !thute account",
        )
    return user
