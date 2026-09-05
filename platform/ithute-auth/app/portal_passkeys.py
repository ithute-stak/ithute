from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import secrets
import uuid
from datetime import timedelta

import jwt
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from .config import Settings, get_settings
from .db import get_db
from .models import PasskeyCredential, User, WebAuthnChallenge, utcnow
from .security import (
    create_browser_session_token,
    decode_browser_session_token,
    verify_password,
)
from .security_service import client_ip, login_rate_limited, record_audit, verify_second_factor


router = APIRouter(tags=["portal-passkeys"])


_STYLE = """
:root{--ink:#10233d;--muted:#607087;--line:#dfe6ee;--soft:#f5f8fb;--brand:#1f5eff;--good:#137a4e;--bad:#b42318}*{box-sizing:border-box}body{margin:0;background:#f4f7fb;color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.shell{max-width:900px;margin:0 auto;padding:24px}.top{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:24px}.brand{font-size:22px;font-weight:850}.brand span{color:var(--brand)}a{color:var(--brand);text-decoration:none}.card{background:#fff;border:1px solid var(--line);border-radius:18px;padding:22px;box-shadow:0 8px 28px rgba(16,35,61,.06);margin-bottom:18px}h1,h2{margin-top:0}p{color:var(--muted);line-height:1.55}.row{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 0;border-bottom:1px solid var(--line)}.row:last-child{border-bottom:0}.small{font-size:12px;color:var(--muted)}label{font-size:13px;font-weight:700}input{width:100%;padding:11px 12px;border:1px solid #cfd8e3;border-radius:10px;font:inherit}form{display:grid;gap:10px}button,.button{border:0;border-radius:10px;padding:10px 14px;background:var(--brand);color:#fff;font-weight:750;cursor:pointer;display:inline-flex;align-items:center;justify-content:center}.secondary{background:#eaf0f8;color:var(--ink)}.danger{background:var(--bad)}.notice{display:none;padding:12px 14px;border-radius:10px;background:#eef5ff;border:1px solid #cfe0ff;margin:12px 0}.notice.error{background:#fff0ef;border-color:#ffc9c5;color:var(--bad)}code{background:#eef2f7;padding:2px 6px;border-radius:6px}@media(max-width:650px){.row,.top{align-items:flex-start;flex-direction:column}}
"""


