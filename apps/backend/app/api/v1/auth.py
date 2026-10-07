import json
import secrets
from html import escape
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import (
    create_access_token,
    decrypt_secret,
    encrypt_secret,
    generate_refresh_token,
    generate_totp_secret,
    hash_password,
    hash_token,
    provisioning_uri,
    refresh_expiry,
    verify_password,
    verify_totp,
)
from app.db.session import get_db
from app.models import AuditLog, PasskeyCredential, PasswordResetToken, RecoveryCode, TrustedDevice, User, UserSession
from app.schemas.auth import (
    LoginRequest,
    MfaCodeRequest,
    MfaSetupResponse,
    PasswordChangeRequest,
    PasswordResetComplete,
    PasswordResetRequest,
    SessionOut,
    TokenResponse,
    RecoveryCodesResponse,
    RecoveryCodeStatus,
    TrustedDeviceOut,
    TrustedDeviceLabelRequest,
    SecurityEventOut,
    PasskeyRegistrationRequest,
    PasskeyAuthenticationRequest,
    PasskeyOut,
)
from app.services.auth_security import (
    clear_login_failures,
    enforce_login_rate_limit,
    enforce_password_reset_rate_limit,
    record_login_failure,
    request_client_ip,
)
from app.services.identity_security import (
    DEVICE_COOKIE_MAX_AGE,
    DEVICE_COOKIE_NAME,
    assess_login_risk,
    cancel_adaptive_challenge,
    generate_recovery_codes,
    issue_adaptive_challenge,
    lookup_device,
    recent_mail_threat_context,
    normalize_recovery_code,
    resolve_or_create_device,
    verify_adaptive_challenge,
)
from app.services.ithute_auth import ithute_auth_enabled
from app.services.passkeys import (
    PasskeyError,
    authentication_options as passkey_authentication_options,
    registration_options as passkey_registration_options,
    verify_authentication as verify_passkey_authentication,
    verify_registration as verify_passkey_registration,
)
from app.services.signup_security import send_system_email

def _require_local_auth_surface() -> None:
    if not settings.local_auth_enabled:
        raise HTTPException(status_code=404, detail="Local authentication is disabled")


router = APIRouter(prefix="/auth", tags=["auth"])
PASSWORD_RESET_EXPIRE_MINUTES = 30
# Always perform an expensive password verification even when the email address
# does not exist. This makes unknown-user responses less useful for timing based
# account discovery.
_DUMMY_PASSWORD_HASH = hash_password("mailbox-dns-invalid-login-sentinel")


def _user_payload(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "is_platform_owner": user.is_platform_owner,
        "mfa_enabled": user.mfa_enabled,
        "email_verified": user.email_verified_at is not None,
        "central_auth_enforced": user.central_auth_enforced,
        "central_auth_enforced_at": user.central_auth_enforced_at.isoformat() if user.central_auth_enforced_at else None,
    }


def _request_is_https(request: Request) -> bool:
    scheme = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower() or request.url.scheme.lower()
    return scheme == "https"


def _require_secure_auth_transport(request: Request, *, allow_bootstrap: bool = True) -> None:
    # Raw-IP bootstrap login is deliberately temporary. Account recovery is
    # stricter because its bearer secret must never traverse plaintext HTTP.
    if (
        settings.environment.lower() == "production"
        and not _request_is_https(request)
        and (not allow_bootstrap or settings.platform_mode == "domain")
    ):
        raise HTTPException(status_code=400, detail="HTTPS is required for authentication")


def _require_recovery_delivery() -> None:
    # Check mail delivery before looking up an account so configuration state
    # cannot be used to infer whether an email address is registered.
    if settings.environment.lower() == "production" and (not settings.system_email_from or not settings.system_smtp_host):
        raise HTTPException(status_code=503, detail="Account recovery is temporarily unavailable")


def _set_auth_cookies(response: Response, access: str, refresh: str, request: Request) -> None:
    common = {
        "httponly": True,
        "secure": settings.cookie_secure or _request_is_https(request),
        "samesite": settings.cookie_samesite,
        "path": "/",
    }
    response.set_cookie(settings.access_cookie_name, access, max_age=settings.access_token_expire_minutes * 60, **common)
    response.set_cookie(settings.refresh_cookie_name, refresh, max_age=settings.refresh_token_expire_days * 86400, **common)


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(settings.access_cookie_name, path="/")
    response.delete_cookie(settings.refresh_cookie_name, path="/")


def _set_device_cookie(response: Response, token: str, request: Request) -> None:
    response.set_cookie(
        DEVICE_COOKIE_NAME,
        token,
        max_age=DEVICE_COOKIE_MAX_AGE,
        httponly=True,
        secure=settings.cookie_secure or _request_is_https(request),
        samesite=settings.cookie_samesite,
        path="/",
    )


def _new_session(user: User, request: Request, db: Session) -> tuple[str, UserSession]:
    raw = generate_refresh_token()
    session = UserSession(
        user_id=user.id,
        refresh_token_hash=hash_token(raw),
        user_agent=request.headers.get("user-agent"),
        ip_address=request.headers.get("x-real-ip") or (request.client.host if request.client else None),
        expires_at=refresh_expiry(),
    )
    db.add(session)
    db.flush()
    return raw, session


