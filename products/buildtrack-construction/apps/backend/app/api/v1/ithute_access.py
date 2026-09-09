from __future__ import annotations

import base64
import hashlib
import secrets
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models import Company, Role, User, UserRoleAssignment
from app.security.access import (
    SESSION_COOKIE,
    create_session,
    hash_password,
    security_policy,
    token_hash,
    utcnow,
)

router = APIRouter(prefix="/access", tags=["Ithute Platform Identity"])
settings = get_settings()


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _cookie_kwargs(max_age: int) -> dict[str, object]:
    return {
        "max_age": max_age,
        "httponly": True,
        "secure": settings.auth_cookie_secure,
        "samesite": settings.auth_cookie_samesite,
        "path": "/",
    }


def _no_store(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return response


def _safe_return_to(value: str | None) -> str:
    if not value or not value.startswith("/") or value.startswith("//"):
        return "/"
    return value[:2048]


def _new_oidc_challenge(return_to: str | None) -> tuple[str, str, str, dict[str, str]]:
    verifier = secrets.token_urlsafe(64)[:96]
    state_value = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    fields = {
        "response_type": "code",
        "client_id": settings.auth_audience,
        "redirect_uri": settings.auth_oidc_redirect_uri,
        "code_challenge": _pkce_challenge(verifier),
        "code_challenge_method": "S256",
        "scope": "openid profile email phone",
        "state": state_value,
        "nonce": nonce,
    }
    return verifier, state_value, nonce, fields


def _set_oidc_challenge_cookies(
    response,
    *,
    verifier: str,
    state_value: str,
    nonce: str,
    return_to: str | None,
) -> None:
    short_cookie = _cookie_kwargs(600)
    response.set_cookie(settings.auth_oidc_state_cookie_name, state_value, **short_cookie)
    response.set_cookie(settings.auth_oidc_nonce_cookie_name, nonce, **short_cookie)
    response.set_cookie(settings.auth_oidc_verifier_cookie_name, verifier, **short_cookie)
    response.set_cookie(settings.auth_oidc_return_cookie_name, _safe_return_to(return_to), **short_cookie)


def _validate_access_token(token: str) -> dict[str, object]:
    try:
        signing_key = jwt.PyJWKClient(settings.auth_jwks_url).get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            issuer=settings.auth_issuer.rstrip("/"),
            audience=settings.auth_audience,
            options={"require": ["exp", "iss", "aud", "sub", "token_use"]},
        )
    except (jwt.PyJWTError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="invalid central Ithute Auth access token") from exc
    if claims.get("token_use") != "access":
        raise HTTPException(status_code=401, detail="invalid central Ithute Auth token type")
    return claims


def _ensure_product_identity(
    db: Session,
    *,
    claims: dict[str, object],
    display_name: str | None,
) -> User:
    subject = str(claims.get("sub") or "").strip()
    email = str(claims.get("email") or "").strip().lower()
    if not subject or not email:
        raise HTTPException(status_code=401, detail="central Ithute identity is missing subject or email")

    company = db.scalar(select(Company).order_by(Company.id).limit(1))
    if company is None:
        raise HTTPException(status_code=503, detail="Nthane Brothers product bootstrap is incomplete")

    user = db.scalar(select(User).where(User.company_id == company.id, User.auth_user_id == subject))
    if user is None:
        user = db.scalar(select(User).where(User.company_id == company.id, User.email == email))

    is_product_superadmin = email == settings.superadmin_email.strip().lower()
    if user is None and not is_product_superadmin:
        raise HTTPException(
            status_code=403,
            detail="Your Ithute account is valid but has not been assigned access to Nthane Brothers",
        )

    if user is None:
        # This password is intentionally random and unreachable. Production login
        # is central OIDC; the local column remains only for backwards-compatible
        # schema support while legacy authentication is disabled.
        user = User(
            company_id=company.id,
            username=email.split("@", 1)[0][:80],
            email=email,
            auth_user_id=subject,
            full_name=(display_name or email).strip()[:255],
            password_hash=hash_password(secrets.token_urlsafe(48)),
            must_change_password=False,
            status="active",
            is_active=True,
            created_by="Ithute Auth federation",
        )
        db.add(user)
        db.flush()
    elif user.auth_user_id is None:
        user.auth_user_id = subject
    elif user.auth_user_id != subject:
        raise HTTPException(status_code=409, detail="BuildTrack profile is linked to another Ithute identity")

    if not user.is_active or user.status == "suspended":
        if not is_product_superadmin:
            raise HTTPException(status_code=403, detail="BuildTrack access is suspended")
        user.is_active = True
        user.status = "active"

    if is_product_superadmin:
        role = db.scalar(select(Role).where(Role.company_id == company.id, Role.code == "SYSTEM_ADMIN"))
        if role is None:
            raise HTTPException(status_code=503, detail="BuildTrack System Administrator role is missing")
        assignment = db.scalar(
            select(UserRoleAssignment).where(
                UserRoleAssignment.user_id == user.id,
                UserRoleAssignment.role_id == role.id,
            )
        )
        if assignment is None:
            db.add(
                UserRoleAssignment(
                    user_id=user.id,
                    role_id=role.id,
                    is_primary=True,
                    created_by="Ithute product superadmin projection",
                )
            )
        user.must_change_password = False

    return user


