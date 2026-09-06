from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from database.config.config import settings
from database.multi_tenant_school_management.models import SchoolMembership, User
from database.multi_tenant_school_management.schemas.user import UserLogin, UserRead, UserUpdate
from database.session import get_db
from utils.auth.password_hash_verify import hash_password, verify_password
from utils.auth.tokens import authenticate_user, get_current_user
from utils.central_auth import project_platform_owner, require_central_claims, validate_central_access_token
from utils.school_context import (
    SCHOOL_WORKSPACE_COOKIE,
    SchoolContext,
    get_school_context,
    require_school_roles,
)


router = APIRouter(prefix="/auth", tags=["Auth"])


class LegacyLinkRequest(BaseModel):
    email: EmailStr
    password: str


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _cookie_kwargs(max_age: int) -> dict[str, object]:
    return {
        "max_age": max_age,
        "httponly": True,
        "secure": settings.AUTH_COOKIE_SECURE,
        "samesite": settings.AUTH_COOKIE_SAMESITE,
        "path": "/",
    }


def _set_session_cookies(response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        settings.AUTH_ACCESS_COOKIE_NAME,
        access_token,
        **_cookie_kwargs(60 * 15),
    )
    response.set_cookie(
        settings.AUTH_REFRESH_COOKIE_NAME,
        refresh_token,
        **_cookie_kwargs(settings.AUTH_COOKIE_MAX_AGE_SECONDS),
    )


def _clear_session_cookies(response) -> None:
    for name in (
        settings.AUTH_ACCESS_COOKIE_NAME,
        settings.AUTH_REFRESH_COOKIE_NAME,
        settings.AUTH_OIDC_STATE_COOKIE_NAME,
        settings.AUTH_OIDC_NONCE_COOKIE_NAME,
        settings.AUTH_OIDC_VERIFIER_COOKIE_NAME,
        SCHOOL_WORKSPACE_COOKIE,
    ):
        response.delete_cookie(name, path="/")


def _role_value(user: User) -> str:
    return getattr(user.role, "value", str(user.role))


def _membership_for_school(
    db: Session,
    user_id: uuid.UUID,
    school_id: uuid.UUID,
) -> SchoolMembership | None:
    return (
        db.query(SchoolMembership)
        .filter(
            SchoolMembership.user_id == user_id,
            SchoolMembership.school_id == school_id,
            SchoolMembership.is_active.is_(True),
        )
        .first()
    )


def _user_belongs_to_school(db: Session, user: User, school_id: uuid.UUID) -> bool:
    return user.school_id == school_id or _membership_for_school(db, user.id, school_id) is not None


@router.get("/oidc/login")
def oidc_login() -> RedirectResponse:
    verifier = secrets.token_urlsafe(64)[:96]
    state_value = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.AUTH_AUDIENCE,
            "redirect_uri": settings.AUTH_OIDC_REDIRECT_URI,
            "code_challenge": _pkce_challenge(verifier),
            "code_challenge_method": "S256",
            "scope": "openid profile email phone",
            "state": state_value,
            "nonce": nonce,
        }
    )
    response = RedirectResponse(f"{settings.auth_authorization_url}?{query}", status_code=303)
    short_cookie = _cookie_kwargs(600)
    response.set_cookie(settings.AUTH_OIDC_STATE_COOKIE_NAME, state_value, **short_cookie)
    response.set_cookie(settings.AUTH_OIDC_NONCE_COOKIE_NAME, nonce, **short_cookie)
    response.set_cookie(settings.AUTH_OIDC_VERIFIER_COOKIE_NAME, verifier, **short_cookie)
    return response