def _revoke_all_sessions(db: Session, user_id: UUID) -> None:
    db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )


def _require_verified_email(user: User) -> None:
    if settings.environment.lower() == "production" and user.email_verified_at is None:
        raise HTTPException(status_code=403, detail="Email verification required")


@router.get("/capabilities")
def auth_capabilities():
    local_enabled = settings.local_auth_enabled
    return {
        "local_auth_enabled": local_enabled,
        "central_auth_enabled": ithute_auth_enabled(),
        "local_security_controls_enabled": local_enabled,
    }


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    _require_local_auth_surface()
    _require_secure_auth_transport(request)
    email = str(payload.email).strip().lower()
    enforce_login_rate_limit(request, email)

    user = db.scalar(select(User).where(User.email == email))
    password_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    password_ok = verify_password(payload.password, password_hash)
    if user is None or not password_ok or not user.is_active:
        record_login_failure(request, email)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    _require_verified_email(user)
    if user.central_auth_enforced:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "CENTRAL_AUTH_REQUIRED",
                "message": "This account requires Ithute Central Authentication.",
            },
        )

    mfa_verified = False
    recovery_code_used = False
    if user.mfa_enabled:
        if payload.recovery_code:
            normalized = normalize_recovery_code(payload.recovery_code)
            recovery = db.scalar(
                select(RecoveryCode).where(
                    RecoveryCode.user_id == user.id,
                    RecoveryCode.code_hash == hash_token(normalized),
                    RecoveryCode.used_at.is_(None),
                )
            )
            if recovery is None:
                record_login_failure(request, email)
                raise HTTPException(status_code=401, detail="Invalid recovery code")
            recovery.used_at = datetime.now(timezone.utc)
            mfa_verified = True
            recovery_code_used = True
        else:
            if not payload.mfa_code:
                raise HTTPException(status_code=401, detail="MFA or recovery code required")
            if not user.mfa_secret:
                record_login_failure(request, email)
                raise HTTPException(status_code=401, detail="Unable to verify sign-in")
            try:
                secret = decrypt_secret(user.mfa_secret)
            except ValueError as exc:
                record_login_failure(request, email)
                raise HTTPException(status_code=401, detail="Unable to verify sign-in") from exc
            if not verify_totp(secret, payload.mfa_code):
                record_login_failure(request, email)
                raise HTTPException(status_code=401, detail="Invalid MFA code")
            mfa_verified = True

    observed_device = lookup_device(db, user=user, request=request)
    is_new_device = observed_device is None
    mail_threat_context = recent_mail_threat_context(db, user=user)
    contextual_signals = []
    if mail_threat_context.get("active"):
        contextual_signals.append({
            "signal": mail_threat_context.get("signal"),
            "weight": mail_threat_context.get("weight"),
            "source": "mail_intelligence",
            "evidence_count": mail_threat_context.get("verified_threat_count"),
        })
    risk = assess_login_risk(
        device=observed_device,
        request=request,
        is_new_device=is_new_device,
        mfa_verified=mfa_verified,
        contextual_signals=contextual_signals,
    )

    if risk["recommended_action"] == "block":
        db.add(AuditLog(
            actor_user_id=user.id,
            action="auth.login.blocked",
            resource_type="user",
            resource_id=str(user.id),
            metadata_json=json.dumps({
                "risk_score": risk["score"],
                "risk_level": risk["level"],
                "signals": risk["signals"],
                "ip_address": request_client_ip(request),
                "user_agent": request.headers.get("user-agent"),
            }, separators=(",", ":")),
        ))
        db.commit()
        try:
            ip = request_client_ip(request)
            agent = request.headers.get("user-agent") or "Unknown browser or device"
            send_system_email(
                user.email,
                "Ithute blocked a high-risk sign-in",
                "Ithute blocked a sign-in because its security risk was too high.\n\n"
                f"Device: {agent}\nIP: {ip}\nRisk: {risk['level']} ({risk['score']}/100)\n\n"
                "If this was you, use a trusted device, a passkey, or Ithute Central Authentication. "
                "If this was not you, review your Security Center immediately.",
                "<html><body style=\"font-family:Arial,sans-serif;color:#173228\"><div style=\"max-width:560px;margin:auto;padding:28px\">"
                "<div style=\"font-size:13px;font-weight:700;color:#285b55\">Ithute Identity &amp; Account Security</div>"
                "<h2>High-risk sign-in blocked</h2>"
                f"<p><strong>Device:</strong> {escape(agent)}</p><p><strong>IP:</strong> {escape(ip)}</p>"
                f"<p><strong>Risk:</strong> {escape(str(risk['level']))} ({int(risk['score'])}/100)</p>"
                "<p>If this was you, use a trusted device, passkey or Central Authentication. If not, review Security Center immediately.</p>"
                "</div></body></html>",
            )
        except RuntimeError:
            pass
        raise HTTPException(
            status_code=403,
            detail={
                "code": "AUTH_RISK_BLOCKED",
                "message": "This sign-in was blocked because Ithute detected unusually high risk.",
                "risk_level": risk["level"],
                "risk_score": risk["score"],
            },
        )

    adaptive_verified = False
    if risk["recommended_action"] == "step_up" and not mfa_verified:
        if payload.step_up_challenge_id and payload.step_up_code:
            adaptive_verified = verify_adaptive_challenge(
                user=user,
                request=request,
                challenge_id=payload.step_up_challenge_id,
                code=payload.step_up_code,
            )
            if not adaptive_verified:
                db.add(AuditLog(
                    actor_user_id=user.id,
                    action="auth.step_up.failed",
                    resource_type="user",
                    resource_id=str(user.id),
                    metadata_json=json.dumps({
                        "risk_score": risk["score"],
                        "risk_level": risk["level"],
                        "ip_address": request_client_ip(request),
                    }, separators=(",", ":")),
                ))
                db.commit()
                raise HTTPException(
                    status_code=401,
                    detail={
                        "code": "AUTH_STEP_UP_INVALID",
                        "message": "That verification code is invalid or expired.",
                    },
                )
        else:
            try:
                challenge_id, code, created = issue_adaptive_challenge(user=user, request=request, risk=risk)
            except RuntimeError as exc:
                raise HTTPException(status_code=503, detail="Adaptive authentication is temporarily unavailable") from exc

            if created:
                try:
                    ip = request_client_ip(request)
                    agent = request.headers.get("user-agent") or "Unknown browser or device"
                    send_system_email(
                        user.email,
                        "Verify your Ithute sign-in",
                        "Ithute detected a sign-in that needs extra verification.\n\n"
                        f"Verification code: {code}\n\n"
                        f"Device: {agent}\nIP: {ip}\nRisk: {risk['level']} ({risk['score']}/100)\n\n"
                        "This code expires in 10 minutes. If this was not you, do not share the code and review your Security Center.",
                        "<html><body style=\"font-family:Arial,sans-serif;color:#173228\"><div style=\"max-width:560px;margin:auto;padding:28px\">"
                        "<div style=\"font-size:13px;font-weight:700;color:#285b55\">Ithute Identity &amp; Account Security</div>"
                        "<h2>Verify your sign-in</h2>"
                        "<p>Ithute detected a sign-in that needs extra verification.</p>"
                        f"<div style=\"font-size:30px;font-weight:800;letter-spacing:8px;margin:22px 0\">{escape(code)}</div>"
                        "<p>This code expires in 10 minutes.</p>"
                        f"<p><strong>Device:</strong> {escape(agent)}</p><p><strong>IP:</strong> {escape(ip)}</p>"
                        f"<p><strong>Risk:</strong> {escape(str(risk['level']))} ({int(risk['score'])}/100)</p>"
                        "<p>If this was not you, do not share the code and review your Security Center.</p>"
                        "</div></body></html>",
                    )
                except RuntimeError as exc:
                    cancel_adaptive_challenge(user=user, request=request, challenge_id=challenge_id)
                    raise HTTPException(status_code=503, detail="Unable to deliver the sign-in verification code") from exc

            db.add(AuditLog(
                actor_user_id=user.id,
                action="auth.step_up.required",
                resource_type="user",
                resource_id=str(user.id),
                metadata_json=json.dumps({
                    "risk_score": risk["score"],
                    "risk_level": risk["level"],
                    "new_device": is_new_device,
                    "signals": risk["signals"],
                    "mail_threat_context": mail_threat_context,
                }, separators=(",", ":")),
            ))
            db.commit()
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "AUTH_STEP_UP_REQUIRED",
                    "message": "This sign-in needs additional verification.",
                    "challenge_id": challenge_id,
                    "methods": ["email_code", "passkey"],
                    "risk_level": risk["level"],
                    "risk_score": risk["score"],
                },
            )

    if adaptive_verified:
        risk = assess_login_risk(
            device=observed_device,
            request=request,
            is_new_device=is_new_device,
            mfa_verified=True,
            contextual_signals=contextual_signals,
        )

    clear_login_failures(email)
    device, device_token, is_new_device = resolve_or_create_device(db, user=user, request=request)
    refresh_token, session = _new_session(user, request, db)
    session.trusted_device_id = device.id
    session.risk_score = int(risk["score"])
    session.risk_level = str(risk["level"])
    session.new_device = bool(is_new_device)
    session.last_seen_at = datetime.now(timezone.utc)
    access = create_access_token(str(user.id), {"sv": user.session_version, "sid": str(session.id)})
    db.add(AuditLog(
        actor_user_id=user.id,
        action="auth.login",
        resource_type="session",
        resource_id=str(session.id),
        metadata_json=json.dumps({
            "risk_score": risk["score"],
            "risk_level": risk["level"],
            "recommended_action": risk["recommended_action"],
            "new_device": is_new_device,
            "trusted_device_id": str(device.id),
            "recovery_code_used": recovery_code_used,
            "adaptive_step_up_verified": adaptive_verified,
            "signals": risk["signals"],
            "mail_threat_context": mail_threat_context,
        }, separators=(",", ":")),
    ))
    if adaptive_verified:
        db.add(AuditLog(
            actor_user_id=user.id,
            action="auth.step_up.verified",
            resource_type="session",
            resource_id=str(session.id),
            metadata_json=json.dumps({"risk_score": risk["score"], "risk_level": risk["level"]}, separators=(",", ":")),
        ))
    if is_new_device:
        db.add(AuditLog(
            actor_user_id=user.id,
            action="auth.device.new",
            resource_type="trusted_device",
            resource_id=str(device.id),
            metadata_json=json.dumps({
                "ip_address": request_client_ip(request),
                "user_agent": request.headers.get("user-agent"),
                "risk_score": risk["score"],
                "risk_level": risk["level"],
            }, separators=(",", ":")),
        ))
    if recovery_code_used:
        db.add(AuditLog(actor_user_id=user.id, action="auth.recovery_code.used", resource_type="user", resource_id=str(user.id)))
    db.commit()
    _set_auth_cookies(response, access, refresh_token, request)
    _set_device_cookie(response, device_token, request)

    if is_new_device:
        try:
            ip = request_client_ip(request)
            agent = request.headers.get("user-agent") or "Unknown browser or device"
            send_system_email(
                user.email,
                "New device signed in to your Ithute account",
                "A new device signed in to your Ithute account.\n\n"
                f"Device: {agent}\nIP: {ip}\nRisk: {risk['level']} ({risk['score']}/100)\n\n"
                "If this was not you, sign in to Ithute Security Center and revoke the device and active sessions.",
                "<html><body style=\"font-family:Arial,sans-serif;color:#173228\">"
                "<div style=\"max-width:560px;margin:auto;padding:28px\">"
                "<div style=\"font-size:13px;font-weight:700;color:#285b55\">Ithute Identity &amp; Account Security</div>"
                "<h2>New device sign-in</h2>"
                f"<p><strong>Device:</strong> {escape(agent)}</p><p><strong>IP:</strong> {escape(ip)}</p>"
                f"<p><strong>Risk:</strong> {escape(str(risk['level']))} ({int(risk['score'])}/100)</p>"
                "<p>If this was not you, open Ithute Security Center and revoke the device and active sessions immediately.</p>"
                "</div></body></html>",
            )
        except RuntimeError:
            pass

    return TokenResponse(access_token=access, user=_user_payload(user))