def _set_central_cookies(response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(settings.auth_access_cookie_name, access_token, **_cookie_kwargs(15 * 60))
    response.set_cookie(
        settings.auth_refresh_cookie_name,
        refresh_token,
        **_cookie_kwargs(settings.auth_cookie_max_age_seconds),
    )


def _clear_cookies(response) -> None:
    for name in (
        SESSION_COOKIE,
        settings.auth_access_cookie_name,
        settings.auth_refresh_cookie_name,
        settings.auth_oidc_state_cookie_name,
        settings.auth_oidc_nonce_cookie_name,
        settings.auth_oidc_verifier_cookie_name,
        settings.auth_oidc_return_cookie_name,
    ):
        response.delete_cookie(
            name,
            path="/",
            secure=settings.auth_cookie_secure,
            samesite=settings.auth_cookie_samesite,
        )


@router.get("/oidc/login")
def oidc_login(
    return_to: str | None = Query(default=None, alias="returnTo", max_length=2048),
) -> RedirectResponse:
    verifier, state_value, nonce, fields = _new_oidc_challenge(return_to)
    response = RedirectResponse(f"{settings.auth_authorization_url}?{urlencode(fields)}", status_code=303)
    _set_oidc_challenge_cookies(
        response,
        verifier=verifier,
        state_value=state_value,
        nonce=nonce,
        return_to=return_to,
    )
    return _no_store(response)


@router.get("/oidc/manual-challenge")
def oidc_manual_challenge(
    return_to: str | None = Query(default=None, alias="returnTo", max_length=2048),
):
    """Prepare a PKCE-bound direct credential form for central Ithute Auth.

    BuildTrack never receives the email/password/MFA values. The browser posts
    them directly to the central Ithute Auth authorization endpoint, which then
    returns the normal authorization code to BuildTrack's OIDC callback.
    """
    verifier, state_value, nonce, fields = _new_oidc_challenge(return_to)
    response = JSONResponse(
        {
            "action": settings.auth_authorization_url,
            "method": "post",
            "fields": fields,
        }
    )
    _set_oidc_challenge_cookies(
        response,
        verifier=verifier,
        state_value=state_value,
        nonce=nonce,
        return_to=return_to,
    )
    return _no_store(response)


@router.get("/oidc/callback")
def oidc_callback(
    request: Request,
    code: str = Query(..., min_length=1),
    state_value: str = Query(..., alias="state", min_length=1),
    db: Session = Depends(get_db),
):
    expected_state = request.cookies.get(settings.auth_oidc_state_cookie_name)
    nonce = request.cookies.get(settings.auth_oidc_nonce_cookie_name)
    verifier = request.cookies.get(settings.auth_oidc_verifier_cookie_name)
    if not expected_state or not nonce or not verifier or not secrets.compare_digest(expected_state, state_value):
        raise HTTPException(status_code=400, detail="invalid OIDC state")

    try:
        token_response = httpx.post(
            settings.auth_token_url,
            data={
                "grant_type": "authorization_code",
                "client_id": settings.auth_audience,
                "code": code,
                "redirect_uri": settings.auth_oidc_redirect_uri,
                "code_verifier": verifier,
            },
            timeout=10.0,
        )
        token_response.raise_for_status()
        token_data = token_response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="central Ithute Auth token exchange failed") from exc

    access_token = str(token_data.get("access_token") or "")
    refresh_token = str(token_data.get("refresh_token") or "")
    id_token = str(token_data.get("id_token") or "")
    if not access_token or not refresh_token or not id_token:
        raise HTTPException(status_code=502, detail="central Ithute Auth returned an incomplete token response")

    claims = _validate_access_token(access_token)
    try:
        signing_key = jwt.PyJWKClient(settings.auth_jwks_url).get_signing_key_from_jwt(id_token).key
        id_claims = jwt.decode(
            id_token,
            signing_key,
            algorithms=["RS256"],
            issuer=settings.auth_issuer.rstrip("/"),
            audience=settings.auth_audience,
            options={"require": ["exp", "iss", "aud", "sub", "nonce"]},
        )
    except (jwt.PyJWTError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="invalid central Ithute Auth ID token") from exc

    if id_claims.get("nonce") != nonce or str(id_claims.get("sub")) != str(claims.get("sub")):
        raise HTTPException(status_code=401, detail="central Ithute OIDC validation failed")

    user = _ensure_product_identity(
        db,
        claims=claims,
        display_name=str(id_claims.get("name") or claims.get("email") or ""),
    )
    user.last_login_at = utcnow()
    user.failed_login_attempts = 0
    user.locked_until = None
    product_session, raw_token = create_session(db, user, request)
    db.commit()

    return_to = _safe_return_to(request.cookies.get(settings.auth_oidc_return_cookie_name))
    response = RedirectResponse(return_to, status_code=303)
    policy = security_policy(db, user.company_id)
    response.set_cookie(
        SESSION_COOKIE,
        raw_token,
        max_age=int(policy["session_hours"]) * 3600,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        path="/",
    )
    _set_central_cookies(response, access_token, refresh_token)
    for name in (
        settings.auth_oidc_state_cookie_name,
        settings.auth_oidc_nonce_cookie_name,
        settings.auth_oidc_verifier_cookie_name,
        settings.auth_oidc_return_cookie_name,
    ):
        response.delete_cookie(name, path="/")
    response.headers["X-BuildTrack-Session"] = str(product_session.id)
    return _no_store(response)


