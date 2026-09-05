import html
from datetime import timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .db import get_db
from .models import User, utcnow
from .oauth import _issue_authorization_code, _redirect_with_code, _validate_authorization_request
from .security import normalize_email, normalize_phone, verify_password
from .security_service import login_rate_limited, record_audit, verify_second_factor


router = APIRouter(tags=["platform-admin-step-up"])


def _form(fields: dict[str, str], *, error: str = "") -> str:
    hidden = "\n".join(
        f'<input type="hidden" name="{html.escape(key)}" value="{html.escape(value, quote=True)}">'
        for key, value in fields.items()
    )
    error_html = f'<div class="error">{html.escape(error)}</div>' if error else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Authorize !thute platform administration</title><style>
body{{font-family:system-ui,sans-serif;background:#f4f7f5;color:#173c36;margin:0;padding:8vh 20px}}main{{max-width:430px;margin:auto;background:white;border:1px solid #dfe7e3;border-radius:20px;padding:28px;box-shadow:0 18px 55px rgba(18,58,56,.12)}}
.badge{{display:inline-block;background:#eef4f1;padding:7px 10px;border-radius:999px;font-size:11px;font-weight:800}}h1{{font-size:24px;margin:18px 0 8px}}p{{color:#61736d;line-height:1.55}}form{{display:grid;gap:14px;margin-top:22px}}label{{display:grid;gap:6px;font-size:12px;font-weight:800}}input{{padding:12px;border:1px solid #cdd9d4;border-radius:10px;font:inherit}}button{{padding:12px;border:0;border-radius:10px;background:#173c36;color:white;font-weight:800;cursor:pointer}}.error{{background:#fff2f0;color:#a63b32;padding:10px;border-radius:10px;font-size:12px;font-weight:700;margin-top:14px}}small{{font-weight:500;color:#71817c}}
</style></head><body><main><span class="badge">!thute privileged step-up</span><h1>Authorize Auth & Push administration</h1><p>This action requires a fresh central platform-admin sign-in. MFA is mandatory even when you already have an !thute SSO session.</p>{error_html}<form method="post" action="/v1/admin/authorize">{hidden}<label>Email or phone<input name="identifier" autocomplete="username" required></label><label>Password<input type="password" name="password" autocomplete="current-password" required></label><label>Authenticator or recovery code <small>Required for every platform admin</small><input name="mfa_code" autocomplete="one-time-code" required></label><button type="submit">Authorize privileged console</button></form></main></body></html>"""


def _fields(**values: str) -> dict[str, str]:
    return values


@router.get("/authorize")
def authorize_get(
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
        db=db, settings=settings, response_type=response_type, client_id=client_id,
        redirect_uri=redirect_uri, code_challenge=code_challenge,
        code_challenge_method=code_challenge_method, scope=scope, state=state, nonce=nonce,
    )
    if client_id != "mailbox-dns":
        raise HTTPException(status_code=400, detail="platform_admin_console_client_required")
    return HTMLResponse(_form(_fields(response_type=response_type, client_id=client_id, redirect_uri=redirect_uri, code_challenge=code_challenge, code_challenge_method=code_challenge_method, state=state, nonce=nonce, scope=normalized_scope)))


@router.post("/authorize")
def authorize_post(
    request: Request,
    response_type: str = Form(...), client_id: str = Form(...), redirect_uri: str = Form(...),
    code_challenge: str = Form(...), code_challenge_method: str = Form(...), state: str = Form(...),
    nonce: str = Form(...), scope: str = Form(default="openid profile email phone"),
    identifier: str = Form(...), password: str = Form(...), mfa_code: str = Form(...),
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
):
    normalized_scope = _validate_authorization_request(
        db=db, settings=settings, response_type=response_type, client_id=client_id,
        redirect_uri=redirect_uri, code_challenge=code_challenge,
        code_challenge_method=code_challenge_method, scope=scope, state=state, nonce=nonce,
    )
    fields = _fields(response_type=response_type, client_id=client_id, redirect_uri=redirect_uri, code_challenge=code_challenge, code_challenge_method=code_challenge_method, state=state, nonce=nonce, scope=normalized_scope)
    if client_id != "mailbox-dns":
        raise HTTPException(status_code=400, detail="platform_admin_console_client_required")
    if login_rate_limited(db, request=request, settings=settings):
        record_audit(db, event_type="platform_admin_step_up_rate_limited", success=False, client_id=client_id, request=request)
        db.commit()
        raise HTTPException(status_code=429, detail="too_many_login_attempts")

    email = normalize_email(identifier)
    phone = normalize_phone(identifier)
    user = db.scalar(select(User).where(or_(User.email == email, User.phone == phone), User.is_active.is_(True)))
    now = utcnow()
    valid = user is not None and (user.locked_until is None or user.locked_until <= now) and verify_password(password, user.password_hash)
    if not valid or user is None:
        record_audit(db, event_type="platform_admin_step_up_failed", user=user, success=False, client_id=client_id, request=request)
        db.commit()
        return HTMLResponse(_form(fields, error="Unable to authorize this platform admin."), status_code=401)
    if not user.is_platform_admin:
        record_audit(db, event_type="platform_admin_step_up_denied", user=user, success=False, client_id=client_id, request=request)
        db.commit()
        return HTMLResponse(_form(fields, error="This !thute account is not a platform admin."), status_code=403)
    if not user.totp_enabled:
        record_audit(db, event_type="platform_admin_step_up_mfa_required", user=user, success=False, client_id=client_id, request=request)
        db.commit()
        return HTMLResponse(_form(fields, error="Platform administration requires MFA. Enable MFA on your !thute account first."), status_code=403)
    if not verify_second_factor(db, user=user, code=mfa_code, settings=settings):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.max_login_failures:
            user.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
        record_audit(db, event_type="platform_admin_step_up_mfa_failed", user=user, success=False, client_id=client_id, request=request)
        db.commit()
        return HTMLResponse(_form(fields, error="Unable to authorize this platform admin."), status_code=401)

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    record_audit(db, event_type="platform_admin_step_up_succeeded", user=user, client_id=client_id, request=request)
    raw_code = _issue_authorization_code(
        db=db, settings=settings, user=user, client_id=client_id, redirect_uri=redirect_uri,
        code_challenge=code_challenge, nonce=nonce, scope=normalized_scope,
    )
    return RedirectResponse(_redirect_with_code(redirect_uri, raw_code, state), status_code=303)
