from __future__ import annotations

import hashlib
import hmac
import html
import secrets
import uuid
from datetime import timedelta
from urllib.parse import quote

import jwt
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .db import get_db
from .delivery import send_email, send_sms
from .models import Application, AuditEvent, AuthSession, MfaRecoveryCode, SecurityToken, User, utcnow
from .security import (
    create_browser_session_token,
    decode_browser_session_token,
    decrypt_totp_secret,
    encrypt_totp_secret,
    hash_password,
    hash_recovery_code,
    hash_security_token,
    new_numeric_code,
    new_recovery_codes,
    new_totp_secret,
    normalize_email,
    normalize_phone,
    totp_provisioning_uri,
    verify_password,
    verify_totp,
)
from .security_service import (
    client_ip,
    login_rate_limited,
    record_audit,
    revoke_sessions,
    verification_confirmation_rate_limited,
    verification_request_rate_limited,
    verify_second_factor,
)


router = APIRouter(tags=["portal"])
_LOGIN_CSRF_COOKIE = "ithute_login_csrf"


_STYLE = """
:root{
  color-scheme:light;
  --ink:#10233d;--ink-soft:#203a5d;--muted:#66758a;--line:#dfe6ee;--line-strong:#cbd6e3;
  --canvas:#f4f7fb;--card:#fff;--soft:#f6f9fc;--soft-blue:#eef5ff;--brand:#1f5eff;--brand-dark:#1748c9;
  --good:#137a4e;--good-bg:#eaf8f1;--warn:#9b5b00;--warn-bg:#fff7e8;--bad:#b42318;--bad-bg:#fff1f0;
  --shadow:0 12px 36px rgba(16,35,61,.07);
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  margin:0;background:var(--canvas);color:var(--ink);
  font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  -webkit-font-smoothing:antialiased;
}
a{color:var(--brand);text-decoration:none}
a:hover{text-decoration:underline}
.shell{max-width:1180px;margin:0 auto;padding:24px}
.topbar{
  position:sticky;top:0;z-index:10;display:flex;align-items:center;justify-content:space-between;gap:16px;
  padding:12px 0 20px;background:linear-gradient(180deg,var(--canvas) 74%,rgba(244,247,251,0));
}
.brand{display:flex;align-items:center;gap:10px;font-weight:850;font-size:20px;letter-spacing:-.025em}
.brand-mark{width:34px;height:34px;border-radius:11px;background:var(--brand);display:grid;place-items:center;color:#fff;font-weight:900;box-shadow:0 7px 18px rgba(31,94,255,.22)}
.nav{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.nav-link{padding:8px 11px;border-radius:9px;color:var(--ink-soft);font-weight:700;font-size:14px}
.nav-link:hover{background:#e9eff7;text-decoration:none}
.card{
  background:var(--card);border:1px solid var(--line);border-radius:18px;padding:22px;
  box-shadow:var(--shadow);
}
.grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:18px}
.col-3{grid-column:span 3}.col-4{grid-column:span 4}.col-5{grid-column:span 5}.col-6{grid-column:span 6}.col-7{grid-column:span 7}.col-8{grid-column:span 8}.col-9{grid-column:span 9}.col-12{grid-column:span 12}
.hero{
  display:flex;justify-content:space-between;align-items:flex-start;gap:22px;padding:8px 2px 20px;
}
.eyebrow{font-size:12px;text-transform:uppercase;letter-spacing:.12em;color:var(--brand);font-weight:850;margin-bottom:8px}
h1,h2,h3{margin:0;letter-spacing:-.025em;color:var(--ink)}
h1{font-size:clamp(28px,4vw,38px);line-height:1.08}
h2{font-size:20px}
h3{font-size:16px}
p{color:var(--muted);line-height:1.6;margin:8px 0 0}
.hero p{font-size:15px;max-width:680px}
.id-card{min-width:320px;max-width:420px}
.id-value{margin-top:9px;display:block}
.metric{font-size:28px;font-weight:850;letter-spacing:-.04em}
.label{font-size:11px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);font-weight:800}
.value{font-size:16px;font-weight:800;margin-top:7px;overflow-wrap:anywhere}
.badge{
  display:inline-flex;align-items:center;gap:6px;padding:5px 9px;border-radius:999px;
  background:var(--soft);border:1px solid var(--line);font-size:12px;font-weight:800;line-height:1;
}
.badge::before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor;opacity:.8}
.good{color:var(--good);background:var(--good-bg);border-color:#ccebdc}
.warn{color:var(--warn);background:var(--warn-bg);border-color:#f0ddb7}
.bad{color:var(--bad);background:var(--bad-bg);border-color:#ffd4d0}
.neutral{color:var(--muted);background:var(--soft)}
.status-line{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:12px}
.section-head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;margin-bottom:16px}
.section-head p{margin-top:4px}
.contact-card{display:flex;flex-direction:column;min-height:180px}
.contact-card .contact-actions{margin-top:auto;padding-top:16px}
.security-card{min-height:100%}
.inline-form{display:inline-flex;gap:8px;align-items:center}
form{display:grid;gap:11px}
label{font-weight:750;font-size:13px;color:var(--ink-soft)}
.help{font-size:12px;color:var(--muted);margin-top:-4px}
input,select{
  width:100%;padding:11px 12px;border:1px solid var(--line-strong);border-radius:10px;
  background:#fff;color:var(--ink);font:inherit;outline:none;transition:border-color .15s,box-shadow .15s;
}
input:focus,select:focus{border-color:var(--brand);box-shadow:0 0 0 3px rgba(31,94,255,.12)}
input::placeholder{color:#94a0b0}
button,.button{
  border:0;border-radius:10px;padding:10px 14px;background:var(--brand);color:#fff;font-weight:800;
  cursor:pointer;display:inline-flex;justify-content:center;align-items:center;gap:7px;font:inherit;
  transition:transform .08s,background .15s,box-shadow .15s;
}
button:hover,.button:hover{background:var(--brand-dark);text-decoration:none;box-shadow:0 6px 16px rgba(31,94,255,.18)}
button:active,.button:active{transform:translateY(1px)}
.secondary{background:#eaf0f8;color:var(--ink)}
.secondary:hover{background:#dde7f3;box-shadow:none}
.ghost{background:#fff;color:var(--ink);border:1px solid var(--line-strong)}
.ghost:hover{background:var(--soft);box-shadow:none}
.danger{background:var(--bad)}
.danger:hover{background:#8f1c14;box-shadow:0 6px 16px rgba(180,35,24,.16)}
.actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.row{
  display:flex;justify-content:space-between;gap:18px;align-items:center;
  padding:15px 0;border-bottom:1px solid var(--line);
}
.row:last-child{border-bottom:0}
.row-main{min-width:0;flex:1}
.row-title{font-weight:800;color:var(--ink);display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.row-meta{font-size:12px;color:var(--muted);margin-top:4px;line-height:1.45;overflow-wrap:anywhere}
.row-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap;justify-content:flex-end}
.small{font-size:12px;color:var(--muted)}
.notice{padding:13px 15px;border-radius:12px;background:var(--soft-blue);border:1px solid #cfe0ff;margin:0 0 18px;color:var(--ink-soft);font-weight:650}
.error{background:var(--bad-bg);border-color:#ffc9c5;color:var(--bad)}
.callout{padding:14px;border-radius:12px;background:var(--soft);border:1px solid var(--line);font-size:13px;color:var(--muted);line-height:1.55}
.danger-zone{border-color:#f3c3bf;background:linear-gradient(180deg,#fff 0%,#fffafa 100%)}
.divider{height:1px;background:var(--line);margin:18px 0}
.stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:18px}
.stat{padding:14px;border-radius:14px;background:var(--soft);border:1px solid var(--line)}
.stat strong{display:block;font-size:19px;letter-spacing:-.02em;margin-top:4px}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:11px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
code{background:#eef2f7;padding:3px 7px;border-radius:7px;word-break:break-all;font-size:.92em}
.login-wrap{min-height:100vh;display:grid;place-items:center;padding:24px}
.login-card{width:min(470px,100%)}
.logo-mark{width:50px;height:50px;border-radius:15px;background:var(--brand);display:grid;place-items:center;color:#fff;font-weight:900;font-size:23px;margin-bottom:18px;box-shadow:0 10px 22px rgba(31,94,255,.23)}
.setup-card{max-width:760px;margin:28px auto}
.recovery-list{columns:2;gap:18px;padding-left:22px}
.recovery-list li{break-inside:avoid;margin:8px 0}
.empty{padding:20px 0;color:var(--muted);text-align:center}
@media(max-width:900px){
  .col-3,.col-4,.col-5,.col-6,.col-7,.col-8,.col-9{grid-column:span 12}
  .hero{display:block}.id-card{min-width:0;max-width:none;margin-top:18px}
}
@media(max-width:680px){
  .shell{padding:14px}.topbar{padding-top:6px}.brand{font-size:17px}.brand-mark{width:31px;height:31px}
  .card{padding:17px;border-radius:15px}.grid{gap:13px}.row{align-items:flex-start;flex-direction:column}
  .row-actions{justify-content:flex-start;width:100%}.section-head{flex-direction:column}
  .section-head form,.section-head button{width:100%}.stats{grid-template-columns:1fr}
  .nav{gap:3px}.nav-link{padding:7px 8px}.recovery-list{columns:1}
}
"""