@router.post("/central-refresh")
def central_refresh(request: Request):
    refresh_token = request.cookies.get(settings.auth_refresh_cookie_name)
    if not refresh_token:
        response = JSONResponse({"detail": "central Ithute session has ended"}, status_code=401)
        _clear_cookies(response)
        return _no_store(response)

    try:
        auth_response = httpx.post(
            settings.auth_refresh_url,
            json={"client_id": settings.auth_audience, "refresh_token": refresh_token},
            timeout=10.0,
        )
    except httpx.RequestError:
        response = JSONResponse(
            {"detail": "central Ithute Auth is temporarily unavailable"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        response.headers["Retry-After"] = "5"
        return _no_store(response)

    if auth_response.status_code in (400, 401, 403):
        response = JSONResponse({"detail": "central Ithute session expired"}, status_code=401)
        _clear_cookies(response)
        return _no_store(response)
    if auth_response.status_code >= 500:
        response = JSONResponse({"detail": "central Ithute Auth is temporarily unavailable"}, status_code=503)
        response.headers["Retry-After"] = "5"
        return _no_store(response)
    if not 200 <= auth_response.status_code < 300:
        return _no_store(JSONResponse({"detail": "central Ithute Auth refresh failed"}, status_code=502))

    try:
        token_data = auth_response.json()
    except ValueError:
        return _no_store(JSONResponse({"detail": "invalid central Ithute Auth refresh response"}, status_code=502))
    access_token = str(token_data.get("access_token") or "")
    new_refresh = str(token_data.get("refresh_token") or "")
    if not access_token or not new_refresh:
        return _no_store(JSONResponse({"detail": "incomplete central Ithute Auth refresh response"}, status_code=502))
    _validate_access_token(access_token)

    response = JSONResponse({"refreshed": True})
    _set_central_cookies(response, access_token, new_refresh)
    return _no_store(response)


@router.post("/central-logout")
def central_logout(request: Request, db: Session = Depends(get_db)):
    refresh_token = request.cookies.get(settings.auth_refresh_cookie_name)
    if refresh_token:
        try:
            httpx.post(settings.auth_logout_url, json={"refresh_token": refresh_token}, timeout=5.0)
        except httpx.HTTPError:
            pass

    raw_session = request.cookies.get(SESSION_COOKIE)
    if raw_session:
        from app.models import UserSession

        product_session = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash(raw_session)))
        if product_session and product_session.revoked_at is None:
            product_session.revoked_at = utcnow()
            product_session.revoked_by = "Ithute Auth logout"
            product_session.revoke_reason = "Central identity logout"
            db.commit()

    response = JSONResponse({"message": "Signed out"})
    _clear_cookies(response)
    return _no_store(response)


@router.get("/platform-status")
def platform_status() -> dict[str, object]:
    return {
        "identity_provider": "Ithute Auth",
        "issuer": settings.auth_issuer,
        "client_id": settings.auth_audience,
        "legacy_login_enabled": settings.legacy_auth_enabled,
        "product_superadmin": settings.superadmin_email,
        "push": bool(settings.push_base_url),
        "realtime": bool(settings.realtime_public_url),
    }