@router.post("/password-reset/request", status_code=202)
def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    _require_local_auth_surface()
    _require_secure_auth_transport(request, allow_bootstrap=False)
    _require_recovery_delivery()
    email = str(payload.email).strip().lower()
    enforce_password_reset_rate_limit(request, email)

    user = db.scalar(select(User).where(User.email == email))
    # Always return the same accepted response for unknown or inactive users.
    if user is None or not user.is_active:
        return {"accepted": True}

    # Central-auth hardened accounts must never be able to reopen the local
    # password path through recovery. The HTTP response remains generic to
    # avoid account-state enumeration.
    if user.central_auth_enforced:
        try:
            send_system_email(
                user.email,
                "Ithute account recovery notice",
                "A password reset was requested for your Ithute account.\n\n"
                "This account is protected by permanent Ithute Central Authentication, "
                "so local password recovery is disabled. Sign in with Central Authentication "
                "or use the central security centre for account recovery.\n\n"
                "If you did not request this, no action is required.",
                "<html><body style=\"font-family:Arial,sans-serif;color:#173228\">"
                "<div style=\"max-width:560px;margin:auto;padding:28px\">"
                "<h2 style=\"margin:0 0 12px\">Ithute account recovery notice</h2>"
                "<p>A password reset was requested for your Ithute account.</p>"
                "<p><strong>This account is protected by permanent Ithute Central Authentication.</strong> "
                "Local password recovery is disabled.</p>"
                "<p>Sign in with Central Authentication or open the central security centre for recovery.</p>"
                "<p style=\"color:#6f8178\">If you did not request this, no action is required.</p>"
                "</div></body></html>",
            )
        except RuntimeError as exc:
            if settings.environment.lower() == "production":
                raise HTTPException(status_code=503, detail="Account recovery is temporarily unavailable") from exc
        return {"accepted": True}

    now = datetime.now(timezone.utc)
    existing = db.scalars(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
    ).all()
    for row in existing:
        row.used_at = now

    raw = secrets.token_urlsafe(48)
    token = PasswordResetToken(
        user_id=user.id,
        token_hash=hash_token(raw),
        expires_at=now + timedelta(minutes=PASSWORD_RESET_EXPIRE_MINUTES),
    )
    db.add(token)
    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="auth.password_reset.request",
            resource_type="user",
            resource_id=str(user.id),
        )
    )
    db.commit()

    # Put the bearer secret in the URL fragment, not the query string. Browser
    # fragments are not sent to HTTP servers or reverse-proxy access logs.
    reset_url = f"{settings.frontend_url.rstrip('/')}/reset-password#token={raw}"
    try:
        send_system_email(
            user.email,
            "Reset your Ithute password",
            "A password reset was requested for your Ithute account.\n\n"
            f"Open this one-time verification link to choose a new password:\n{reset_url}\n\n"
            f"The link expires in {PASSWORD_RESET_EXPIRE_MINUTES} minutes and can only be used once. "
            "If you did not request this reset, you can ignore this message.",
            "<html><body style=\"margin:0;background:#f4f7f6;font-family:Arial,sans-serif;color:#173228\">"
            "<div style=\"max-width:600px;margin:0 auto;padding:32px 18px\">"
            "<div style=\"background:#ffffff;border:1px solid #dfe8e4;border-radius:18px;padding:30px\">"
            "<div style=\"font-size:13px;font-weight:700;color:#285b55;margin-bottom:18px\">Ithute Identity &amp; Account Security</div>"
            "<h2 style=\"font-size:26px;margin:0 0 12px\">Reset your password</h2>"
            "<p style=\"font-size:15px;line-height:1.6\">We received a request to reset the password for your Ithute account.</p>"
            f"<p style=\"margin:26px 0\"><a href=\"{reset_url}\" style=\"display:inline-block;background:#123a38;color:#ffffff;text-decoration:none;padding:13px 20px;border-radius:10px;font-weight:700\">Verify and reset password</a></p>"
            f"<p style=\"font-size:13px;line-height:1.6;color:#65766e\">This one-time link expires in {PASSWORD_RESET_EXPIRE_MINUTES} minutes. "
            "For your protection, completing the reset signs out existing local sessions.</p>"
            "<p style=\"font-size:13px;line-height:1.6;color:#65766e\">If you did not request this reset, you can ignore this email.</p>"
            "<hr style=\"border:none;border-top:1px solid #e5ece8;margin:24px 0\">"
            "<p style=\"font-size:12px;color:#8a9791\">Sent by auth@ithute.co.ls · Ithute account security</p>"
            "</div></div></body></html>",
        )
    except RuntimeError as exc:
        if settings.environment.lower() == "production":
            raise HTTPException(status_code=503, detail="Account recovery is temporarily unavailable") from exc

    result = {"accepted": True}
    if settings.environment.lower() != "production":
        result["reset_token"] = raw
    return result