@router.get("/oidc/callback")
def oidc_callback(
    request: Request,
    code: str = Query(..., min_length=1),
    state_value: str = Query(..., alias="state", min_length=1),
    db: Session = Depends(get_db),
):
    expected_state = request.cookies.get(settings.AUTH_OIDC_STATE_COOKIE_NAME)
    nonce = request.cookies.get(settings.AUTH_OIDC_NONCE_COOKIE_NAME)
    verifier = request.cookies.get(settings.AUTH_OIDC_VERIFIER_COOKIE_NAME)
    if not expected_state or not nonce or not verifier or not secrets.compare_digest(expected_state, state_value):
        raise HTTPException(status_code=400, detail="invalid OIDC state")

    try:
        token_response = httpx.post(
            settings.auth_token_url,
            data={
                "grant_type": "authorization_code",
                "client_id": settings.AUTH_AUDIENCE,
                "code": code,
                "redirect_uri": settings.AUTH_OIDC_REDIRECT_URI,
                "code_verifier": verifier,
            },
            timeout=10.0,
        )
        token_response.raise_for_status()
        token_data = token_response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="central Auth token exchange failed") from exc

    access_token = str(token_data.get("access_token") or "")
    refresh_token = str(token_data.get("refresh_token") or "")
    id_token = str(token_data.get("id_token") or "")
    if not access_token or not refresh_token or not id_token:
        raise HTTPException(status_code=502, detail="central Auth returned an incomplete token response")

    claims = validate_central_access_token(access_token)
    try:
        signing_key = jwt.PyJWKClient(settings.auth_jwks_url).get_signing_key_from_jwt(id_token).key
        id_claims = jwt.decode(
            id_token,
            signing_key,
            algorithms=["RS256"],
            issuer=settings.auth_issuer,
            audience=settings.AUTH_AUDIENCE,
            options={"require": ["exp", "iss", "aud", "sub", "nonce"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="invalid central Auth ID token") from exc

    if id_claims.get("nonce") != nonce or id_claims.get("sub") != claims.get("sub"):
        raise HTTPException(status_code=401, detail="central Auth OIDC validation failed")

    subject = uuid.UUID(str(claims["sub"]))
    if claims.get("is_platform_admin") is True:
        linked_user = project_platform_owner(db, claims)
    else:
        linked_user = db.query(User).filter(User.auth_user_id == subject).first()

    if linked_user is None:
        destination = "/login?link_required=1"
    elif claims.get("is_platform_admin") is True:
        destination = "/dashboard"
    else:
        has_membership = (
            db.query(SchoolMembership)
            .filter(
                SchoolMembership.user_id == linked_user.id,
                SchoolMembership.is_active.is_(True),
            )
            .first()
            is not None
        )
        destination = "/dashboard" if has_membership or linked_user.school_id is not None else "/onboarding/school"

    response = RedirectResponse(f"{settings.TUTOR_FRONTEND_URL.rstrip('/')}{destination}", status_code=303)
    _set_session_cookies(response, access_token, refresh_token)
    for name in (
        settings.AUTH_OIDC_STATE_COOKIE_NAME,
        settings.AUTH_OIDC_NONCE_COOKIE_NAME,
        settings.AUTH_OIDC_VERIFIER_COOKIE_NAME,
    ):
        response.delete_cookie(name, path="/")
    return response


@router.post("/link-central")
def link_existing_tutor_profile(
    payload: LegacyLinkRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Link only after proving control of both central and legacy identities."""
    claims = require_central_claims(request)
    subject = uuid.UUID(str(claims["sub"]))

    existing_subject = db.query(User).filter(User.auth_user_id == subject).first()
    if existing_subject is not None:
        return {"linked": True, "user_id": str(existing_subject.id)}

    user = db.query(User).filter(User.email == str(payload.email).strip().lower()).first()
    if user is None or not user.password or not verify_password(payload.password, str(user.password)):
        raise HTTPException(status_code=401, detail="legacy Tutor credentials are invalid")
    if user.auth_user_id is not None and user.auth_user_id != subject:
        raise HTTPException(status_code=409, detail="Tutor profile is already linked to another !thute account")

    user.auth_user_id = subject
    db.commit()
    return {"linked": True, "user_id": str(user.id), "auth_user_id": str(subject)}


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/refresh")
def refresh(request: Request):
    refresh_token = request.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
    if not refresh_token:
        raise HTTPException(status_code=401, detail="missing central refresh token")

    try:
        auth_response = httpx.post(
            settings.auth_refresh_url,
            json={"client_id": settings.AUTH_AUDIENCE, "refresh_token": refresh_token},
            timeout=10.0,
        )
        auth_response.raise_for_status()
        token_data = auth_response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="central Auth session expired") from exc

    access_token = str(token_data.get("access_token") or "")
    new_refresh = str(token_data.get("refresh_token") or "")
    if not access_token or not new_refresh:
        raise HTTPException(status_code=502, detail="central Auth refresh response incomplete")

    validate_central_access_token(access_token)
    response = JSONResponse({"access_token": access_token, "token_type": "bearer"})
    _set_session_cookies(response, access_token, new_refresh)
    return response


@router.post("/logout")
def logout(request: Request):
    refresh_token = request.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
    if refresh_token:
        try:
            httpx.post(
                settings.auth_logout_url,
                json={"refresh_token": refresh_token},
                timeout=5.0,
            )
        except httpx.HTTPError:
            pass
    response = JSONResponse({"message": "Logged out successfully"})
    _clear_session_cookies(response)
    return response


@router.post("/login")
def legacy_login(payload: UserLogin, db: Session = Depends(get_db)):
    if not settings.LEGACY_AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Tutor local login is disabled; use central !thute Auth",
        )

    user = db.query(User).filter(User.email == payload.email).first()
    if user is None or not user.password or not verify_password(payload.password, str(user.password)):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {
        "access_token": authenticate_user(user),
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "channel": user.channel,
            "email": user.email,
            "name": user.username,
            "role": user.role,
            "school_id": str(user.school_id) if user.school_id else None,
        },
    }


@router.get("/users", response_model=list[UserRead])
def get_users(
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(
        require_school_roles(
            "school_admin",
            "principal",
            "vice_principal",
            "registrar",
            "hr_manager",
            "ict_manager",
            "system_administrator",
        )
    ),
):
    user_ids = [
        row[0]
        for row in db.query(SchoolMembership.user_id)
        .filter(
            SchoolMembership.school_id == context.school_id,
            SchoolMembership.is_active.is_(True),
        )
        .all()
    ]
    query = db.query(User)
    if user_ids:
        query = query.filter(User.id.in_(user_ids))
    else:
        query = query.filter(User.school_id == context.school_id)
    return query.order_by(User.username.asc()).all()


@router.get("/users/{user_id}", response_model=UserRead)
def get_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    context: SchoolContext = Depends(get_school_context),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id != current_user.id and not _user_belongs_to_school(db, user, context.school_id):
        raise HTTPException(status_code=404, detail="User not found in this school")
    return user


@router.put("/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(
        require_school_roles("school_admin", "principal", "hr_manager", "system_administrator")
    ),
):
    user = db.get(User, user_id)
    if user is None or not _user_belongs_to_school(db, user, context.school_id):
        raise HTTPException(status_code=404, detail="User not found in this school")

    update_data = payload.model_dump(exclude_unset=True)
    if "password" in update_data:
        if not settings.LEGACY_AUTH_ENABLED:
            raise HTTPException(status_code=400, detail="local Tutor passwords are migration-only")
        update_data["password"] = hash_password(update_data["password"])

    if "email" in update_data and user.auth_user_id is not None and update_data["email"] != user.email:
        raise HTTPException(status_code=400, detail="central account email is managed by !thute Auth")

    for key, value in update_data.items():
        setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}")
def remove_user_from_school(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles("school_admin", "principal", "system_administrator")),
):
    user = db.get(User, user_id)
    if user is None or not _user_belongs_to_school(db, user, context.school_id):
        raise HTTPException(status_code=404, detail="User not found in this school")

    if user.id == context.user_id and not context.is_platform_admin:
        raise HTTPException(status_code=400, detail="You cannot remove your own active school membership")

    membership = _membership_for_school(db, user.id, context.school_id)
    if membership is not None:
        membership.is_active = False
        membership.is_default = False

    if user.school_id == context.school_id:
        replacement = (
            db.query(SchoolMembership)
            .filter(
                SchoolMembership.user_id == user.id,
                SchoolMembership.school_id != context.school_id,
                SchoolMembership.is_active.is_(True),
            )
            .order_by(SchoolMembership.is_default.desc(), SchoolMembership.created_at.asc())
            .first()
        )
        user.school_id = replacement.school_id if replacement is not None else None

    db.commit()
    return {
        "message": "User removed from this school workspace",
        "user_id": str(user.id),
        "school_id": str(context.school_id),
    }
