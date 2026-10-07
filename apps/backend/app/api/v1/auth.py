import secrets
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
from app.models import AuditLog, PasswordResetToken, User, UserSession
from app.schemas.auth import (
    LoginRequest,
    MfaCodeRequest,
    MfaSetupResponse,
    PasswordChangeRequest,
    PasswordResetComplete,
    PasswordResetRequest,
    SessionOut,
    TokenResponse,
)
from app.services.auth_security import (
    clear_login_failures,
    enforce_login_rate_limit,
    enforce_password_reset_rate_limit,
    record_login_failure,
)
from app.services.ithute_auth import ithute_auth_enabled
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
    if user.mfa_enabled:
        if not payload.mfa_code:
            raise HTTPException(status_code=401, detail="MFA code required")
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

    clear_login_failures(email)
    refresh_token, session = _new_session(user, request, db)
    access = create_access_token(str(user.id), {"sv": user.session_version, "sid": str(session.id)})
    db.add(AuditLog(actor_user_id=user.id, action="auth.login", resource_type="session", resource_id=str(session.id)))
    db.commit()
    _set_auth_cookies(response, access, refresh_token, request)
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
