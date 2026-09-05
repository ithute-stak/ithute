from __future__ import annotations

import secrets
import time
from typing import Any
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_platform_owner
from app.core.config import settings as app_settings
from app.db.session import get_db
from app.models import AuditLog, User
from app.services.ithute_auth import decode_ithute_access_token
from app.services.ithute_platform_admin import (
    auth_request,
    authorization_url,
    exchange_code,
    get_platform_admin_settings,
    pkce_pair,
    push_request,
    sign_step_up_state,
    validate_admin_access_token,
    validate_id_token,
    verify_step_up_state,
)


router = APIRouter(prefix="/platform/ithute", tags=["ithute-platform-admin"])
_UNLINKED = "unlinked"


class AdminUserUpdate(BaseModel):
    is_active: bool | None = None
    unlock: bool = False


class AdminApplicationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    is_active: bool | None = None


def _secure_request(request: Request) -> bool:
    if app_settings.environment.strip().lower() == "production" or app_settings.cookie_secure:
        return True
    scheme = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower() or request.url.scheme.lower()
    return scheme == "https"


def _linked_owner(current: User) -> str:
    if current.auth_user_id is None:
        raise HTTPException(status_code=403, detail="Central !thute identity is not linked to this platform owner")
    return str(current.auth_user_id)


def _upstream(response, *, service: str) -> Any:
    if response.status_code in {401, 403}:
        raise HTTPException(status_code=401, detail=f"{service} admin elevation expired or was revoked")
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"{service} administration is temporarily unavailable")
    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"{service} returned an invalid administration response") from exc


def _elevated_token(request: Request, current: User) -> str:
    cfg = get_platform_admin_settings()
    expected_sub = _linked_owner(current)
    token = request.cookies.get(cfg.admin_cookie_name)
    if not token:
        raise HTTPException(status_code=401, detail="Central !thute admin step-up required")
    try:
        validate_admin_access_token(token, expected_sub=expected_sub)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Central !thute admin step-up expired or invalid") from exc

    proof = auth_request("GET", "/v1/admin/overview", token=token)
    if proof.status_code != 200:
        raise HTTPException(status_code=401, detail="Central !thute platform-admin permission is required")
    return token


@router.get("/admin/status")
def admin_status(
    request: Request,
    current: User = Depends(require_platform_owner),
) -> dict[str, object]:
    linked = current.auth_user_id is not None
    if not linked:
        return {"platform_owner": True, "linked": False, "elevated": False, "bootstrap_link_available": True}
    try:
        token = _elevated_token(request, current)
        overview = _upstream(auth_request("GET", "/v1/admin/overview", token=token), service="!thute Auth")
        return {
            "platform_owner": True,
            "linked": True,
            "elevated": True,
            "bootstrap_link_available": False,
            "central_admin": overview.get("admin") if isinstance(overview, dict) else None,
        }
    except HTTPException:
        return {"platform_owner": True, "linked": True, "elevated": False, "bootstrap_link_available": False}


@router.get("/admin/login")
def admin_login(
    request: Request,
    current: User = Depends(require_platform_owner),
):
    auth_user_id = str(current.auth_user_id) if current.auth_user_id is not None else _UNLINKED
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier, challenge = pkce_pair()
    signed = sign_step_up_state(
        local_user_id=str(current.id),
        auth_user_id=auth_user_id,
        state=state,
        nonce=nonce,
        verifier=verifier,
    )
    response = RedirectResponse(authorization_url(state=state, nonce=nonce, challenge=challenge), status_code=303)
    cfg = get_platform_admin_settings()
    response.set_cookie(
        cfg.state_cookie_name,
        signed,
        max_age=min(max(cfg.step_up_seconds, 120), 900),
        httponly=True,
        secure=_secure_request(request),
        samesite="lax",
        path="/api/v1/platform/ithute/admin",
    )
    return response