@router.post("/password-reset/complete")
def complete_password_reset(
    payload: PasswordResetComplete,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    _require_local_auth_surface()
    _require_secure_auth_transport(request, allow_bootstrap=False)
    now = datetime.now(timezone.utc)
    token = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(payload.token))
    )
    if token is None or token.used_at is not None or token.expires_at <= now:
        raise HTTPException(status_code=400, detail="Password reset link is invalid or expired")

    user = db.get(User, token.user_id)
    if user is None or not user.is_active:
        token.used_at = now
        db.commit()
        raise HTTPException(status_code=400, detail="Password reset link is invalid or expired")
    if user.central_auth_enforced:
        token.used_at = now
        db.commit()
        raise HTTPException(status_code=400, detail="Password reset link is invalid or expired")
    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Choose a password you have not just been using")

    user.password_hash = hash_password(payload.new_password)
    user.session_version += 1
    _revoke_all_sessions(db, user.id)
    token.used_at = now
    other_tokens = db.scalars(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.id != token.id,
            PasswordResetToken.used_at.is_(None),
        )
    ).all()
    for row in other_tokens:
        row.used_at = now
    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="auth.password_reset.complete",
            resource_type="user",
            resource_id=str(user.id),
        )
    )
    db.commit()
    _clear_auth_cookies(response)
    return {"reset": True}


