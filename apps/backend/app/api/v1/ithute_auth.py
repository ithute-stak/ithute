import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from urllib.parse import urlencode
from uuid import UUID

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import central_user_from_claims, get_current_local_user, get_current_user
from app.core.config import settings
from app.core.security import verify_password
from app.db.session import get_db
from app.models import AuditLog, User
from app.services.ithute_auth import (
    IthuteAuthDisabled,
    IthuteAuthUnavailable,
    decode_ithute_access_token,
    get_ithute_auth_settings,
    ithute_auth_enabled,
)

router = APIRouter(prefix="/auth/ithute", tags=["auth"])
_SSO_STATE_COOKIE = "mdns_ithute_oauth_state"
_SSO_VERIFIER_COOKIE = "mdns_ithute_oauth_verifier"
_SSO_NONCE_COOKIE = "mdns_ithute_oauth_nonce"
_SSO_TTL_SECONDS = 600


class IthuteLinkRequest(BaseModel):
    access_token: str = Field(min_length=100, max_length=8192)
    current_password: str = Field(min_length=6, max_length=256)


class IthuteUnlinkRequest(BaseModel):
    current_password: str = Field(min_length=6, max_length=256)


def _request_is_https(request: Request) -> bool:
    scheme = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower() or request.url.scheme.lower()
    return scheme == "https"


def _cookie_options(request: Request) -> dict:
    return {
        "httponly": True,
        "secure": settings.cookie_secure or _request_is_https(request),
        "samesite": "lax",
        "path": "/",
    }


def _redirect_uri() -> str:
    return f"{settings.frontend_url.rstrip('/')}/api/v1/auth/ithute/callback"


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _set_central_session_cookies(
    response: Response,
    request: Request,
    *,
    access_token: str,
    refresh_token: str,
    expires_in: int,
) -> None:
    common = _cookie_options(request)
    response.set_cookie(settings.access_cookie_name, access_token, max_age=max(60, expires_in), **common)
    response.set_cookie(settings.refresh_cookie_name, refresh_token, max_age=30 * 86400, **common)


@router.get("/login")
def central_login(request: Request):
    if not ithute_auth_enabled():
        raise HTTPException(status_code=503, detail="!thute Auth is not enabled for Mailbox DNS")

    config = get_ithute_auth_settings()
    verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    params = urlencode(
        {
            "response_type": "code",
            "client_id": config.audience,
            "redirect_uri": _redirect_uri(),
            "code_challenge": _pkce_challenge(verifier),
            "code_challenge_method": "S256",
            "state": state,
            "nonce": nonce,
            "scope": "openid profile email phone",
        }
    )
    response = RedirectResponse(f"{config.resolved_issuer}/oauth/authorize?{params}", status_code=303)
    temporary = {**_cookie_options(request), "max_age": _SSO_TTL_SECONDS}
    response.set_cookie(_SSO_STATE_COOKIE, state, **temporary)
    response.set_cookie(_SSO_VERIFIER_COOKIE, verifier, **temporary)
    response.set_cookie(_SSO_NONCE_COOKIE, nonce, **temporary)
    return response


@router.get("/callback")
async def central_callback(
    request: Request,
    code: str,
    state: str,
    db: Session = Depends(get_db),
):
    expected_state = request.cookies.get(_SSO_STATE_COOKIE) or ""
    verifier = request.cookies.get(_SSO_VERIFIER_COOKIE) or ""
    if not expected_state or not verifier or not hmac.compare_digest(expected_state, state):
        raise HTTPException(status_code=400, detail="Central sign-in state is invalid or expired")

    config = get_ithute_auth_settings()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_response = await client.post(
                f"{config.resolved_internal_url}/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": config.audience,
                    "code": code,
                    "redirect_uri": _redirect_uri(),
                    "code_verifier": verifier,
                },
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="!thute Auth token exchange is unavailable") from exc
    if token_response.status_code != 200:
        raise HTTPException(status_code=401, detail="Central sign-in could not be completed")

    payload = token_response.json()
    access_token = str(payload.get("access_token") or "")
    refresh_token = str(payload.get("refresh_token") or "")
    if not access_token or not refresh_token:
        raise HTTPException(status_code=502, detail="!thute Auth returned an incomplete session")
    try:
        claims = decode_ithute_access_token(access_token)
    except (IthuteAuthDisabled, IthuteAuthUnavailable, jwt.InvalidTokenError) as exc:
        raise HTTPException(status_code=401, detail="Invalid central sign-in session") from exc
    central_user_from_claims(claims, db)

    response = RedirectResponse(f"{settings.frontend_url.rstrip('/')}/dashboard", status_code=303)
    _set_central_session_cookies(
        response,
        request,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=int(payload.get("expires_in") or 600),
    )
    for name in (_SSO_STATE_COOKIE, _SSO_VERIFIER_COOKIE, _SSO_NONCE_COOKIE):
        response.delete_cookie(name, path="/")
    return response