@router.get("/admin/callback")
def admin_callback(
    request: Request,
    code: str = Query(..., min_length=16, max_length=1024),
    state: str = Query(..., min_length=16, max_length=512),
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    cfg = get_platform_admin_settings()
    signed = request.cookies.get(cfg.state_cookie_name)
    if not signed:
        raise HTTPException(status_code=400, detail="Central admin authorization state is missing")
    try:
        pending = verify_step_up_state(signed)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not secrets.compare_digest(pending["state"], state):
        raise HTTPException(status_code=400, detail="Central admin authorization state does not match")
    if pending["local_user_id"] != str(current.id):
        raise HTTPException(status_code=403, detail="Central admin authorization belongs to a different panel session")
    if current.auth_user_id is not None and pending["auth_user_id"] != str(current.auth_user_id):
        raise HTTPException(status_code=403, detail="Central admin identity binding changed during authorization")
    if current.auth_user_id is None and pending["auth_user_id"] != _UNLINKED:
        raise HTTPException(status_code=403, detail="Central admin bootstrap state is invalid")

    try:
        tokens = exchange_code(code=code, verifier=pending["verifier"])
        access_token = str(tokens["access_token"])
        access_claims = (
            validate_admin_access_token(access_token, expected_sub=pending["auth_user_id"])
            if pending["auth_user_id"] != _UNLINKED
            else decode_ithute_access_token(access_token)
        )
        central_sub = str(access_claims["sub"])
        id_token = tokens.get("id_token")
        if not isinstance(id_token, str):
            raise jwt.InvalidTokenError("central id token missing")
        id_claims = validate_id_token(id_token, nonce=pending["nonce"])
        if not secrets.compare_digest(str(id_claims.get("sub", "")), central_sub):
            raise jwt.InvalidTokenError("central access and identity token subjects differ")
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Central !thute admin step-up failed") from exc

    proof = auth_request("GET", "/v1/admin/overview", token=access_token)
    if proof.status_code != 200:
        raise HTTPException(status_code=403, detail="This central !thute account is not a platform admin")

    if current.auth_user_id is None:
        central_uuid = UUID(central_sub)
        existing = db.scalar(select(User).where(User.auth_user_id == central_uuid, User.id != current.id))
        if existing is not None:
            raise HTTPException(status_code=409, detail="This central !thute admin is already linked to another panel account")
        current.auth_user_id = central_uuid
        db.add(
            AuditLog(
                actor_user_id=current.id,
                action="ithute.platform_admin.bootstrap_link",
                resource_type="user",
                resource_id=str(current.id),
                metadata_json=f'{{"auth_user_id":"{central_sub}"}}',
            )
        )
        db.commit()
    elif str(current.auth_user_id) != central_sub:
        raise HTTPException(status_code=403, detail="Central admin identity does not match this platform owner")

    remaining = max(1, int(access_claims["exp"]) - int(time.time()))
    max_age = min(remaining, max(120, cfg.step_up_seconds))
    response = RedirectResponse(f"{cfg.panel_return_url}?admin=ready", status_code=303)
    response.delete_cookie(cfg.state_cookie_name, path="/api/v1/platform/ithute/admin")
    response.set_cookie(
        cfg.admin_cookie_name,
        access_token,
        max_age=max_age,
        httponly=True,
        secure=_secure_request(request),
        samesite="lax",
        path="/api/v1/platform/ithute",
    )
    return response


@router.post("/admin/logout", status_code=204)
def admin_logout(
    current: User = Depends(require_platform_owner),
):
    _ = current
    from fastapi import Response

    response = Response(status_code=204)
    cfg = get_platform_admin_settings()
    response.delete_cookie(cfg.admin_cookie_name, path="/api/v1/platform/ithute")
    return response


@router.get("/overview")
def combined_overview(
    request: Request,
    current: User = Depends(require_platform_owner),
) -> dict[str, object]:
    token = _elevated_token(request, current)
    auth = _upstream(auth_request("GET", "/v1/admin/overview", token=token), service="!thute Auth")
    push = _upstream(push_request("GET", "/v1/admin/overview", central_access_token=token), service="!thute Push")
    return {"auth": auth, "push": push}


@router.get("/auth/users")
def auth_users(
    request: Request,
    q: str | None = Query(default=None, max_length=160),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current: User = Depends(require_platform_owner),
):
    token = _elevated_token(request, current)
    params: dict[str, object] = {"limit": limit, "offset": offset}
    if q:
        params["q"] = q
    return _upstream(auth_request("GET", "/v1/admin/users", token=token, params=params), service="!thute Auth")


@router.patch("/auth/users/{user_id}")
def update_auth_user(
    user_id: str,
    payload: AdminUserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    token = _elevated_token(request, current)
    result = _upstream(
        auth_request("PATCH", f"/v1/admin/users/{user_id}", token=token, json_body=payload.model_dump()),
        service="!thute Auth",
    )
    db.add(AuditLog(actor_user_id=current.id, action="ithute.auth.admin.user.update", resource_type="auth_user", resource_id=user_id))
    db.commit()
    return result


@router.post("/auth/users/{user_id}/revoke-sessions")
def revoke_auth_user_sessions(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    token = _elevated_token(request, current)
    result = _upstream(auth_request("POST", f"/v1/admin/users/{user_id}/revoke-sessions", token=token), service="!thute Auth")
    db.add(AuditLog(actor_user_id=current.id, action="ithute.auth.admin.sessions.revoke", resource_type="auth_user", resource_id=user_id))
    db.commit()
    return result


@router.get("/auth/applications")
def auth_applications(
    request: Request,
    current: User = Depends(require_platform_owner),
):
    token = _elevated_token(request, current)
    return _upstream(auth_request("GET", "/v1/admin/applications", token=token), service="!thute Auth")


@router.patch("/auth/applications/{client_id}")
def update_auth_application(
    client_id: str,
    payload: AdminApplicationUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    token = _elevated_token(request, current)
    result = _upstream(
        auth_request("PATCH", f"/v1/admin/applications/{client_id}", token=token, json_body=payload.model_dump(exclude_none=True)),
        service="!thute Auth",
    )
    db.add(AuditLog(actor_user_id=current.id, action="ithute.auth.admin.application.update", resource_type="auth_application", resource_id=client_id))
    db.commit()
    return result


@router.get("/push/applications")
def push_applications(
    request: Request,
    current: User = Depends(require_platform_owner),
):
    token = _elevated_token(request, current)
    return _upstream(push_request("GET", "/v1/admin/applications", central_access_token=token), service="!thute Push")


@router.get("/push/messages")
def push_messages(
    request: Request,
    limit: int = Query(default=25, ge=1, le=100),
    current: User = Depends(require_platform_owner),
):
    token = _elevated_token(request, current)
    return _upstream(push_request("GET", f"/v1/admin/messages?limit={limit}", central_access_token=token), service="!thute Push")