def _e(value: object | None) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _fmt(value) -> str:
    if value is None:
        return "—"
    try:
        return value.astimezone().strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(value)


def _page(title: str, body: str, *, user: User | None = None) -> str:
    nav = ""
    if user is not None:
        admin = '<a class="nav-link" href="/admin">Admin</a>' if user.is_platform_admin else ""
        nav = (
            '<div class="nav">'
            '<a class="nav-link" href="/account">Account</a>'
            '<a class="nav-link" href="/account/passkeys">Passkeys</a>'
            f"{admin}"
            '<form method="post" action="/account/logout" style="display:inline">'
            '<button class="secondary" type="submit">Sign out</button>'
            "</form></div>"
        )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{_e(title)} · !thute</title><style>{_STYLE}</style></head>"
        '<body><div class="shell"><div class="topbar">'
        '<div class="brand"><div class="brand-mark">!</div><span>thute Identity</span></div>'
        f"{nav}</div>{body}</div></body></html>"
    )


def _login_page(*, csrf_token: str, error: str | None = None, notice: str | None = None) -> str:
    error_html = f'<div class="notice error">{_e(error)}</div>' if error else ""
    notice_html = f'<div class="notice">{_e(notice)}</div>' if notice else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sign in · !thute</title><style>{_STYLE}</style></head><body><div class="login-wrap"><div class="card login-card"><div class="logo-mark">!</div><div class="eyebrow">Ithute Identity</div><h1>Sign in securely</h1><p>One central identity for Ithute products.</p><div style="height:16px"></div>{notice_html}{error_html}<form method="post" action="/account/login"><input type="hidden" name="csrf_token" value="{_e(csrf_token)}"><label>Email or phone</label><input name="identifier" autocomplete="username" placeholder="you@ithute.co.ls" required><label>Password</label><input type="password" name="password" autocomplete="current-password" required><label>Authenticator or recovery code <span class="small">(if MFA is enabled)</span></label><input name="mfa_code" autocomplete="one-time-code"><button type="submit">Continue</button></form><div class="actions" style="margin-top:16px;justify-content:space-between"><a href="/forgot-password">Forgot password?</a><a href="/account/passkey-login">Use a passkey</a></div><div class="callout" style="margin-top:18px">Authentication is provided centrally by !thute Auth. Product roles and business permissions remain inside each Ithute product.</div></div></div></body></html>"""


def _cookie_user(request: Request, db: Session, settings: Settings) -> User | None:
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


def _portal_csrf(raw_cookie: str, settings: Settings) -> str:
    key = hashlib.sha256(("ithute-portal-csrf-v1\n" + settings.private_key).encode("utf-8")).digest()
    return hmac.new(key, raw_cookie.encode("utf-8"), hashlib.sha256).hexdigest()


def _require_portal_user(request: Request, db: Session, settings: Settings) -> tuple[User, str, str]:
    raw = request.cookies.get(settings.browser_cookie_name)
    user = _cookie_user(request, db, settings)
    if user is None or not raw:
        raise HTTPException(status_code=401, detail="sign in required")
    return user, raw, _portal_csrf(raw, settings)


def _require_csrf(request: Request, form_token: str, settings: Settings) -> None:
    raw = request.cookies.get(settings.browser_cookie_name)
    if not raw:
        raise HTTPException(status_code=401, detail="sign in required")
    expected = _portal_csrf(raw, settings)
    if not hmac.compare_digest(expected, form_token):
        raise HTTPException(status_code=403, detail="invalid CSRF token")


def _set_sso_cookie(response, user: User, settings: Settings) -> None:
    response.set_cookie(
        settings.browser_cookie_name,
        create_browser_session_token(settings=settings, user_id=user.id, security_version=user.security_version),
        max_age=settings.browser_session_hours * 3600,
        httponly=True,
        secure=settings.browser_cookie_secure,
        samesite="lax",
        path="/",
    )


def _new_login_response(page: str, token: str, settings: Settings, *, status_code: int = 200) -> HTMLResponse:
    response = HTMLResponse(page, status_code=status_code)
    response.set_cookie(
        _LOGIN_CSRF_COOKIE,
        token,
        max_age=600,
        httponly=True,
        secure=settings.browser_cookie_secure,
        samesite="strict",
        path="/account/login",
    )
    return response


def _mark_previous_tokens_consumed(db: Session, *, user_id: uuid.UUID, purpose: str) -> None:
    rows = db.scalars(
        select(SecurityToken).where(
            SecurityToken.user_id == user_id,
            SecurityToken.purpose == purpose,
            SecurityToken.consumed_at.is_(None),
        )
    ).all()
    now = utcnow()
    for row in rows:
        row.consumed_at = now


@router.get("/")
def portal_root() -> RedirectResponse:
    return RedirectResponse("/account", status_code=303)


@router.get("/account/login", response_class=HTMLResponse)
def portal_login_get(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    if _cookie_user(request, db, settings) is not None:
        return RedirectResponse("/account", status_code=303)
    token = secrets.token_urlsafe(32)
    notice = "Password updated. Sign in again." if request.query_params.get("changed") else None
    return _new_login_response(_login_page(csrf_token=token, notice=notice), token, settings)


@router.post("/account/login", response_class=HTMLResponse)
def portal_login_post(
    request: Request,
    identifier: str = Form(...),
    password: str = Form(...),
    mfa_code: str = Form(default=""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    cookie_token = request.cookies.get(_LOGIN_CSRF_COOKIE, "")
    if not cookie_token or not hmac.compare_digest(cookie_token, csrf_token):
        raise HTTPException(status_code=403, detail="invalid CSRF token")

    if login_rate_limited(db, request=request, settings=settings):
        record_audit(db, event_type="login_rate_limited", success=False, client_id="ithute-account", request=request)
        db.commit()
        token = secrets.token_urlsafe(32)
        return _new_login_response(
            _login_page(csrf_token=token, error="Too many login attempts. Try again later."),
            token,
            settings,
            status_code=429,
        )

    email = normalize_email(identifier)
    phone = normalize_phone(identifier)
    user = db.scalar(
        select(User).where(
            or_(User.email == email, User.phone == phone),
            User.is_active.is_(True),
        )
    )
    now = utcnow()
    valid = (
        user is not None
        and (user.locked_until is None or user.locked_until <= now)
        and verify_password(password, user.password_hash)
    )
    if not valid:
        if user is not None and (user.locked_until is None or user.locked_until <= now):
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= settings.max_login_failures:
                user.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
        record_audit(db, event_type="login_failed", user=user, success=False, client_id="ithute-account", request=request)
        db.commit()
        token = secrets.token_urlsafe(32)
        return _new_login_response(
            _login_page(csrf_token=token, error="Invalid sign-in details."),
            token,
            settings,
            status_code=401,
        )

    assert user is not None
    if not verify_second_factor(db, user=user, code=mfa_code or None, settings=settings):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.max_login_failures:
            user.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
        record_audit(db, event_type="mfa_challenge_failed", user=user, success=False, client_id="ithute-account", request=request)
        db.commit()
        token = secrets.token_urlsafe(32)
        return _new_login_response(
            _login_page(csrf_token=token, error="Authenticator or recovery code is required or invalid."),
            token,
            settings,
            status_code=401,
        )

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    user.last_login_ip = client_ip(request)
    record_audit(db, event_type="portal_login_succeeded", user=user, client_id="ithute-account", request=request)
    db.commit()
    response = RedirectResponse("/account", status_code=303)
    _set_sso_cookie(response, user, settings)
    response.delete_cookie(_LOGIN_CSRF_COOKIE, path="/account/login")
    return response


@router.post("/account/logout")
def portal_logout(settings: Settings = Depends(get_settings)) -> RedirectResponse:
    response = RedirectResponse("/account/login", status_code=303)
    response.delete_cookie(settings.browser_cookie_name, path="/")
    return response


@router.get("/account", response_class=HTMLResponse)
def account_home(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    user = _cookie_user(request, db, settings)
    if user is None:
        return RedirectResponse("/account/login", status_code=303)

    raw = request.cookies[settings.browser_cookie_name]
    csrf = _portal_csrf(raw, settings)
    sessions = db.scalars(
        select(AuthSession)
        .where(AuthSession.user_id == user.id)
        .order_by(AuthSession.created_at.desc())
        .limit(30)
    ).all()
    audits = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.user_id == user.id)
        .order_by(AuditEvent.created_at.desc())
        .limit(20)
    ).all()
    applications = db.scalars(select(Application)).all()
    app_names = {app.client_id: app.name for app in applications}

    active_sessions = sum(1 for row in sessions if row.revoked_at is None)
    successful_events = sum(1 for event in audits if event.success)
    last_security_event = _fmt(audits[0].created_at) if audits else "No activity yet"

    session_rows = "".join(
        (
            '<div class="row">'
            '<div class="row-main">'
            f'<div class="row-title">{_e(app_names.get(row.client_id, row.client_id))}'
            f' <span class="badge {"bad" if row.revoked_at else "good"}">{"Revoked" if row.revoked_at else "Active"}</span></div>'
            f'<div class="row-meta">{_e(row.client_id)} · {_e(row.ip_address or "unknown IP")} · last seen {_e(_fmt(row.last_seen_at))}</div>'
            f'<div class="row-meta">{_e((row.user_agent or "Unknown device")[:160])}</div>'
            "</div>"
            '<div class="row-actions">'
            + (
                ""
                if row.revoked_at
                else (
                    f'<form method="post" action="/account/sessions/{row.id}/revoke">'
                    f'<input type="hidden" name="csrf_token" value="{csrf}">'
                    '<button class="ghost" type="submit">Revoke session</button></form>'
                )
            )
            + "</div></div>"
        )
        for row in sessions
    ) or '<div class="empty">No product sessions yet.</div>'

    audit_rows = "".join(
        (
            '<div class="row"><div class="row-main">'
            f'<div class="row-title">{_e(event.event_type.replace("_", " ").title())}</div>'
            f'<div class="row-meta">{_e(_fmt(event.created_at))} · {_e(event.ip_address or "unknown IP")} · {_e(app_names.get(event.client_id, event.client_id or "central"))}</div>'
            f'</div><div class="row-actions"><span class="badge {"good" if event.success else "bad"}">{"Success" if event.success else "Failed"}</span></div></div>'
        )
        for event in audits
    ) or '<div class="empty">No security activity yet.</div>'

    def contact_state(value: str | None, verified: bool) -> str:
        if not value:
            return '<span class="badge neutral">Not set</span>'
        if verified:
            return '<span class="badge good">Verified</span>'
        return '<span class="badge warn">Verification needed</span>'

    email_state = contact_state(user.email, user.email_verified)
    phone_state = contact_state(user.phone, user.phone_verified)
    mfa_state = '<span class="badge good">Enabled</span>' if user.totp_enabled else '<span class="badge warn">Not enabled</span>'

    verify_email = ""
    if user.email and not user.email_verified:
        verify_email = (
            '<form method="post" action="/account/verification/request">'
            f'<input type="hidden" name="csrf_token" value="{csrf}">'
            '<input type="hidden" name="channel" value="email">'
            '<button class="secondary" type="submit">Send verification code</button></form>'
        )
    verify_phone = ""
    if user.phone and not user.phone_verified:
        verify_phone = (
            '<form method="post" action="/account/verification/request">'
            f'<input type="hidden" name="csrf_token" value="{csrf}">'
            '<input type="hidden" name="channel" value="phone">'
            '<button class="secondary" type="submit">Send verification code</button></form>'
        )

    available_channels: list[str] = []
    if user.email and not user.email_verified:
        available_channels.append('<option value="email">Email</option>')
    if user.phone and not user.phone_verified:
        available_channels.append('<option value="phone">Phone</option>')

    if available_channels:
        verification_panel = f"""
        <div class="card col-6 security-card">
          <div class="section-head"><div><h2>Confirm contact verification</h2><p>Enter the six-digit code sent to an unverified contact.</p></div></div>
          <form method="post" action="/account/verification/confirm">
            <input type="hidden" name="csrf_token" value="{csrf}">
            <label>Contact channel</label>
            <select name="channel">{"".join(available_channels)}</select>
            <label>Verification code</label>
            <input name="code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{{6}}" minlength="6" maxlength="6" placeholder="000000" required>
            <button type="submit">Verify contact</button>
          </form>
        </div>"""
    else:
        verification_panel = """
        <div class="card col-6 security-card">
          <div class="section-head"><div><h2>Contact verification</h2><p>Your configured recovery contacts do not need verification.</p></div></div>
          <div class="callout">Verified contact details help you recover access securely. Add or update contact information through the identity administration process when needed.</div>
        </div>"""

    if user.totp_enabled:
        mfa_controls = f"""
        <form method="post" action="/account/mfa/disable" onsubmit="return confirm('Disable multi-factor authentication for this account?');">
          <input type="hidden" name="csrf_token" value="{csrf}">
          <label>Current password</label>
          <input type="password" name="password" autocomplete="current-password" required>
          <label>Authenticator or recovery code</label>
          <input name="code" autocomplete="one-time-code" required>
          <button class="danger" type="submit">Disable MFA</button>
        </form>"""
    else:
        mfa_controls = f"""
        <form method="post" action="/account/mfa/start">
          <input type="hidden" name="csrf_token" value="{csrf}">
          <label>Current password</label>
          <input type="password" name="password" autocomplete="current-password" required>
          <button type="submit">Set up authenticator</button>
        </form>"""

    notice_map = {
        "password-changed": "Password updated. Existing product sessions were revoked as a security precaution.",
        "verification-sent": "Verification code sent. Enter it below to confirm the contact.",
        "verified": "Contact verified successfully.",
        "mfa-disabled": "Multi-factor authentication was disabled and existing product sessions were revoked.",
        "session-revoked": "The selected product session was revoked.",
    }
    notice = notice_map.get(request.query_params.get("notice", ""))
    notice_html = f'<div class="notice">{_e(notice)}</div>' if notice else ""

    role_badge = '<span class="badge good">System owner</span>' if user.is_platform_admin else '<span class="badge neutral">Central user</span>'
    security_summary = "MFA enabled" if user.totp_enabled else "MFA needs attention"

    body = f"""
    {notice_html}
    <section class="hero">
      <div>
        <div class="eyebrow">Central identity</div>
        <h1>{_e(user.display_name)}</h1>
        <p>This identity signs you into Ithute products. Product permissions remain inside each product; credentials and central security are managed here.</p>
        <div class="actions" style="margin-top:14px">{role_badge}<span class="badge {"good" if user.is_active else "bad"}">{"Active" if user.is_active else "Disabled"}</span></div>
      </div>
      <div class="card id-card">
        <div class="label">Central user ID</div>
        <code class="id-value">{_e(user.id)}</code>
        <p class="small">This immutable ID links the same person across Ithute products.</p>
      </div>
    </section>

    <div class="grid">
      <div class="card col-4 contact-card">
        <div class="label">Email</div>
        <div class="value">{_e(user.email or "Not set")}</div>
        <div class="status-line">{email_state}</div>
        <div class="contact-actions">{verify_email}</div>
      </div>
      <div class="card col-4 contact-card">
        <div class="label">Phone</div>
        <div class="value">{_e(user.phone or "Not set")}</div>
        <div class="status-line">{phone_state}</div>
        <div class="contact-actions">{verify_phone}</div>
      </div>
      <div class="card col-4 contact-card">
        <div class="label">Account protection</div>
        <div class="value">{_e(security_summary)}</div>
        <div class="status-line">{mfa_state}</div>
        <div class="contact-actions"><a class="button secondary" href="/account/passkeys">Manage passkeys</a></div>
      </div>

      <div class="card col-12">
        <div class="section-head">
          <div><h2>Security overview</h2><p>Quick view of the protections and recent usage attached to this central identity.</p></div>
        </div>
        <div class="stats">
          <div class="stat"><div class="label">Active product sessions</div><strong>{active_sessions}</strong></div>
          <div class="stat"><div class="label">Recent successful security events</div><strong>{successful_events}</strong></div>
          <div class="stat"><div class="label">Latest security activity</div><strong style="font-size:14px">{_e(last_security_event)}</strong></div>
        </div>
      </div>

      {verification_panel}

      <div class="card col-6 security-card">
        <div class="section-head"><div><h2>Change password</h2><p>Changing the password revokes product sessions and refreshes your central SSO session.</p></div></div>
        <form method="post" action="/account/password/change">
          <input type="hidden" name="csrf_token" value="{csrf}">
          <label>Current password</label>
          <input type="password" name="current_password" autocomplete="current-password" required>
          <label>New password</label>
          <input type="password" name="new_password" minlength="10" maxlength="128" autocomplete="new-password" required>
          <div class="help">Use at least 10 characters.</div>
          <label>Confirm new password</label>
          <input type="password" name="confirm_new_password" minlength="10" maxlength="128" autocomplete="new-password" required>
          <button type="submit">Change password</button>
        </form>
      </div>

      <div class="card col-12">
        <div class="section-head">
          <div><h2>Multi-factor authentication</h2><p>Protect the central account with an authenticator app and one-time recovery codes.</p></div>
          <div>{mfa_state}</div>
        </div>
        <div class="grid">
          <div class="col-7"><div class="callout">MFA protects every Ithute product that relies on this central sign-in. Keep recovery codes offline and never share authenticator codes.</div></div>
          <div class="col-5">{mfa_controls}</div>
        </div>
      </div>

      <div class="card col-12">
        <div class="section-head">
          <div><h2>Product sessions</h2><p>Review where this identity has active sessions across Mailbox, LoanHub, Tutor and other Ithute products.</p></div>
          <form method="post" action="/account/sessions/revoke-all" onsubmit="return confirm('Sign out of all Ithute product sessions?');">
            <input type="hidden" name="csrf_token" value="{csrf}">
            <button class="danger" type="submit">Sign out everywhere</button>
          </form>
        </div>
        {session_rows}
      </div>

      <div class="card col-12">
        <div class="section-head"><div><h2>Security activity</h2><p>Recent authentication, recovery, MFA and session events for this identity.</p></div></div>
        {audit_rows}
      </div>

      <div class="card col-12 danger-zone">
        <div class="section-head">
          <div><h2>Security guidance</h2><p>For a system-owner account, keep MFA enabled, maintain a verified recovery contact and revoke any session you do not recognize.</p></div>
          <a class="button ghost" href="/account/passkeys">Review passkeys</a>
        </div>
      </div>
    </div>"""
    return HTMLResponse(_page("Account", body, user=user))


@router.post("/account/password/change")
def portal_change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_new_password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    user, _, _ = _require_portal_user(request, db, settings)
    _require_csrf(request, csrf_token, settings)
    if len(new_password) < 10 or len(new_password) > 128:
        raise HTTPException(status_code=400, detail="new password must be 10-128 characters")
    if not hmac.compare_digest(new_password, confirm_new_password):
        raise HTTPException(status_code=400, detail="new passwords do not match")
    if not verify_password(current_password, user.password_hash):
        record_audit(db, event_type="password_change", user=user, success=False, request=request)
        db.commit()
        raise HTTPException(status_code=401, detail="invalid credentials")
    user.password_hash = hash_password(new_password)
    user.password_changed_at = utcnow()
    user.security_version += 1
    revoke_sessions(db, user_id=user.id, reason="password changed")
    record_audit(db, event_type="password_change", user=user, request=request)
    db.commit()
    response = RedirectResponse("/account?notice=password-changed", status_code=303)
    _set_sso_cookie(response, user, settings)
    return response


@router.post("/account/verification/request")
def portal_verification_request(
    request: Request,
    channel: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    user, _, _ = _require_portal_user(request, db, settings)
    _require_csrf(request, csrf_token, settings)
    if channel not in {"email", "phone"}:
        raise HTTPException(status_code=400, detail="invalid channel")
    target = user.email if channel == "email" else user.phone
    if not target:
        raise HTTPException(status_code=400, detail=f"no {channel} on account")
    if (channel == "email" and user.email_verified) or (channel == "phone" and user.phone_verified):
        return RedirectResponse("/account", status_code=303)
    if verification_request_rate_limited(db, user=user, settings=settings):
        record_audit(db, event_type=f"{channel}_verification_rate_limited", user=user, success=False, request=request)
        db.commit()
        raise HTTPException(status_code=429, detail="too many verification requests")
    purpose = f"verify_{channel}"
    _mark_previous_tokens_consumed(db, user_id=user.id, purpose=purpose)
    code = new_numeric_code()
    row = SecurityToken(
        user_id=user.id,
        purpose=purpose,
        token_hash=hash_security_token(f"{user.id}:{code}"),
        target=target,
        expires_at=utcnow() + timedelta(minutes=settings.verification_code_minutes),
    )
    db.add(row)
    record_audit(db, event_type=f"{channel}_verification_requested", user=user, request=request)
    db.commit()
    try:
        if channel == "email":
            send_email(settings, recipient=target, subject="Verify your !thute email", body=f"Your !thute verification code is {code}.")
        else:
            send_sms(settings, phone=target, message=f"Your !thute verification code is {code}.")
    except Exception as exc:
        row.consumed_at = utcnow()
        record_audit(db, event_type=f"{channel}_verification_delivery", user=user, success=False, request=request)
        db.commit()
        raise HTTPException(status_code=503, detail="verification delivery is unavailable") from exc
    return RedirectResponse("/account?notice=verification-sent", status_code=303)


@router.post("/account/verification/confirm")
def portal_verification_confirm(
    request: Request,
    channel: str = Form(...),
    code: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    user, _, _ = _require_portal_user(request, db, settings)
    _require_csrf(request, csrf_token, settings)
    if channel not in {"email", "phone"}:
        raise HTTPException(status_code=400, detail="invalid channel")
    if verification_confirmation_rate_limited(db, user_id=user.id, settings=settings):
        record_audit(db, event_type=f"{channel}_verification_confirm_rate_limited", user=user, success=False, request=request)
        db.commit()
        raise HTTPException(status_code=429, detail="too many verification attempts")
    purpose = f"verify_{channel}"
    row = db.scalar(
        select(SecurityToken)
        .where(
            SecurityToken.user_id == user.id,
            SecurityToken.purpose == purpose,
            SecurityToken.token_hash == hash_security_token(f"{user.id}:{code.strip()}"),
            SecurityToken.consumed_at.is_(None),
        )
        .with_for_update()
    )
    if row is None or row.expires_at <= utcnow():
        record_audit(db, event_type=f"{channel}_verification_failed", user=user, success=False, request=request)
        db.commit()
        raise HTTPException(status_code=400, detail="invalid or expired verification code")
    row.consumed_at = utcnow()
    if channel == "email":
        user.email_verified = True
    else:
        user.phone_verified = True
    record_audit(db, event_type=f"{channel}_verified", user=user, request=request)
    db.commit()
    return RedirectResponse("/account?notice=verified", status_code=303)


@router.post("/account/mfa/start")
def portal_mfa_start(
    request: Request,
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    user, _, _ = _require_portal_user(request, db, settings)
    _require_csrf(request, csrf_token, settings)
    if user.totp_enabled:
        raise HTTPException(status_code=409, detail="MFA is already enabled; disable it with fresh password and MFA proof before replacing it")
    if not verify_password(password, user.password_hash):
        record_audit(db, event_type="mfa_enrollment_started", user=user, success=False, request=request)
        db.commit()
        raise HTTPException(status_code=401, detail="invalid credentials")
    secret = new_totp_secret()
    user.totp_secret_encrypted = encrypt_totp_secret(secret, settings)
    record_audit(db, event_type="mfa_enrollment_started", user=user, request=request)
    db.commit()
    return RedirectResponse("/account/mfa/setup", status_code=303)


@router.get("/account/mfa/setup", response_class=HTMLResponse)
def portal_mfa_setup(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    user = _cookie_user(request, db, settings)
    if user is None:
        return RedirectResponse("/account/login", status_code=303)
    if user.totp_enabled or not user.totp_secret_encrypted:
        return RedirectResponse("/account", status_code=303)
    raw = request.cookies[settings.browser_cookie_name]
    csrf = _portal_csrf(raw, settings)
    secret = decrypt_totp_secret(user.totp_secret_encrypted, settings)
    account_name = user.email or user.phone or str(user.id)
    uri = totp_provisioning_uri(secret, account_name=account_name, issuer_name=settings.totp_issuer_name)
    body = f"""
    <div class="card setup-card">
      <div class="eyebrow">Account protection</div>
      <h1>Set up authenticator</h1>
      <p>Add this account to your authenticator app, then enter the six-digit code it generates.</p>
      <div class="grid" style="margin-top:20px">
        <div class="col-6"><div class="callout"><div class="label">Manual setup secret</div><p><code>{_e(secret)}</code></p></div></div>
        <div class="col-6"><div class="callout"><div class="label">Provisioning URI</div><p><code>{_e(uri)}</code></p></div></div>
      </div>
      <form method="post" action="/account/mfa/confirm" style="margin-top:20px">
        <input type="hidden" name="csrf_token" value="{csrf}">
        <label>Authenticator code</label>
        <input name="code" autocomplete="one-time-code" inputmode="numeric" pattern="[0-9]{{6}}" minlength="6" maxlength="6" placeholder="000000" required>
        <button type="submit">Enable MFA</button>
      </form>
      <p class="small">The secret is shown only during setup. Keep it private.</p>
    </div>"""
    return HTMLResponse(_page("Set up MFA", body, user=user))


@router.post("/account/mfa/confirm", response_class=HTMLResponse)
def portal_mfa_confirm(
    request: Request,
    code: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    user, _, _ = _require_portal_user(request, db, settings)
    _require_csrf(request, csrf_token, settings)
    if user.totp_enabled:
        raise HTTPException(status_code=409, detail="MFA is already enabled")
    if not user.totp_secret_encrypted:
        raise HTTPException(status_code=400, detail="MFA enrollment has not started")
    secret = decrypt_totp_secret(user.totp_secret_encrypted, settings)
    if not verify_totp(secret, code):
        record_audit(db, event_type="mfa_enrollment_confirmed", user=user, success=False, request=request)
        db.commit()
        raise HTTPException(status_code=400, detail="invalid authenticator code")
    codes = new_recovery_codes()
    db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id))
    for recovery_code in codes:
        db.add(MfaRecoveryCode(user_id=user.id, code_hash=hash_recovery_code(recovery_code)))
    user.totp_enabled = True
    user.security_version += 1
    revoke_sessions(db, user_id=user.id, reason="MFA enabled")
    record_audit(db, event_type="mfa_enabled", user=user, request=request)
    db.commit()
    code_html = "".join(f"<li><code>{_e(value)}</code></li>" for value in codes)
    body = f"""
    <div class="card setup-card">
      <div class="eyebrow">MFA enabled</div>
      <h1>Save your recovery codes</h1>
      <p>Each code can be used once if your authenticator is unavailable. They will not be shown again.</p>
      <div class="callout" style="margin-top:18px"><ol class="recovery-list">{code_html}</ol></div>
      <div class="actions" style="margin-top:18px"><a class="button" href="/account">Return to account</a></div>
    </div>"""
    response = HTMLResponse(_page("Recovery codes", body, user=user))
    _set_sso_cookie(response, user, settings)
    return response


@router.post("/account/mfa/disable")
def portal_mfa_disable(
    request: Request,
    password: str = Form(...),
    code: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    user, _, _ = _require_portal_user(request, db, settings)
    _require_csrf(request, csrf_token, settings)
    if not verify_password(password, user.password_hash) or not verify_second_factor(db, user=user, code=code, settings=settings):
        record_audit(db, event_type="mfa_disabled", user=user, success=False, request=request)
        db.commit()
        raise HTTPException(status_code=401, detail="invalid credentials or MFA code")
    user.totp_enabled = False
    user.totp_secret_encrypted = None
    user.security_version += 1
    db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id))
    revoke_sessions(db, user_id=user.id, reason="MFA disabled")
    record_audit(db, event_type="mfa_disabled", user=user, request=request)
    db.commit()
    response = RedirectResponse("/account?notice=mfa-disabled", status_code=303)
    _set_sso_cookie(response, user, settings)
    return response


@router.post("/account/sessions/{session_id}/revoke")
def portal_revoke_session(
    session_id: uuid.UUID,
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    user, _, _ = _require_portal_user(request, db, settings)
    _require_csrf(request, csrf_token, settings)
    row = db.get(AuthSession, session_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="session not found")
    if row.revoked_at is None:
        row.revoked_at = utcnow()
        row.revoked_reason = "revoked from account portal"
    record_audit(
        db,
        event_type="session_revoked",
        user=user,
        client_id=row.client_id,
        request=request,
        details={"session_id": str(row.id)},
    )
    db.commit()
    return RedirectResponse("/account?notice=session-revoked", status_code=303)


@router.post("/account/sessions/revoke-all")
def portal_revoke_all_sessions(
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    user, _, _ = _require_portal_user(request, db, settings)
    _require_csrf(request, csrf_token, settings)
    count = revoke_sessions(db, user_id=user.id, reason="sign out everywhere")
    user.security_version += 1
    record_audit(db, event_type="all_sessions_revoked", user=user, request=request, details={"count": count})
    db.commit()
    response = RedirectResponse("/account/login", status_code=303)
    response.delete_cookie(settings.browser_cookie_name, path="/")
    return response


def _require_admin(request: Request, db: Session, settings: Settings) -> tuple[User, str]:
    user, _, csrf = _require_portal_user(request, db, settings)
    if not user.is_platform_admin:
        raise HTTPException(status_code=403, detail="platform admin required")
    return user, csrf


@router.get("/admin", response_class=HTMLResponse)
def admin_home(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    user = _cookie_user(request, db, settings)
    if user is None:
        return RedirectResponse("/account/login", status_code=303)
    if not user.is_platform_admin:
        raise HTTPException(status_code=403, detail="platform admin required")
    raw = request.cookies[settings.browser_cookie_name]
    csrf = _portal_csrf(raw, settings)
    users = db.scalars(select(User).order_by(User.created_at.desc()).limit(100)).all()
    apps = db.scalars(select(Application).order_by(Application.name.asc())).all()

    user_rows = "".join(
        (
            f'<tr><td><strong>{_e(row.display_name)}</strong><div class="small">{_e(row.email or row.phone or row.id)}</div></td>'
            f'<td>{"Admin" if row.is_platform_admin else "User"}</td>'
            f'<td><span class="badge {"good" if row.is_active else "bad"}">{"Active" if row.is_active else "Disabled"}</span></td>'
            f'<td>{_e(_fmt(row.last_login_at))}</td>'
            f'<td><form method="post" action="/admin/users/{row.id}/action">'
            f'<input type="hidden" name="csrf_token" value="{csrf}">'
            '<select name="action"><option value="unlock">Unlock</option><option value="revoke">Revoke sessions</option><option value="enable">Enable</option><option value="disable">Disable</option></select>'
            '<button class="secondary" type="submit">Apply</button></form></td></tr>'
        )
        for row in users
    )
    app_rows = "".join(
        (
            f'<tr><td><strong>{_e(app.name)}</strong><div class="small"><code>{_e(app.client_id)}</code></div></td>'
            f'<td><span class="badge {"good" if app.is_active else "bad"}">{"Enabled" if app.is_active else "Disabled"}</span></td>'
            f'<td><form method="post" action="/admin/apps/{quote(app.client_id, safe="")}/toggle">'
            f'<input type="hidden" name="csrf_token" value="{csrf}">'
            f'<button class="secondary" type="submit">{"Disable" if app.is_active else "Enable"}</button></form></td></tr>'
        )
        for app in apps
    )
    body = f"""
    <div class="hero"><div><div class="eyebrow">Platform administration</div><h1>Identity administration</h1><p>Central user and first-party application controls. Product roles and business permissions remain inside each product.</p></div></div>
    <div class="grid">
      <div class="card col-12"><div class="section-head"><div><h2>Users</h2><p>Manage central account availability and sessions.</p></div></div><table><thead><tr><th>User</th><th>Role</th><th>Status</th><th>Last login</th><th>Action</th></tr></thead><tbody>{user_rows}</tbody></table></div>
      <div class="card col-12"><div class="section-head"><div><h2>Applications</h2><p>Enable or disable first-party clients registered with !thute Auth.</p></div></div><table><thead><tr><th>Application</th><th>Status</th><th>Action</th></tr></thead><tbody>{app_rows}</tbody></table></div>
    </div>"""
    return HTMLResponse(_page("Admin", body, user=user))


@router.post("/admin/users/{user_id}/action")
def admin_user_action(
    user_id: uuid.UUID,
    request: Request,
    action: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    admin, _ = _require_admin(request, db, settings)
    _require_csrf(request, csrf_token, settings)
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user not found")
    if action == "unlock":
        target.failed_login_attempts = 0
        target.locked_until = None
    elif action == "revoke":
        revoke_sessions(db, user_id=target.id, reason="platform admin revocation")
        target.security_version += 1
    elif action == "enable":
        target.is_active = True
    elif action == "disable":
        if target.id == admin.id:
            raise HTTPException(status_code=400, detail="cannot disable your own admin account")
        target.is_active = False
        target.security_version += 1
        revoke_sessions(db, user_id=target.id, reason="account disabled by platform admin")
    else:
        raise HTTPException(status_code=400, detail="invalid admin action")
    record_audit(db, event_type=f"admin_user_{action}", user=admin, request=request, details={"target_user_id": str(target.id)})
    db.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/admin/apps/{client_id}/toggle")
def admin_app_toggle(
    client_id: str,
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    admin, _ = _require_admin(request, db, settings)
    _require_csrf(request, csrf_token, settings)
    app = db.scalar(select(Application).where(Application.client_id == client_id))
    if app is None:
        raise HTTPException(status_code=404, detail="application not found")
    app.is_active = not app.is_active
    record_audit(
        db,
        event_type="admin_application_toggled",
        user=admin,
        client_id=app.client_id,
        request=request,
        details={"active": app.is_active},
    )
    db.commit()
    return RedirectResponse("/admin", status_code=303)
