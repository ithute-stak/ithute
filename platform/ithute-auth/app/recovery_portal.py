from __future__ import annotations

import hmac
import html
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .db import get_db
from .delivery import DeliveryUnavailable, send_email, send_sms
from .models import SecurityToken, User, utcnow
from .security import (
    hash_password,
    hash_security_token,
    new_security_token,
    normalize_email,
    normalize_phone,
)
from .security_service import record_audit, recovery_request_rate_limited, revoke_sessions


router = APIRouter(tags=["recovery-portal"])
_RECOVERY_CSRF_COOKIE = "ithute_recovery_csrf"
_RESET_TOKEN_COOKIE = "ithute_reset_token"


_STYLE = """
:root{--ink:#10233d;--muted:#607087;--line:#dfe6ee;--brand:#1f5eff;--bad:#b42318}*{box-sizing:border-box}body{margin:0;background:#f4f7fb;color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.wrap{min-height:100vh;display:grid;place-items:center;padding:24px}.card{width:min(480px,100%);background:#fff;border:1px solid var(--line);border-radius:18px;padding:24px;box-shadow:0 8px 28px rgba(16,35,61,.06)}h1{margin-top:0}p{color:var(--muted);line-height:1.55}form{display:grid;gap:11px}label{font-size:13px;font-weight:700}input{width:100%;padding:11px 12px;border:1px solid #cfd8e3;border-radius:10px;font:inherit}button,.button{border:0;border-radius:10px;padding:11px 14px;background:var(--brand);color:#fff;font-weight:750;cursor:pointer;text-decoration:none;text-align:center}.notice{padding:12px 14px;border-radius:10px;background:#eef5ff;border:1px solid #cfe0ff;margin-bottom:16px}.error{background:#fff0ef;border-color:#ffc9c5;color:var(--bad)}a{color:var(--brand);text-decoration:none}.small{font-size:12px;color:var(--muted)}
"""


