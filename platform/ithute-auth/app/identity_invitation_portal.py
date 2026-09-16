from __future__ import annotations

import html
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .db import get_db
from .identity_invitation_models import IdentityInvitation
from .identity_invitation_schemas import IdentityInvitationActivationRequest
from .identity_invitations import activate_identity_invitation


router = APIRouter(tags=["identity-activation-portal"])


def _mask_target(invitation: IdentityInvitation) -> str:
    if invitation.preferred_channel == "phone" and invitation.phone:
        digits = invitation.phone
        return f"{digits[:4]}••••{digits[-2:]}" if len(digits) > 6 else "verified phone"
    if invitation.email:
        local, _, domain = invitation.email.partition("@")
        visible = local[:2] + "•••" if local else "•••"
        return f"{visible}@{domain}" if domain else "verified email"
    return "registered contact"


def _page(*, invitation: IdentityInvitation | None, token: str = "", error: str = "", success: bool = False) -> str:
    title = "Activate your Ithute identity"
    if invitation is None:
        body = "<div class='notice error'>This activation invitation could not be found.</div>"
    elif success:
        body = """
        <div class='success-mark'>✓</div>
        <h1>Identity activated</h1>
        <p>Your central Ithute identity is ready. You can now sign in securely to services assigned to you.</p>
        <a class='primary' href='/account/login'>Continue to Ithute Auth</a>
        """
    else:
        error_html = f"<div class='notice error'>{html.escape(error)}</div>" if error else ""
        token_field = f"<input type='hidden' name='token' value='{html.escape(token, quote=True)}'>"
        target = html.escape(_mask_target(invitation))
        body = f"""
        <div class='eyebrow'>TRUSTED IDENTITY INVITATION</div>
        <h1>{html.escape(title)}</h1>
        <p class='lead'>Complete the invitation for <strong>{html.escape(invitation.display_name)}</strong>. The challenge was sent to <strong>{target}</strong>.</p>
        {error_html}
        <form method='post' action='/account/activate'>
          <input type='hidden' name='invitation_id' value='{invitation.id}'>
          {token_field}
          <label>Activation code</label>
          <input name='code' inputmode='numeric' autocomplete='one-time-code' placeholder='Enter the 6-digit code' maxlength='16'>
          <div class='hint'>If you opened an email activation link, you can leave the code field empty.</div>
          <label>Create password</label>
          <input type='password' name='password' autocomplete='new-password' minlength='10' maxlength='128' placeholder='At least 10 characters'>
          <label>Confirm password</label>
          <input type='password' name='password_confirm' autocomplete='new-password' minlength='10' maxlength='128' placeholder='Repeat password'>
          <div class='hint'>If you already have an Ithute identity, your existing password is not changed and these password fields may be left empty.</div>
          <button class='primary' type='submit'>Activate securely</button>
        </form>
        <div class='security-note'><strong>Why this is safe</strong><br>Trade or another trusted service can invite you, but it never receives your password. Your credential is created only inside Ithute Auth.</div>
        """

    return f"""<!doctype html>
<html lang='en'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Ithute Auth · Activate identity</title>
<link rel='icon' href='/favicon.svg' type='image/svg+xml'>
<style>
:root{{--blue:#126fd1;--deep:#062f68;--green:#42ad20;--ink:#10233f;--muted:#66758a;--line:#dce6f2;--bg:#f4f8fc}}
*{{box-sizing:border-box}} body{{margin:0;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:linear-gradient(135deg,#eef6ff 0%,#f8fbff 55%,#f1faef 100%);color:var(--ink);min-height:100vh;display:grid;place-items:center;padding:28px}}
.shell{{width:min(940px,100%);display:grid;grid-template-columns:.9fr 1.1fr;background:#fff;border:1px solid var(--line);border-radius:28px;overflow:hidden;box-shadow:0 24px 70px rgba(30,66,110,.14)}}
.brand{{padding:52px;background:linear-gradient(155deg,var(--deep),#0b5aa8 62%,#1f8c72);color:#fff;position:relative;overflow:hidden}} .brand:after{{content:"";position:absolute;inset:auto -80px -120px 40px;height:250px;border-radius:50%;background:rgba(123,211,21,.18)}}
.mark{{width:64px;height:64px;border-radius:20px;background:linear-gradient(145deg,#1a83e5,#0a4d9a);border:1px solid rgba(255,255,255,.32);display:grid;place-items:center;font-size:30px;font-weight:800;box-shadow:0 10px 26px rgba(0,0,0,.18)}}
.brand h2{{font-size:30px;margin:26px 0 12px}} .brand p{{line-height:1.65;color:#d8e9fb;max-width:380px}} .brand .mini{{margin-top:34px;padding-top:24px;border-top:1px solid rgba(255,255,255,.18);font-size:14px;color:#d8e9fb}}
.card{{padding:48px}} .eyebrow{{font-size:12px;font-weight:800;letter-spacing:.14em;color:var(--blue);margin-bottom:12px}} h1{{font-size:34px;line-height:1.15;margin:0 0 14px}} .lead{{color:var(--muted);line-height:1.6;margin-bottom:26px}} label{{display:block;font-size:13px;font-weight:750;margin:16px 0 7px}} input{{width:100%;border:1px solid #cbd9e8;border-radius:12px;padding:13px 14px;font-size:15px;outline:none}} input:focus{{border-color:var(--blue);box-shadow:0 0 0 3px rgba(18,111,209,.12)}} .hint{{font-size:12px;color:var(--muted);line-height:1.45;margin-top:6px}} .primary{{display:block;width:100%;border:0;border-radius:12px;background:linear-gradient(90deg,var(--blue),#0d63bd);color:#fff;padding:14px 18px;text-align:center;text-decoration:none;font-size:15px;font-weight:800;margin-top:22px;cursor:pointer}} .security-note{{margin-top:24px;border:1px solid #d9ead2;background:#f6fbf3;border-radius:14px;padding:14px 16px;color:#36593b;font-size:13px;line-height:1.5}} .notice{{padding:12px 14px;border-radius:12px;margin:14px 0;font-size:13px}} .error{{background:#fff2f2;border:1px solid #f3caca;color:#8d2424}} .success-mark{{width:64px;height:64px;border-radius:50%;display:grid;place-items:center;background:#eaf8e6;color:#258317;font-size:32px;font-weight:900;margin-bottom:20px}}
@media(max-width:780px){{.shell{{grid-template-columns:1fr}}.brand{{padding:32px}}.card{{padding:32px 26px}}h1{{font-size:30px}}}}
</style>
</head>
<body><main class='shell'><section class='brand'><div class='mark'>I</div><h2>Ithute Auth</h2><p>One secure identity for Ithute products and trusted business services. Your password, passkeys and MFA stay inside Ithute Auth.</p><div class='mini'>Identity invitation · Secure activation · Central account recovery</div></section><section class='card'>{body}</section></main></body></html>"""