def _e(value: object | None) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _from_b64url(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _enum_value(value) -> str | None:
    return None if value is None else str(getattr(value, "value", value))


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


def _csrf(raw_cookie: str, settings: Settings) -> str:
    key = hashlib.sha256(("ithute-portal-csrf-v1\n" + settings.private_key).encode("utf-8")).digest()
    return hmac.new(key, raw_cookie.encode("utf-8"), hashlib.sha256).hexdigest()


def _require_user(request: Request, db: Session, settings: Settings) -> tuple[User, str]:
    raw = request.cookies.get(settings.browser_cookie_name)
    user = _cookie_user(request, db, settings)
    if user is None or not raw:
        raise HTTPException(status_code=401, detail="sign in required")
    return user, _csrf(raw, settings)


def _require_csrf(request: Request, submitted: str, settings: Settings) -> None:
    raw = request.cookies.get(settings.browser_cookie_name)
    if not raw or not hmac.compare_digest(_csrf(raw, settings), submitted):
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


def _challenge(db: Session, challenge_id: str, *, purpose: str, user_id: uuid.UUID | None = None) -> WebAuthnChallenge:
    try:
        challenge_uuid = uuid.UUID(challenge_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid challenge") from None
    row = db.scalar(select(WebAuthnChallenge).where(WebAuthnChallenge.id == challenge_uuid).with_for_update())
    if (
        row is None
        or row.purpose != purpose
        or row.consumed_at is not None
        or row.expires_at <= utcnow()
        or (user_id is not None and row.user_id != user_id)
    ):
        raise HTTPException(status_code=400, detail="invalid or expired challenge")
    return row


def _webauthn_js() -> str:
    return r"""
function b64urlToBytes(value){
  const pad='='.repeat((4-value.length%4)%4); const base64=(value+pad).replace(/-/g,'+').replace(/_/g,'/');
  const raw=atob(base64); return Uint8Array.from(raw,c=>c.charCodeAt(0));
}
function bytesToB64url(value){
  if(value===null||value===undefined) return null;
  const bytes=new Uint8Array(value); let binary=''; for(const b of bytes) binary+=String.fromCharCode(b);
  return btoa(binary).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
}
function creationOptions(json){
  const o=structuredClone(json); o.challenge=b64urlToBytes(o.challenge); o.user.id=b64urlToBytes(o.user.id);
  if(o.excludeCredentials) o.excludeCredentials=o.excludeCredentials.map(c=>({...c,id:b64urlToBytes(c.id)})); return o;
}
function requestOptions(json){
  const o=structuredClone(json); o.challenge=b64urlToBytes(o.challenge);
  if(o.allowCredentials) o.allowCredentials=o.allowCredentials.map(c=>({...c,id:b64urlToBytes(c.id)})); return o;
}
function registrationJSON(c){
  return {id:c.id,rawId:bytesToB64url(c.rawId),type:c.type,clientExtensionResults:c.getClientExtensionResults(),response:{clientDataJSON:bytesToB64url(c.response.clientDataJSON),attestationObject:bytesToB64url(c.response.attestationObject),transports:c.response.getTransports?c.response.getTransports():[]}};
}
function authenticationJSON(c){
  return {id:c.id,rawId:bytesToB64url(c.rawId),type:c.type,clientExtensionResults:c.getClientExtensionResults(),response:{clientDataJSON:bytesToB64url(c.response.clientDataJSON),authenticatorData:bytesToB64url(c.response.authenticatorData),signature:bytesToB64url(c.response.signature),userHandle:bytesToB64url(c.response.userHandle)}};
}
function message(text,isError=false){const el=document.getElementById('passkey-notice');if(!el)return;el.textContent=text;el.className='notice'+(isError?' error':'');el.style.display='block';}
"""


@router.get("/account/passkeys", response_class=HTMLResponse)
def passkey_page(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    user = _cookie_user(request, db, settings)
    if user is None:
        return RedirectResponse("/account/login", status_code=303)
    raw = request.cookies[settings.browser_cookie_name]
    csrf = _csrf(raw, settings)
    rows = db.scalars(select(PasskeyCredential).where(PasskeyCredential.user_id == user.id).order_by(PasskeyCredential.created_at.desc())).all()
    passkey_rows = "".join(
        f'<div class="row"><div><strong>{_e(row.label or "Passkey")}</strong><div class="small">{_e(row.device_type or "Authenticator")} · {"synced" if row.backed_up else "device-bound"} · added {_e(row.created_at.strftime("%Y-%m-%d"))}</div></div><form method="post" action="/account/passkeys/{row.id}/remove"><input type="hidden" name="csrf_token" value="{csrf}"><input type="password" name="password" placeholder="Password" required><input name="mfa_code" placeholder="MFA/recovery code if enabled"><button class="danger" type="submit">Remove</button></form></div>'
        for row in rows
    ) or '<p>No passkeys are registered yet.</p>'
    js = _webauthn_js() + f"""
async function addPasskey(){{
  try{{
    message('Preparing your passkey…');
    const start=await fetch('/account/passkeys/registration/options',{{method:'POST',headers:{{'content-type':'application/json'}},body:JSON.stringify({{csrf_token:'{csrf}'}})}});
    const data=await start.json(); if(!start.ok) throw new Error(data.detail||'Could not start passkey registration');
    const credential=await navigator.credentials.create({{publicKey:creationOptions(data.options)}}); if(!credential) throw new Error('No credential was created');
    const password=document.getElementById('pk-password').value; const mfa=document.getElementById('pk-mfa').value; const label=document.getElementById('pk-label').value;
    const verify=await fetch('/account/passkeys/registration/verify',{{method:'POST',headers:{{'content-type':'application/json'}},body:JSON.stringify({{csrf_token:'{csrf}',challenge_id:data.challenge_id,credential:registrationJSON(credential),password:password,mfa_code:mfa||null,label:label||null}})}});
    const result=await verify.json(); if(!verify.ok) throw new Error(result.detail||'Passkey registration failed');
    location.reload();
  }}catch(err){{message(err.message||String(err),true);}}
}}
"""
    body = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Passkeys · !thute</title><style>{_STYLE}</style></head><body><div class="shell"><div class="top"><div class="brand"><span>!</span>thute Identity</div><div><a href="/account">← Account</a></div></div><div class="card"><h1>Passkeys</h1><p>Use Face ID, Touch ID, Windows Hello, Android biometrics, a device PIN, or a FIDO2 security key to authenticate without sharing a password with a product.</p><div id="passkey-notice" class="notice"></div><label>Passkey label</label><input id="pk-label" placeholder="e.g. Work laptop"><label>Current password</label><input id="pk-password" type="password" required><label>MFA/recovery code <span class="small">(required only if MFA is enabled)</span></label><input id="pk-mfa"><div style="margin-top:12px"><button type="button" onclick="addPasskey()">Add passkey</button></div></div><div class="card"><h2>Your passkeys</h2>{passkey_rows}</div><div class="card"><h2>Passwordless sign-in</h2><p>After adding a passkey, you can sign into the central !thute account without entering your password.</p><a class="button secondary" href="/account/passkey-login">Try passkey sign-in</a></div></div><script>{js}</script></body></html>"""
    return HTMLResponse(body)


@router.post("/account/passkeys/registration/options")
async def portal_registration_options(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    user, expected_csrf = _require_user(request, db, settings)
    payload = await request.json()
    submitted = str(payload.get("csrf_token", "")) if isinstance(payload, dict) else ""
    if not hmac.compare_digest(expected_csrf, submitted):
        raise HTTPException(status_code=403, detail="invalid CSRF token")
    challenge = secrets.token_bytes(32)
    row = WebAuthnChallenge(user_id=user.id, purpose="portal_register", challenge=_b64url(challenge), expires_at=utcnow() + timedelta(minutes=settings.webauthn_challenge_minutes))
    db.add(row); db.commit(); db.refresh(row)
    existing = db.scalars(select(PasskeyCredential).where(PasskeyCredential.user_id == user.id)).all()
    options = generate_registration_options(
        rp_id=settings.webauthn_rp_id,
        rp_name=settings.webauthn_rp_name,
        user_id=user.id.bytes,
        user_name=user.email or user.phone or str(user.id),
        user_display_name=user.display_name,
        challenge=challenge,
        attestation=AttestationConveyancePreference.NONE,
        authenticator_selection=AuthenticatorSelectionCriteria(resident_key=ResidentKeyRequirement.REQUIRED,user_verification=UserVerificationRequirement.REQUIRED),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(item.credential_id)) for item in existing],
    )
    return {"challenge_id": str(row.id), "options": json.loads(options_to_json(options))}


@router.post("/account/passkeys/registration/verify")
async def portal_registration_verify(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    user, expected_csrf = _require_user(request, db, settings)
    payload = await request.json()
    if not isinstance(payload, dict) or not hmac.compare_digest(expected_csrf, str(payload.get("csrf_token", ""))):
        raise HTTPException(status_code=403, detail="invalid CSRF token")
    challenge = _challenge(db, str(payload.get("challenge_id", "")), purpose="portal_register", user_id=user.id)
    password = str(payload.get("password", "")); mfa_code = payload.get("mfa_code")
    if not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    if not verify_second_factor(db, user=user, code=str(mfa_code) if mfa_code else None, settings=settings):
        db.commit(); raise HTTPException(status_code=401, detail="MFA required or invalid code")
    credential = payload.get("credential")
    if not isinstance(credential, dict):
        raise HTTPException(status_code=400, detail="invalid credential")
    try:
        verification = verify_registration_response(credential=credential, expected_challenge=_from_b64url(challenge.challenge), expected_rp_id=settings.webauthn_rp_id, expected_origin=settings.webauthn_origin, require_user_verification=True)
    except Exception as exc:
        record_audit(db, event_type="passkey_registration", user=user, success=False, request=request); db.commit()
        raise HTTPException(status_code=400, detail="invalid passkey registration") from exc
    transports = credential.get("response", {}).get("transports") if isinstance(credential.get("response"), dict) else None
    row = PasskeyCredential(user_id=user.id, credential_id=_b64url(verification.credential_id), public_key=_b64url(verification.credential_public_key), sign_count=verification.sign_count, device_type=_enum_value(verification.credential_device_type), backed_up=bool(verification.credential_backed_up), transports_json=json.dumps(transports) if isinstance(transports,list) else None, label=(str(payload.get("label")).strip()[:160] if payload.get("label") else None))
    challenge.consumed_at=utcnow(); db.add(row)
    try:
        db.flush()
    except Exception as exc:
        db.rollback(); raise HTTPException(status_code=409, detail="passkey is already registered") from exc
    record_audit(db,event_type="passkey_registered",user=user,request=request,details={"passkey_id":str(row.id)}); db.commit()
    return {"status":"registered","id":str(row.id)}


@router.post("/account/passkeys/{passkey_id}/remove")
def portal_remove_passkey(passkey_id: uuid.UUID, request: Request, password: str = Form(...), mfa_code: str = Form(default=""), csrf_token: str = Form(...), db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    user, _ = _require_user(request, db, settings); _require_csrf(request, csrf_token, settings)
    row = db.get(PasskeyCredential, passkey_id)
    if row is None or row.user_id != user.id: raise HTTPException(status_code=404, detail="passkey not found")
    if not verify_password(password,user.password_hash) or not verify_second_factor(db,user=user,code=mfa_code or None,settings=settings):
        record_audit(db,event_type="passkey_removed",user=user,success=False,request=request); db.commit(); raise HTTPException(status_code=401,detail="invalid credentials or MFA code")
    db.delete(row); record_audit(db,event_type="passkey_removed",user=user,request=request,details={"passkey_id":str(passkey_id)}); db.commit()
    return RedirectResponse("/account/passkeys",status_code=303)


@router.get("/account/passkey-login", response_class=HTMLResponse)
def portal_passkey_login_page(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    if _cookie_user(request,db,settings) is not None: return RedirectResponse("/account",status_code=303)
    js=_webauthn_js()+"""
async function signInPasskey(){try{message('Waiting for your passkey…');const s=await fetch('/account/passkey-login/options',{method:'POST'});const d=await s.json();if(!s.ok)throw new Error(d.detail||'Could not start sign-in');const c=await navigator.credentials.get({publicKey:requestOptions(d.options)});if(!c)throw new Error('No passkey was selected');const v=await fetch('/account/passkey-login/verify',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({challenge_id:d.challenge_id,credential:authenticationJSON(c)})});const r=await v.json();if(!v.ok)throw new Error(r.detail||'Passkey sign-in failed');location.href='/account';}catch(err){message(err.message||String(err),true);}}
"""
    body=f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Passkey sign-in · !thute</title><style>{_STYLE}</style></head><body><div class="shell"><div class="top"><div class="brand"><span>!</span>thute Identity</div><a href="/account/login">Use password instead</a></div><div class="card" style="max-width:520px;margin:8vh auto"><h1>Sign in with a passkey</h1><p>Your device will ask for its biometric, PIN, or security key. Your biometric data never leaves your device.</p><div id="passkey-notice" class="notice"></div><button type="button" onclick="signInPasskey()">Continue with passkey</button></div></div><script>{js}</script></body></html>"""
    return HTMLResponse(body)


@router.post("/account/passkey-login/options")
def portal_passkey_login_options(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    challenge=secrets.token_bytes(32); row=WebAuthnChallenge(purpose="portal_authenticate",challenge=_b64url(challenge),expires_at=utcnow()+timedelta(minutes=settings.webauthn_challenge_minutes)); db.add(row); db.commit(); db.refresh(row)
    options=generate_authentication_options(rp_id=settings.webauthn_rp_id,challenge=challenge,user_verification=UserVerificationRequirement.REQUIRED)
    return {"challenge_id":str(row.id),"options":json.loads(options_to_json(options))}


@router.post("/account/passkey-login/verify")
async def portal_passkey_login_verify(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    if login_rate_limited(db,request=request,settings=settings): raise HTTPException(status_code=429,detail="too many login attempts")
    payload=await request.json()
    if not isinstance(payload,dict): raise HTTPException(status_code=400,detail="invalid request")
    challenge=_challenge(db,str(payload.get("challenge_id","")),purpose="portal_authenticate"); credential=payload.get("credential")
    if not isinstance(credential,dict) or not isinstance(credential.get("id"),str): raise HTTPException(status_code=400,detail="invalid credential")
    passkey=db.scalar(select(PasskeyCredential).where(PasskeyCredential.credential_id==credential["id"]).with_for_update())
    if passkey is None: record_audit(db,event_type="login_failed",success=False,client_id="ithute-account",request=request); db.commit(); raise HTTPException(status_code=401,detail="invalid passkey")
    user=db.get(User,passkey.user_id)
    if user is None or not user.is_active or (user.locked_until is not None and user.locked_until>utcnow()): raise HTTPException(status_code=401,detail="invalid passkey")
    try:
        verification=verify_authentication_response(credential=credential,expected_challenge=_from_b64url(challenge.challenge),expected_rp_id=settings.webauthn_rp_id,expected_origin=settings.webauthn_origin,credential_public_key=_from_b64url(passkey.public_key),credential_current_sign_count=passkey.sign_count,require_user_verification=True)
    except Exception as exc:
        user.failed_login_attempts+=1
        if user.failed_login_attempts>=settings.max_login_failures: user.locked_until=utcnow()+timedelta(minutes=settings.login_lock_minutes)
        record_audit(db,event_type="login_failed",user=user,success=False,client_id="ithute-account",request=request); db.commit(); raise HTTPException(status_code=401,detail="invalid passkey") from exc
    now=utcnow(); challenge.consumed_at=now; passkey.sign_count=verification.new_sign_count; passkey.device_type=_enum_value(verification.credential_device_type); passkey.backed_up=bool(verification.credential_backed_up); passkey.last_used_at=now; user.failed_login_attempts=0; user.locked_until=None; user.last_login_at=now; user.last_login_ip=client_ip(request)
    record_audit(db,event_type="passkey_login_succeeded",user=user,client_id="ithute-account",request=request,details={"passkey_id":str(passkey.id)}); db.commit()
    response=JSONResponse({"status":"ok"}); _set_sso_cookie(response,user,settings); return response