def _e(value: object | None) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _page(title: str, body: str) -> HTMLResponse:
    response = HTMLResponse(
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><title>{_e(title)} · !thute</title><style>{_STYLE}</style></head><body><div class="wrap"><div class="card">{body}</div></div></body></html>'
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


def _new_csrf_response(response: HTMLResponse, settings: Settings) -> HTMLResponse:
    token = secrets.token_urlsafe(32)
    response.set_cookie(
        _RECOVERY_CSRF_COOKIE,
        token,
        max_age=600,
        httponly=True,
        secure=settings.browser_cookie_secure,
        samesite="strict",
        path="/",
    )
    response.body = response.body.replace(b"__RECOVERY_CSRF__", token.encode("ascii"))
    response.headers["content-length"] = str(len(response.body))
    return response


def _require_csrf(request: Request, submitted: str) -> None:
    expected = request.cookies.get(_RECOVERY_CSRF_COOKIE, "")
    if not expected or not hmac.compare_digest(expected, submitted):
        raise HTTPException(status_code=403, detail="invalid CSRF token")


def _find_user(db: Session, identifier: str) -> User | None:
    email = normalize_email(identifier)
    phone = normalize_phone(identifier)
    return db.scalar(select(User).where(or_(User.email == email, User.phone == phone)))


def _consume_active_reset_tokens(db: Session, user: User) -> None:
    rows = db.scalars(
        select(SecurityToken).where(
            SecurityToken.user_id == user.id,
            SecurityToken.purpose == "password_reset",
            SecurityToken.consumed_at.is_(None),
        )
    ).all()
    now = utcnow()
    for row in rows:
        row.consumed_at = now


def _deliver_reset(settings: Settings, user: User, token: str) -> None:
    link = f"{settings.account_base_url.rstrip('/')}/reset-password?token={token}"
    if user.email:
        send_email(
            settings,
            recipient=user.email,
            subject="Reset your !thute password",
            body=f"Use this secure link to reset your !thute password:\n\n{link}\n\nIf you did not request this, ignore this message.",
        )
        return
    if user.phone:
        send_sms(settings, phone=user.phone, message=f"!thute password reset: {link}")
        return
    raise DeliveryUnavailable("user has no recovery channel")


@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_get(settings: Settings = Depends(get_settings)) -> HTMLResponse:
    body = """
      <h1>Reset your password</h1>
      <p>Enter the email address or phone number on your central !thute account.</p>
      <form method="post" action="/forgot-password">
        <input type="hidden" name="csrf_token" value="__RECOVERY_CSRF__">
        <label>Email or phone</label>
        <input name="identifier" autocomplete="username" required>
        <button type="submit">Send reset instructions</button>
      </form>
      <p class="small"><a href="/account/login">Back to sign in</a></p>
    """
    return _new_csrf_response(_page("Forgot password", body), settings)


@router.post("/forgot-password", response_class=HTMLResponse)
def forgot_password_post(
    request: Request,
    identifier: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    _require_csrf(request, csrf_token)
    user = _find_user(db, identifier)
    limited = recovery_request_rate_limited(db, request=request, user=user, settings=settings)
    if limited:
        record_audit(db, event_type="password_reset_rate_limited", user=user, success=False, request=request)
        db.commit()
    else:
        record_audit(db, event_type="password_reset_requested", user=user, request=request)
        if user is not None and user.is_active:
            _consume_active_reset_tokens(db, user)
            raw = new_security_token()
            row = SecurityToken(
                user_id=user.id,
                purpose="password_reset",
                token_hash=hash_security_token(raw),
                target=user.email or user.phone,
                expires_at=utcnow() + timedelta(minutes=settings.password_reset_minutes),
            )
            db.add(row)
            db.commit()
            try:
                _deliver_reset(settings, user, raw)
            except Exception:
                row.consumed_at = utcnow()
                record_audit(db, event_type="password_reset_delivery", user=user, success=False, request=request)
                db.commit()
        else:
            db.commit()

    response = _page(
        "Check your messages",
        '<h1>Check your messages</h1><div class="notice">If that account can be recovered, reset instructions have been sent.</div><p><a href="/account/login">Return to sign in</a></p>',
    )
    response.delete_cookie(_RECOVERY_CSRF_COOKIE, path="/")
    return response


@router.get("/reset-password", response_class=HTMLResponse)
def reset_password_get(
    request: Request,
    token: str | None = None,
    settings: Settings = Depends(get_settings),
):
    if token:
        if not 20 <= len(token) <= 512:
            return _page("Invalid reset link", '<h1>Reset link unavailable</h1><div class="notice error">This reset link is invalid.</div><p><a href="/forgot-password">Request a new link</a></p>')
        response = RedirectResponse("/reset-password", status_code=303)
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.set_cookie(
            _RESET_TOKEN_COOKIE,
            token,
            max_age=settings.password_reset_minutes * 60,
            httponly=True,
            secure=settings.browser_cookie_secure,
            samesite="strict",
            path="/reset-password",
        )
        return response

    if not request.cookies.get(_RESET_TOKEN_COOKIE):
        return _page("Reset link unavailable", '<h1>Reset link unavailable</h1><div class="notice error">Request a new password reset link to continue.</div><p><a href="/forgot-password">Request a new link</a></p>')

    body = """
      <h1>Choose a new password</h1>
      <p>Your new password must contain at least 10 characters. Completing this reset signs the account out of all existing product sessions.</p>
      <form method="post" action="/reset-password">
        <input type="hidden" name="csrf_token" value="__RECOVERY_CSRF__">
        <label>New password</label>
        <input type="password" name="new_password" minlength="10" maxlength="128" autocomplete="new-password" required>
        <label>Confirm new password</label>
        <input type="password" name="confirm_password" minlength="10" maxlength="128" autocomplete="new-password" required>
        <button type="submit">Reset password</button>
      </form>
    """
    return _new_csrf_response(_page("Choose a new password", body), settings)


@router.post("/reset-password")
def reset_password_post(
    request: Request,
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    _require_csrf(request, csrf_token)
    raw = request.cookies.get(_RESET_TOKEN_COOKIE, "")
    if not raw or not 20 <= len(raw) <= 512:
        raise HTTPException(status_code=400, detail="invalid or expired reset token")
    if new_password != confirm_password:
        raise HTTPException(status_code=400, detail="passwords do not match")
    if not 10 <= len(new_password) <= 128:
        raise HTTPException(status_code=400, detail="new password must be 10-128 characters")

    row = db.scalar(
        select(SecurityToken)
        .where(
            SecurityToken.token_hash == hash_security_token(raw),
            SecurityToken.purpose == "password_reset",
        )
        .with_for_update()
    )
    if row is None or row.consumed_at is not None or row.expires_at <= utcnow():
        raise HTTPException(status_code=400, detail="invalid or expired reset token")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail="invalid or expired reset token")

    row.consumed_at = utcnow()
    user.password_hash = hash_password(new_password)
    user.password_changed_at = utcnow()
    user.security_version += 1
    user.failed_login_attempts = 0
    user.locked_until = None
    revoke_sessions(db, user_id=user.id, reason="password reset")
    record_audit(db, event_type="password_reset_completed", user=user, request=request)
    db.commit()

    response = RedirectResponse("/account/login?changed=1", status_code=303)
    response.delete_cookie(_RESET_TOKEN_COOKIE, path="/reset-password")
    response.delete_cookie(_RECOVERY_CSRF_COOKIE, path="/")
    response.delete_cookie(settings.browser_cookie_name, path="/")
    return response