@router.post("/refresh", response_model=TokenResponse)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    _require_local_auth_surface()
    _require_secure_auth_transport(request)
    raw = request.cookies.get(settings.refresh_cookie_name)
    if not raw:
        raise HTTPException(status_code=401, detail="Refresh token required")
    session = db.scalar(select(UserSession).where(UserSession.refresh_token_hash == hash_token(raw)))
    now = datetime.now(timezone.utc)
    if not session or session.revoked_at is not None or session.expires_at <= now:
        raise HTTPException(status_code=401, detail="Refresh session expired or revoked")
    user = db.get(User, session.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Inactive or unknown user")
    _require_verified_email(user)

    session.revoked_at = now
    new_refresh, new_session = _new_session(user, request, db)
    new_session.trusted_device_id = session.trusted_device_id
    new_session.risk_score = session.risk_score
    new_session.risk_level = session.risk_level
    new_session.new_device = False
    new_session.last_seen_at = now
    if session.trusted_device_id:
        device = db.get(TrustedDevice, session.trusted_device_id)
        if device is not None and device.revoked_at is None:
            device.last_seen_at = now
            device.last_ip_address = request_client_ip(request)
    access = create_access_token(str(user.id), {"sv": user.session_version, "sid": str(new_session.id)})
    db.add(AuditLog(actor_user_id=user.id, action="auth.refresh", resource_type="session", resource_id=str(new_session.id)))
    db.commit()
    _set_auth_cookies(response, access, new_refresh, request)
    return TokenResponse(access_token=access, user=_user_payload(user))


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    raw = request.cookies.get(settings.refresh_cookie_name)
    if raw:
        session = db.scalar(select(UserSession).where(UserSession.refresh_token_hash == hash_token(raw)))
        if session and session.revoked_at is None:
            session.revoked_at = datetime.now(timezone.utc)
            db.add(AuditLog(actor_user_id=session.user_id, action="auth.logout", resource_type="session", resource_id=str(session.id)))
            db.commit()
    _clear_auth_cookies(response)


@router.get("/me")
def me(current: User = Depends(get_current_user)):
    return _user_payload(current)


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _require_local_auth_surface()
    rows = db.scalars(select(UserSession).where(UserSession.user_id == current.id).order_by(UserSession.created_at.desc())).all()
    return [
        SessionOut(
            id=str(row.id),
            created_at=row.created_at.isoformat(),
            expires_at=row.expires_at.isoformat(),
            user_agent=row.user_agent,
            ip_address=row.ip_address,
            revoked=row.revoked_at is not None,
            trusted_device_id=str(row.trusted_device_id) if row.trusted_device_id else None,
            risk_score=row.risk_score,
            risk_level=row.risk_level,
            new_device=row.new_device,
            last_seen_at=row.last_seen_at.isoformat() if row.last_seen_at else None,
        )
        for row in rows
    ]


@router.delete("/sessions/{session_id}", status_code=204)
def revoke_session(session_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _require_local_auth_surface()
    session = db.get(UserSession, session_id)
    if not session or session.user_id != current.id:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.revoked_at is None:
        session.revoked_at = datetime.now(timezone.utc)
        db.add(AuditLog(actor_user_id=current.id, action="auth.session.revoke", resource_type="session", resource_id=str(session.id)))
        db.commit()


@router.delete("/sessions", status_code=204)
def revoke_all_sessions(response: Response, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _require_local_auth_surface()
    _revoke_all_sessions(db, current.id)
    current.session_version += 1
    db.add(AuditLog(actor_user_id=current.id, action="auth.sessions.revoke_all", resource_type="user", resource_id=str(current.id)))
    db.commit()
    _clear_auth_cookies(response)


@router.get("/devices", response_model=list[TrustedDeviceOut])
def list_trusted_devices(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _require_local_auth_surface()
    rows = db.scalars(
        select(TrustedDevice)
        .where(TrustedDevice.user_id == current.id)
        .order_by(TrustedDevice.last_seen_at.desc())
    ).all()
    return [
        TrustedDeviceOut(
            id=str(row.id),
            label=row.label,
            first_seen_at=row.first_seen_at.isoformat(),
            last_seen_at=row.last_seen_at.isoformat(),
            first_ip_address=row.first_ip_address,
            last_ip_address=row.last_ip_address,
            first_user_agent=row.first_user_agent,
            trusted=row.trusted_at is not None and row.revoked_at is None,
            revoked=row.revoked_at is not None,
        )
        for row in rows
    ]


@router.post("/devices/{device_id}/trust", response_model=TrustedDeviceOut)
def trust_device(
    device_id: UUID,
    payload: TrustedDeviceLabelRequest | None = None,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    _require_local_auth_surface()
    device = db.get(TrustedDevice, device_id)
    if device is None or device.user_id != current.id or device.revoked_at is not None:
        raise HTTPException(status_code=404, detail="Device not found")
    device.trusted_at = device.trusted_at or datetime.now(timezone.utc)
    if payload is not None:
        device.label = payload.label.strip()
    db.add(AuditLog(
        actor_user_id=current.id,
        action="auth.device.trust",
        resource_type="trusted_device",
        resource_id=str(device.id),
        metadata_json=json.dumps({"label": device.label}, separators=(",", ":")),
    ))
    db.commit()
    db.refresh(device)
    return TrustedDeviceOut(
        id=str(device.id),
        label=device.label,
        first_seen_at=device.first_seen_at.isoformat(),
        last_seen_at=device.last_seen_at.isoformat(),
        first_ip_address=device.first_ip_address,
        last_ip_address=device.last_ip_address,
        first_user_agent=device.first_user_agent,
        trusted=True,
        revoked=False,
    )


@router.delete("/devices/{device_id}", status_code=204)
def revoke_device(device_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _require_local_auth_surface()
    device = db.get(TrustedDevice, device_id)
    if device is None or device.user_id != current.id:
        raise HTTPException(status_code=404, detail="Device not found")
    now = datetime.now(timezone.utc)
    device.revoked_at = device.revoked_at or now
    db.execute(
        update(UserSession)
        .where(
            UserSession.user_id == current.id,
            UserSession.trusted_device_id == device.id,
            UserSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    db.add(AuditLog(actor_user_id=current.id, action="auth.device.revoke", resource_type="trusted_device", resource_id=str(device.id)))
    db.commit()


@router.get("/recovery-codes", response_model=RecoveryCodeStatus)
def recovery_code_status(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _require_local_auth_surface()
    rows = db.scalars(select(RecoveryCode).where(RecoveryCode.user_id == current.id)).all()
    remaining = sum(1 for row in rows if row.used_at is None)
    return RecoveryCodeStatus(remaining=remaining, generated=bool(rows))


@router.post("/recovery-codes/regenerate", response_model=RecoveryCodesResponse)
def regenerate_recovery_codes(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _require_local_auth_surface()
    if not current.mfa_enabled:
        raise HTTPException(status_code=409, detail="Enable MFA before generating recovery codes")
    previous = db.scalars(select(RecoveryCode).where(RecoveryCode.user_id == current.id)).all()
    for row in previous:
        db.delete(row)
    codes = generate_recovery_codes()
    for value in codes:
        db.add(RecoveryCode(user_id=current.id, code_hash=hash_token(normalize_recovery_code(value))))
    db.add(AuditLog(
        actor_user_id=current.id,
        action="auth.recovery_codes.regenerate",
        resource_type="user",
        resource_id=str(current.id),
        metadata_json=json.dumps({"count": len(codes)}, separators=(",", ":")),
    ))
    db.commit()
    return RecoveryCodesResponse(codes=codes, remaining=len(codes))


@router.get("/passkeys", response_model=list[PasskeyOut])
def list_passkeys(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _require_local_auth_surface()
    rows = db.scalars(
        select(PasskeyCredential)
        .where(PasskeyCredential.user_id == current.id)
        .order_by(PasskeyCredential.created_at.desc())
    ).all()
    return [
        PasskeyOut(
            id=str(row.id),
            name=row.name,
            created_at=row.created_at.isoformat(),
            last_used_at=row.last_used_at.isoformat() if row.last_used_at else None,
            device_type=row.device_type,
            backed_up=row.backed_up,
            revoked=row.revoked_at is not None,
        )
        for row in rows
    ]


@router.post("/passkeys/register/options")
def passkey_register_options(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _require_local_auth_surface()
    if current.central_auth_enforced:
        raise HTTPException(status_code=409, detail="Passkeys for this account are managed by Ithute Central Authentication")
    try:
        return passkey_registration_options(db, current)
    except PasskeyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/passkeys/register/verify", response_model=PasskeyOut, status_code=201)
def passkey_register_verify(
    payload: PasskeyRegistrationRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    _require_local_auth_surface()
    if current.central_auth_enforced:
        raise HTTPException(status_code=409, detail="Passkeys for this account are managed by Ithute Central Authentication")
    if not verify_password(payload.current_password, current.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    try:
        item = verify_passkey_registration(
            db,
            user=current,
            flow_id=payload.flow_id,
            credential=payload.credential,
            name=payload.name,
        )
    except PasskeyError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.add(AuditLog(
        actor_user_id=current.id,
        action="auth.passkey.register",
        resource_type="passkey",
        resource_id=str(item.id),
        metadata_json=json.dumps({"name": item.name, "device_type": item.device_type, "backed_up": item.backed_up}, separators=(",", ":")),
    ))
    db.commit()
    db.refresh(item)
    return PasskeyOut(
        id=str(item.id),
        name=item.name,
        created_at=item.created_at.isoformat(),
        last_used_at=None,
        device_type=item.device_type,
        backed_up=item.backed_up,
        revoked=False,
    )


@router.delete("/passkeys/{passkey_id}", status_code=204)
def revoke_passkey(passkey_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _require_local_auth_surface()
    item = db.get(PasskeyCredential, passkey_id)
    if item is None or item.user_id != current.id:
        raise HTTPException(status_code=404, detail="Passkey not found")
    if item.revoked_at is None:
        item.revoked_at = datetime.now(timezone.utc)
        db.add(AuditLog(actor_user_id=current.id, action="auth.passkey.revoke", resource_type="passkey", resource_id=str(item.id)))
        db.commit()


@router.post("/passkeys/auth/options")
def passkey_auth_options():
    _require_local_auth_surface()
    try:
        return passkey_authentication_options()
    except PasskeyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/passkeys/auth/verify", response_model=TokenResponse)
def passkey_auth_verify(
    payload: PasskeyAuthenticationRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    _require_local_auth_surface()
    _require_secure_auth_transport(request)
    enforce_login_rate_limit(request, "passkey")
    try:
        user, passkey = verify_passkey_authentication(
            db,
            flow_id=payload.flow_id,
            credential=payload.credential,
        )
    except PasskeyError as exc:
        db.rollback()
        record_login_failure(request, "passkey")
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    _require_verified_email(user)
    if user.central_auth_enforced:
        db.rollback()
        raise HTTPException(
            status_code=403,
            detail={"code": "CENTRAL_AUTH_REQUIRED", "message": "This account requires Ithute Central Authentication."},
        )

    clear_login_failures("passkey")
    now = datetime.now(timezone.utc)
    passkey.last_used_at = now
    device, device_token, is_new_device = resolve_or_create_device(db, user=user, request=request)
    risk = assess_login_risk(device=device, request=request, is_new_device=is_new_device, mfa_verified=True)
    refresh_token, session = _new_session(user, request, db)
    session.trusted_device_id = device.id
    session.risk_score = int(risk["score"])
    session.risk_level = str(risk["level"])
    session.new_device = bool(is_new_device)
    session.last_seen_at = now
    access = create_access_token(str(user.id), {"sv": user.session_version, "sid": str(session.id)})
    db.add(AuditLog(
        actor_user_id=user.id,
        action="auth.passkey.login",
        resource_type="session",
        resource_id=str(session.id),
        metadata_json=json.dumps({
            "passkey_id": str(passkey.id),
            "risk_score": risk["score"],
            "risk_level": risk["level"],
            "new_device": is_new_device,
            "trusted_device_id": str(device.id),
            "signals": risk["signals"],
        }, separators=(",", ":")),
    ))
    if is_new_device:
        db.add(AuditLog(
            actor_user_id=user.id,
            action="auth.device.new",
            resource_type="trusted_device",
            resource_id=str(device.id),
            metadata_json=json.dumps({
                "source": "passkey",
                "ip_address": request_client_ip(request),
                "user_agent": request.headers.get("user-agent"),
                "risk_score": risk["score"],
                "risk_level": risk["level"],
            }, separators=(",", ":")),
        ))
    db.commit()
    _set_auth_cookies(response, access, refresh_token, request)
    _set_device_cookie(response, device_token, request)

    if is_new_device:
        try:
            ip = request_client_ip(request)
            agent = request.headers.get("user-agent") or "Unknown browser or device"
            send_system_email(
                user.email,
                "New passkey sign-in to your Ithute account",
                "A new device signed in to your Ithute account using a passkey.\n\n"
                f"Device: {agent}\nIP: {ip}\nRisk: {risk['level']} ({risk['score']}/100)\n\n"
                "If this was not you, open Ithute Security Center and revoke the passkey, device and active sessions.",
                "<html><body style=\"font-family:Arial,sans-serif;color:#173228\"><div style=\"max-width:560px;margin:auto;padding:28px\">"
                "<div style=\"font-size:13px;font-weight:700;color:#285b55\">Ithute Identity &amp; Account Security</div>"
                "<h2>New passkey sign-in</h2>"
                f"<p><strong>Device:</strong> {escape(agent)}</p><p><strong>IP:</strong> {escape(ip)}</p>"
                f"<p><strong>Risk:</strong> {escape(str(risk['level']))} ({int(risk['score'])}/100)</p>"
                "<p>If this was not you, revoke the passkey, device and active sessions immediately.</p></div></body></html>",
            )
        except RuntimeError:
            pass

    return TokenResponse(access_token=access, user=_user_payload(user))


@router.get("/security-events", response_model=list[SecurityEventOut])
def security_events(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.actor_user_id == current.id, AuditLog.action.like("auth.%"))
        .order_by(AuditLog.created_at.desc())
        .limit(100)
    ).all()
    result = []
    for row in rows:
        metadata = {}
        if row.metadata_json:
            try:
                parsed = json.loads(row.metadata_json)
                if isinstance(parsed, dict):
                    metadata = parsed
            except (TypeError, ValueError, json.JSONDecodeError):
                metadata = {}
        result.append(SecurityEventOut(
            id=str(row.id),
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            created_at=row.created_at.isoformat(),
            metadata=metadata,
        ))
    return result


@router.post("/mfa/setup", response_model=MfaSetupResponse)
def mfa_setup(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _require_local_auth_surface()
    if current.mfa_enabled:
        raise HTTPException(status_code=409, detail="Disable existing MFA before starting a new setup")
    secret = generate_totp_secret()
    current.mfa_secret = encrypt_secret(secret)
    db.add(AuditLog(actor_user_id=current.id, action="auth.mfa.setup", resource_type="user", resource_id=str(current.id)))
    db.commit()
    return MfaSetupResponse(secret=secret, provisioning_uri=provisioning_uri(secret, current.email))


@router.post("/mfa/enable", status_code=204)
def mfa_enable(payload: MfaCodeRequest, response: Response, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _require_local_auth_surface()
    if not current.mfa_secret:
        raise HTTPException(status_code=400, detail="MFA setup required")
    try:
        secret = decrypt_secret(current.mfa_secret)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="MFA setup is invalid") from exc
    if not verify_totp(secret, payload.code):
        raise HTTPException(status_code=400, detail="Invalid MFA code")
    current.mfa_enabled = True
    current.session_version += 1
    _revoke_all_sessions(db, current.id)
    db.add(AuditLog(actor_user_id=current.id, action="auth.mfa.enable", resource_type="user", resource_id=str(current.id)))
    db.commit()
    _clear_auth_cookies(response)


@router.post("/mfa/disable", status_code=204)
def mfa_disable(payload: MfaCodeRequest, response: Response, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _require_local_auth_surface()
    if not current.mfa_enabled or not current.mfa_secret:
        raise HTTPException(status_code=400, detail="MFA is not enabled")
    try:
        secret = decrypt_secret(current.mfa_secret)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="MFA setup is invalid") from exc
    if not verify_totp(secret, payload.code):
        raise HTTPException(status_code=400, detail="Invalid MFA code")
    current.mfa_enabled = False
    current.mfa_secret = None
    current.session_version += 1
    _revoke_all_sessions(db, current.id)
    db.add(AuditLog(actor_user_id=current.id, action="auth.mfa.disable", resource_type="user", resource_id=str(current.id)))
    db.commit()
    _clear_auth_cookies(response)


@router.post("/password", status_code=204)
def change_password(
    payload: PasswordChangeRequest,
    response: Response,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    _require_local_auth_surface()
    if not verify_password(payload.current_password, current.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="New password must be different")
    current.password_hash = hash_password(payload.new_password)
    current.session_version += 1
    _revoke_all_sessions(db, current.id)
    db.add(AuditLog(actor_user_id=current.id, action="auth.password.change", resource_type="user", resource_id=str(current.id)))
    db.commit()
    _clear_auth_cookies(response)