@router.post("/refresh")
async def central_refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    raw_refresh = request.cookies.get(settings.refresh_cookie_name)
    if not raw_refresh:
        raise HTTPException(status_code=401, detail="Central refresh token required")
    config = get_ithute_auth_settings()
    if not config.enabled:
        raise HTTPException(status_code=401, detail="Central authentication is disabled")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_response = await client.post(
                f"{config.resolved_internal_url}/oauth/token",
                data={
                    "grant_type": "refresh_token",
                    "client_id": config.audience,
                    "refresh_token": raw_refresh,
                },
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="!thute Auth refresh is unavailable") from exc
    if token_response.status_code != 200:
        raise HTTPException(status_code=401, detail="Central session expired or revoked")

    payload = token_response.json()
    access_token = str(payload.get("access_token") or "")
    refresh_token = str(payload.get("refresh_token") or "")
    try:
        claims = decode_ithute_access_token(access_token)
    except (IthuteAuthDisabled, IthuteAuthUnavailable, jwt.InvalidTokenError) as exc:
        raise HTTPException(status_code=401, detail="Invalid refreshed central session") from exc
    central_user_from_claims(claims, db)
    _set_central_session_cookies(
        response,
        request,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=int(payload.get("expires_in") or 600),
    )
    return {"refreshed": True}


@router.get("/status")
def status_view(current: User = Depends(get_current_user)):
    return {
        "enabled": ithute_auth_enabled(),
        "linked": current.auth_user_id is not None,
        "auth_user_id": str(current.auth_user_id) if current.auth_user_id else None,
    }


@router.post("/link")
def link_account(
    payload: IthuteLinkRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_local_user),
):
    if not verify_password(payload.current_password, current.password_hash):
        raise HTTPException(status_code=400, detail="Current Mailbox DNS password is incorrect")

    try:
        claims = decode_ithute_access_token(payload.access_token)
    except IthuteAuthDisabled as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="!thute Auth is not enabled for Mailbox DNS",
        ) from exc
    except IthuteAuthUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="!thute Auth verification is temporarily unavailable",
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid !thute Auth token") from exc

    central_subject = UUID(str(claims["sub"]))
    other = db.scalar(
        select(User).where(
            User.auth_user_id == central_subject,
            User.id != current.id,
        )
    )
    if other is not None:
        raise HTTPException(
            status_code=409,
            detail="This !thute account is already linked to another Mailbox DNS user",
        )
    if current.auth_user_id and current.auth_user_id != central_subject:
        raise HTTPException(
            status_code=409,
            detail="This Mailbox DNS user is already linked to a different !thute account",
        )

    current.auth_user_id = central_subject
    db.add(
        AuditLog(
            actor_user_id=current.id,
            action="auth.ithute.link",
            resource_type="user",
            resource_id=str(current.id),
        )
    )
    db.commit()
    return {
        "linked": True,
        "auth_user_id": str(central_subject),
        "message": "!thute account linked. Existing Mailbox DNS login remains available during migration.",
    }


@router.post("/unlink")
def unlink_account(
    payload: IthuteUnlinkRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_local_user),
):
    if not verify_password(payload.current_password, current.password_hash):
        raise HTTPException(status_code=400, detail="Current Mailbox DNS password is incorrect")
    if current.auth_user_id is None:
        return {"linked": False, "message": "No !thute account is linked."}

    previous = str(current.auth_user_id)
    current.auth_user_id = None
    db.add(
        AuditLog(
            actor_user_id=current.id,
            action="auth.ithute.unlink",
            resource_type="user",
            resource_id=str(current.id),
            metadata_json=f'{{"previous_auth_user_id":"{previous}"}}',
        )
    )
    db.commit()
    return {
        "linked": False,
        "message": "!thute account unlinked. Existing Mailbox DNS login remains available.",
    }