@router.get("/account/activate", response_class=HTMLResponse)
def activation_page(
    invitation: uuid.UUID | None = None,
    token: str = "",
    db: Session = Depends(get_db),
) -> HTMLResponse:
    row = db.get(IdentityInvitation, invitation) if invitation else None
    return HTMLResponse(_page(invitation=row, token=token))


@router.post("/account/activate", response_class=HTMLResponse)
def activation_submit(
    request: Request,
    invitation_id: uuid.UUID = Form(...),
    code: str = Form(default=""),
    token: str = Form(default=""),
    password: str = Form(default=""),
    password_confirm: str = Form(default=""),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    invitation = db.get(IdentityInvitation, invitation_id)
    if password != password_confirm:
        return HTMLResponse(_page(invitation=invitation, token=token, error="Passwords do not match."), status_code=400)
    try:
        payload = IdentityInvitationActivationRequest(
            invitation_id=invitation_id,
            code=code.strip() or None,
            token=token.strip() or None,
            password=password or None,
        )
        activate_identity_invitation(payload, request=request, db=db, settings=settings)
    except (HTTPException, ValueError) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else "Please check the activation details and try again."
        status_code = exc.status_code if isinstance(exc, HTTPException) else 400
        return HTMLResponse(_page(invitation=invitation, token=token, error=str(detail)), status_code=status_code)
    return HTMLResponse(_page(invitation=invitation, success=True))
