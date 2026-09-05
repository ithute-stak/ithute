from __future__ import annotations

import hmac
import html
import string
import uuid
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import jwt
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .db import get_db
from .models import Application, AuthSession, AuthorizationCode, User, utcnow
from .schemas import TokenResponse
from .security import (
    create_access_token,
    create_browser_session_token,
    create_id_token,
    decode_browser_session_token,
    hash_authorization_code,
    hash_refresh_token,
    new_authorization_code,
    new_refresh_token,
    normalize_email,
    normalize_phone,
    pkce_s256,
    verify_password,
)
from .security_service import client_ip, login_rate_limited, record_audit, verify_second_factor


router = APIRouter(tags=["oauth"])
_ALLOWED_SCOPES = {"openid", "profile", "email", "phone"}
_PKCE_CHARS = frozenset(string.ascii_letters + string.digits + "-._~")


def _valid_pkce_value(value: str) -> bool:
    return 43 <= len(value) <= 128 and all(ch in _PKCE_CHARS for ch in value)


def _require_client_redirect(db: Session, settings: Settings, client_id: str, redirect_uri: str) -> Application:
    client = db.scalar(
        select(Application).where(
            Application.client_id == client_id,
            Application.is_active.is_(True),
        )
    )
    if client is None:
        raise HTTPException(status_code=400, detail="invalid_client")
    if redirect_uri not in settings.redirect_uris.get(client_id, ()):
        raise HTTPException(status_code=400, detail="invalid_redirect_uri")
    return client


def _validate_authorization_request(
    *,
    db: Session,
    settings: Settings,
    response_type: str,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    code_challenge_method: str,
    scope: str,
    state: str,
    nonce: str,
) -> str:
    _require_client_redirect(db, settings, client_id, redirect_uri)
    if response_type != "code":
        raise HTTPException(status_code=400, detail="unsupported_response_type")
    if code_challenge_method != "S256":
        raise HTTPException(status_code=400, detail="code_challenge_method_must_be_S256")
    if not _valid_pkce_value(code_challenge):
        raise HTTPException(status_code=400, detail="invalid_code_challenge")
    if not state or len(state) > 512:
        raise HTTPException(status_code=400, detail="state_required")
    if not 16 <= len(nonce) <= 512:
        raise HTTPException(status_code=400, detail="nonce_required")
    requested = [value for value in scope.split() if value]
    if not requested:
        requested = ["openid"]
    if "openid" not in requested or any(value not in _ALLOWED_SCOPES for value in requested):
        raise HTTPException(status_code=400, detail="invalid_scope")
    return " ".join(dict.fromkeys(requested))


def _redirect_with_code(redirect_uri: str, code: str, state: str) -> str:
    parts = urlsplit(redirect_uri)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query.extend([("code", code), ("state", state)])
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _issue_authorization_code(
    *,
    db: Session,
    settings: Settings,
    user: User,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    nonce: str,
    scope: str,
) -> str:
    raw_code = new_authorization_code()
    db.add(
        AuthorizationCode(
            code_hash=hash_authorization_code(raw_code),
            user_id=user.id,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            nonce=nonce,
            scope=scope,
            expires_at=utcnow() + timedelta(minutes=settings.authorization_code_minutes),
        )
    )
    db.commit()
    return raw_code


def _browser_user(request: Request, db: Session, settings: Settings) -> User | None:
    raw = request.cookies.get(settings.browser_cookie_name)
    if not raw:
        return None
    try:
        claims = decode_browser_session_token(raw, settings)
        user_id = uuid.UUID(str(claims["sub"]))
        security_version = int(claims["sv"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active or user.security_version != security_version:
        return None
    return user


def _login_html(fields: dict[str, str]) -> str:
    hidden = "\n".join(
        f'<input type="hidden" name="{html.escape(key)}" value="{html.escape(value, quote=True)}">'
        for key, value in fields.items()
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Sign in to !thute</title>
  <style>
    body{{font-family:system-ui,sans-serif;max-width:420px;margin:8vh auto;padding:24px;color:#17202a}}
    form{{display:grid;gap:14px}} label{{display:grid;gap:6px;font-weight:600}}
    input{{padding:11px 12px;border:1px solid #c9d1d9;border-radius:8px;font:inherit}}
    button{{padding:11px;border:0;border-radius:8px;background:#111827;color:white;font:inherit;font-weight:700;cursor:pointer}}
    p{{color:#5b6573}} small{{color:#6b7280;font-weight:400}}
  </style>
</head>
<body>
  <h1>Sign in to !thute</h1>
  <p>Use your central Ithute account to continue.</p>
  <form method="post" action="/oauth/authorize">
    {hidden}
    <label>Email or phone<input name="identifier" autocomplete="username" required></label>
    <label>Password<input type="password" name="password" autocomplete="current-password" required></label>
    <label>Authenticator or recovery code <small>Required only when MFA is enabled</small><input name="mfa_code" inputmode="numeric" autocomplete="one-time-code"></label>
    <button type="submit">Continue</button>
  </form>
</body>
</html>"""


@router.get("/oauth/authorize")
def authorize_get(
    request: Request,
    response_type: str = Query(...),
    client_id: str = Query(..., min_length=1, max_length=120),
    redirect_uri: str = Query(..., min_length=1, max_length=2048),
    code_challenge: str = Query(..., min_length=43, max_length=128),
    code_challenge_method: str = Query(...),
    state: str = Query(..., min_length=1, max_length=512),
    nonce: str = Query(..., min_length=16, max_length=512),
    scope: str = Query(default="openid profile email phone", max_length=512),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    normalized_scope = _validate_authorization_request(
        db=db,
        settings=settings,
        response_type=response_type,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        scope=scope,
        state=state,
        nonce=nonce,
    )
    user = _browser_user(request, db, settings)
    if user is not None:
        code = _issue_authorization_code(
            db=db,
            settings=settings,
            user=user,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            nonce=nonce,
            scope=normalized_scope,
        )
        return RedirectResponse(_redirect_with_code(redirect_uri, code, state), status_code=303)

    return HTMLResponse(
        _login_html(
            {
                "response_type": response_type,
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "code_challenge": code_challenge,
                "code_challenge_method": code_challenge_method,
                "state": state,
                "nonce": nonce,
                "scope": normalized_scope,
            }
        )
    )


@router.post("/oauth/authorize")
def authorize_post(
    request: Request,
    response_type: str = Form(...),
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    code_challenge: str = Form(...),
    code_challenge_method: str = Form(...),
    state: str = Form(...),
    nonce: str = Form(...),
    scope: str = Form(default="openid profile email phone"),
    identifier: str = Form(...),
    password: str = Form(...),
    mfa_code: str = Form(default=""),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    normalized_scope = _validate_authorization_request(
        db=db,
        settings=settings,
        response_type=response_type,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        scope=scope,
        state=state,
        nonce=nonce,
    )
    if login_rate_limited(db, request=request, settings=settings):
        record_audit(db, event_type="oidc_login_rate_limited", success=False, client_id=client_id, request=request)
        db.commit()
        raise HTTPException(status_code=429, detail="too_many_login_attempts")

    email = normalize_email(identifier)
    phone = normalize_phone(identifier)
    user = db.scalar(
        select(User).where(
            or_(User.email == email, User.phone == phone),
            User.is_active.is_(True),
        )
    )
    now = utcnow()
    if user is None:
        record_audit(db, event_type="oidc_login_failed", success=False, client_id=client_id, request=request)
        db.commit()
        raise HTTPException(status_code=401, detail="invalid_credentials")
    if user.locked_until is not None and user.locked_until > now:
        record_audit(db, event_type="oidc_login_blocked", user=user, success=False, client_id=client_id, request=request)
        db.commit()
        raise HTTPException(status_code=401, detail="invalid_credentials")
    if not verify_password(password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.max_login_failures:
            user.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
        record_audit(
            db,
            event_type="oidc_login_failed",
            user=user,
            success=False,
            client_id=client_id,
            request=request,
            details={"failed_attempts": user.failed_login_attempts},
        )
        db.commit()
        raise HTTPException(status_code=401, detail="invalid_credentials")
    if not verify_second_factor(db, user=user, code=mfa_code or None, settings=settings):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.max_login_failures:
            user.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
        record_audit(
            db,
            event_type="oidc_mfa_failed",
            user=user,
            success=False,
            client_id=client_id,
            request=request,
            details={"failed_attempts": user.failed_login_attempts},
        )
        db.commit()
        raise HTTPException(status_code=401, detail="mfa_required_or_invalid")

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    user.last_login_ip = client_ip(request)
    record_audit(db, event_type="oidc_login_succeeded", user=user, client_id=client_id, request=request)
    code = _issue_authorization_code(
        db=db,
        settings=settings,
        user=user,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        nonce=nonce,
        scope=normalized_scope,
    )
    response = RedirectResponse(_redirect_with_code(redirect_uri, code, state), status_code=303)
    response.set_cookie(
        settings.browser_cookie_name,
        create_browser_session_token(
            settings=settings,
            user_id=user.id,
            security_version=user.security_version,
        ),
        max_age=settings.browser_session_hours * 3600,
        httponly=True,
        secure=settings.browser_cookie_secure,
        samesite="lax",
        path="/",
    )
    return response


@router.post("/oauth/token", response_model=TokenResponse)
def token(
    request: Request,
    grant_type: str = Form(...),
    client_id: str = Form(...),
    code: str | None = Form(default=None),
    redirect_uri: str | None = Form(default=None),
    code_verifier: str | None = Form(default=None),
    refresh_token: str | None = Form(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    client = db.scalar(
        select(Application).where(
            Application.client_id == client_id,
            Application.is_active.is_(True),
        )
    )
    if client is None:
        raise HTTPException(status_code=400, detail="invalid_client")

    if grant_type == "authorization_code":
        if not code or not redirect_uri or not code_verifier:
            raise HTTPException(status_code=400, detail="invalid_request")
        _require_client_redirect(db, settings, client_id, redirect_uri)
        if not _valid_pkce_value(code_verifier):
            raise HTTPException(status_code=400, detail="invalid_code_verifier")
        row = db.scalar(
            select(AuthorizationCode)
            .where(AuthorizationCode.code_hash == hash_authorization_code(code))
            .with_for_update()
        )
        now = utcnow()
        if (
            row is None
            or row.client_id != client_id
            or row.redirect_uri != redirect_uri
            or row.consumed_at is not None
            or row.expires_at <= now
        ):
            raise HTTPException(status_code=400, detail="invalid_grant")
        if not hmac.compare_digest(pkce_s256(code_verifier), row.code_challenge):
            raise HTTPException(status_code=400, detail="invalid_grant")
        user = db.get(User, row.user_id)
        if user is None or not user.is_active:
            raise HTTPException(status_code=400, detail="invalid_grant")
        row.consumed_at = now
        raw_refresh = new_refresh_token()
        session = AuthSession(
            user_id=user.id,
            client_id=client_id,
            refresh_token_hash=hash_refresh_token(raw_refresh),
            user_agent=request.headers.get("user-agent"),
            ip_address=client_ip(request),
            expires_at=now + timedelta(days=settings.refresh_token_days),
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        access = create_access_token(
            settings=settings,
            user_id=user.id,
            client_id=client_id,
            session_id=session.id,
            email=user.email,
            phone=user.phone,
        )
        id_token = create_id_token(
            settings=settings,
            user_id=user.id,
            client_id=client_id,
            session_id=session.id,
            nonce=row.nonce,
            email=user.email,
            phone=user.phone,
            display_name=user.display_name,
            email_verified=user.email_verified,
            phone_verified=user.phone_verified,
        )
        return TokenResponse(
            access_token=access,
            refresh_token=raw_refresh,
            id_token=id_token,
            expires_in=settings.access_token_minutes * 60,
        )

    if grant_type == "refresh_token":
        if not refresh_token:
            raise HTTPException(status_code=400, detail="invalid_request")
        row = db.scalar(
            select(AuthSession)
            .where(AuthSession.refresh_token_hash == hash_refresh_token(refresh_token))
            .with_for_update()
        )
        now = utcnow()
        if (
            row is None
            or row.client_id != client_id
            or row.revoked_at is not None
            or row.expires_at <= now
        ):
            raise HTTPException(status_code=400, detail="invalid_grant")
        user = db.get(User, row.user_id)
        if user is None or not user.is_active:
            raise HTTPException(status_code=400, detail="invalid_grant")
        new_refresh = new_refresh_token()
        row.refresh_token_hash = hash_refresh_token(new_refresh)
        row.last_seen_at = now
        db.commit()
        access = create_access_token(
            settings=settings,
            user_id=user.id,
            client_id=client_id,
            session_id=row.id,
            email=user.email,
            phone=user.phone,
        )
        return TokenResponse(
            access_token=access,
            refresh_token=new_refresh,
            expires_in=settings.access_token_minutes * 60,
        )

    raise HTTPException(status_code=400, detail="unsupported_grant_type")


@router.post("/oauth/browser-logout", status_code=204)
def browser_logout(response: Response, settings: Settings = Depends(get_settings)) -> None:
    response.delete_cookie(settings.browser_cookie_name, path="/")
