from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import quote

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .db import get_db
from .delivery import DeliveryUnavailable, send_email, send_sms
from .models import AuditEvent, AuthSession, MfaRecoveryCode, SecurityToken, User, utcnow
from .schemas import (
    AuditEventResponse,
    MfaConfirmRequest,
    MfaDisableRequest,
    MfaEnrollRequest,
    MfaEnrollResponse,
    MfaRecoveryCodesResponse,
    PasswordChangeRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    SessionResponse,
    VerificationConfirmRequest,
    VerificationRequest,
)
from .security import (
    decode_access_token,
    decrypt_totp_secret,
    encrypt_totp_secret,
    hash_password,
    hash_recovery_code,
    hash_security_token,
    new_numeric_code,
    new_recovery_codes,
    new_security_token,
    new_totp_secret,
    normalize_email,
    normalize_phone,
    totp_provisioning_uri,
    verify_password,
    verify_totp,
)
from .security_service import (
    record_audit,
    recovery_request_rate_limited,
    revoke_sessions,
    verification_confirmation_rate_limited,
    verification_request_rate_limited,
    verify_second_factor,
)


router = APIRouter(prefix="/v1/account", tags=["account-security"])
bearer = HTTPBearer(auto_error=False)


@dataclass
class AuthContext:
    user: User
    session: AuthSession
    claims: dict[str, object]


def authenticated_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthContext:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    try:
        claims = decode_access_token(credentials.credentials, settings)
        if claims.get("token_use") != "access":
            raise ValueError("wrong token type")
        user_id = uuid.UUID(str(claims["sub"]))
        session_id = uuid.UUID(str(claims["sid"]))
        audience = claims.get("aud")
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token") from None

    session = db.get(AuthSession, session_id)
    if (
        session is None
        or session.user_id != user_id
        or session.revoked_at is not None
        or session.expires_at <= utcnow()
        or session.client_id != audience
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session expired")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user unavailable")
    session.last_seen_at = utcnow()
    db.commit()
    return AuthContext(user=user, session=session, claims=claims)


def _find_user(db: Session, identifier: str) -> User | None:
    email = normalize_email(identifier)
    phone = normalize_phone(identifier)
    return db.scalar(select(User).where(or_(User.email == email, User.phone == phone)))


def _active_token(db: Session, *, token_hash: str, purpose: str) -> SecurityToken | None:
    row = db.scalar(
        select(SecurityToken)
        .where(
            SecurityToken.token_hash == token_hash,
            SecurityToken.purpose == purpose,
        )
        .with_for_update()
    )
    if row is None or row.consumed_at is not None or row.expires_at <= utcnow():
        return None
    return row


def _consume_active_tokens(db: Session, *, user_id: uuid.UUID, purpose: str) -> None:
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


def _deliver_reset(settings: Settings, user: User, token: str) -> None:
    link = f"{settings.account_base_url.rstrip('/')}/reset-password?token={quote(token)}"
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


@router.post("/password/change", status_code=204)
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    context: AuthContext = Depends(authenticated_context),
    db: Session = Depends(get_db),
) -> None:
    if not verify_password(payload.current_password, context.user.password_hash):
        record_audit(db, event_type="password_change", user=context.user, success=False, request=request)
        db.commit()
        raise HTTPException(status_code=401, detail="invalid credentials")
    context.user.password_hash = hash_password(payload.new_password)
    context.user.password_changed_at = utcnow()
    context.user.security_version += 1
    revoke_sessions(db, user_id=context.user.id, reason="password changed", except_session_id=context.session.id)
    record_audit(db, event_type="password_change", user=context.user, request=request)
    db.commit()


@router.post("/password/reset/request", status_code=202)
def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    user = _find_user(db, payload.identifier)
    if recovery_request_rate_limited(db, request=request, user=user, settings=settings):
        record_audit(db, event_type="password_reset_rate_limited", user=user, success=False, request=request)
        db.commit()
        return {"status": "accepted"}

    record_audit(db, event_type="password_reset_requested", user=user, request=request)
    if user is None or not user.is_active:
        db.commit()
        return {"status": "accepted"}

    _consume_active_tokens(db, user_id=user.id, purpose="password_reset")
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
    return {"status": "accepted"}


@router.post("/password/reset/confirm", status_code=204)
def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> None:
    row = _active_token(db, token_hash=hash_security_token(payload.token), purpose="password_reset")
    if row is None:
        raise HTTPException(status_code=400, detail="invalid or expired reset token")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail="invalid or expired reset token")
    row.consumed_at = utcnow()
    user.password_hash = hash_password(payload.new_password)
    user.password_changed_at = utcnow()
    user.security_version += 1
    user.failed_login_attempts = 0
    user.locked_until = None
    revoke_sessions(db, user_id=user.id, reason="password reset")
    record_audit(db, event_type="password_reset_completed", user=user, request=request)
    db.commit()


@router.post("/verification/request", status_code=202)
def request_verification(
    payload: VerificationRequest,
    request: Request,
    context: AuthContext = Depends(authenticated_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    target = context.user.email if payload.channel == "email" else context.user.phone
    if not target:
        raise HTTPException(status_code=400, detail=f"no {payload.channel} on account")
    if payload.channel == "email" and context.user.email_verified:
        return {"status": "already_verified"}
    if payload.channel == "phone" and context.user.phone_verified:
        return {"status": "already_verified"}
    if verification_request_rate_limited(db, user=context.user, settings=settings):
        record_audit(
            db,
            event_type=f"{payload.channel}_verification_rate_limited",
            user=context.user,
            success=False,
            request=request,
        )
        db.commit()
        raise HTTPException(status_code=429, detail="too many verification requests")

    code = new_numeric_code()
    purpose = f"verify_{payload.channel}"
    _consume_active_tokens(db, user_id=context.user.id, purpose=purpose)
    db.add(
        SecurityToken(
            user_id=context.user.id,
            purpose=purpose,
            token_hash=hash_security_token(f"{context.user.id}:{code}"),
            target=target,
            expires_at=utcnow() + timedelta(minutes=settings.verification_code_minutes),
        )
    )
    record_audit(db, event_type=f"{payload.channel}_verification_requested", user=context.user, request=request)
    db.commit()
    try:
        if payload.channel == "email":
            send_email(settings, recipient=target, subject="Verify your !thute email", body=f"Your !thute verification code is {code}.")
        else:
            send_sms(settings, phone=target, message=f"Your !thute verification code is {code}.")
    except Exception as exc:
        record_audit(db, event_type=f"{payload.channel}_verification_delivery", user=context.user, success=False, request=request)
        db.commit()
        raise HTTPException(status_code=503, detail="verification delivery is unavailable") from exc
    return {"status": "sent"}


@router.post("/verification/confirm", status_code=204)
def confirm_verification(
    payload: VerificationConfirmRequest,
    request: Request,
    context: AuthContext = Depends(authenticated_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    if verification_confirmation_rate_limited(db, user_id=context.user.id, settings=settings):
        record_audit(
            db,
            event_type=f"{payload.channel}_verification_confirm_rate_limited",
            user=context.user,
            success=False,
            request=request,
        )
        db.commit()
        raise HTTPException(status_code=429, detail="too many verification attempts")

    purpose = f"verify_{payload.channel}"
    token_hash = hash_security_token(f"{context.user.id}:{payload.code.strip()}")
    row = _active_token(db, token_hash=token_hash, purpose=purpose)
    if row is None or row.user_id != context.user.id:
        record_audit(
            db,
            event_type=f"{payload.channel}_verification_failed",
            user=context.user,
            success=False,
            request=request,
        )
        db.commit()
        raise HTTPException(status_code=400, detail="invalid or expired verification code")
    row.consumed_at = utcnow()
    if payload.channel == "email":
        context.user.email_verified = True
    else:
        context.user.phone_verified = True
    record_audit(db, event_type=f"{payload.channel}_verified", user=context.user, request=request)
    db.commit()


@router.post("/mfa/enroll", response_model=MfaEnrollResponse)
def enroll_mfa(
    payload: MfaEnrollRequest,
    request: Request,
    context: AuthContext = Depends(authenticated_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MfaEnrollResponse:
    if context.user.totp_enabled:
        raise HTTPException(status_code=409, detail="MFA is already enabled; disable it with fresh password and MFA proof before replacing it")
    if not verify_password(payload.password, context.user.password_hash):
        record_audit(db, event_type="mfa_enrollment_started", user=context.user, success=False, request=request)
        db.commit()
        raise HTTPException(status_code=401, detail="invalid credentials")
    secret = new_totp_secret()
    context.user.totp_secret_encrypted = encrypt_totp_secret(secret, settings)
    record_audit(db, event_type="mfa_enrollment_started", user=context.user, request=request)
    db.commit()
    account_name = context.user.email or context.user.phone or str(context.user.id)
    return MfaEnrollResponse(
        secret=secret,
        provisioning_uri=totp_provisioning_uri(secret, account_name=account_name, issuer_name=settings.totp_issuer_name),
    )


@router.post("/mfa/confirm", response_model=MfaRecoveryCodesResponse)
def confirm_mfa(
    payload: MfaConfirmRequest,
    request: Request,
    context: AuthContext = Depends(authenticated_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MfaRecoveryCodesResponse:
    if context.user.totp_enabled:
        raise HTTPException(status_code=409, detail="MFA is already enabled")
    if not context.user.totp_secret_encrypted:
        raise HTTPException(status_code=400, detail="MFA enrollment has not started")
    secret = decrypt_totp_secret(context.user.totp_secret_encrypted, settings)
    if not verify_totp(secret, payload.code):
        record_audit(db, event_type="mfa_enrollment_confirmed", user=context.user, success=False, request=request)
        db.commit()
        raise HTTPException(status_code=400, detail="invalid authenticator code")
    codes = new_recovery_codes()
    db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == context.user.id))
    for code in codes:
        db.add(MfaRecoveryCode(user_id=context.user.id, code_hash=hash_recovery_code(code)))
    context.user.totp_enabled = True
    context.user.security_version += 1
    revoke_sessions(db, user_id=context.user.id, reason="MFA enabled", except_session_id=context.session.id)
    record_audit(db, event_type="mfa_enabled", user=context.user, request=request)
    db.commit()
    return MfaRecoveryCodesResponse(recovery_codes=codes)


@router.post("/mfa/recovery-codes", response_model=MfaRecoveryCodesResponse)
def regenerate_recovery_codes(
    payload: MfaConfirmRequest,
    request: Request,
    context: AuthContext = Depends(authenticated_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MfaRecoveryCodesResponse:
    if not context.user.totp_enabled or not context.user.totp_secret_encrypted:
        raise HTTPException(status_code=400, detail="MFA is not enabled")
    secret = decrypt_totp_secret(context.user.totp_secret_encrypted, settings)
    if not verify_totp(secret, payload.code):
        raise HTTPException(status_code=400, detail="invalid authenticator code")
    codes = new_recovery_codes()
    db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == context.user.id))
    for code in codes:
        db.add(MfaRecoveryCode(user_id=context.user.id, code_hash=hash_recovery_code(code)))
    record_audit(db, event_type="mfa_recovery_codes_regenerated", user=context.user, request=request)
    db.commit()
    return MfaRecoveryCodesResponse(recovery_codes=codes)


@router.post("/mfa/disable", status_code=204)
def disable_mfa(
    payload: MfaDisableRequest,
    request: Request,
    context: AuthContext = Depends(authenticated_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    if not verify_password(payload.password, context.user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    if context.user.totp_enabled and not verify_second_factor(db, user=context.user, code=payload.code, settings=settings):
        raise HTTPException(status_code=401, detail="invalid MFA code")
    context.user.totp_enabled = False
    context.user.totp_secret_encrypted = None
    context.user.security_version += 1
    db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == context.user.id))
    revoke_sessions(db, user_id=context.user.id, reason="MFA disabled", except_session_id=context.session.id)
    record_audit(db, event_type="mfa_disabled", user=context.user, request=request)
    db.commit()


@router.get("/sessions", response_model=list[SessionResponse])
def list_sessions(
    context: AuthContext = Depends(authenticated_context),
    db: Session = Depends(get_db),
) -> list[SessionResponse]:
    rows = db.scalars(
        select(AuthSession).where(AuthSession.user_id == context.user.id).order_by(AuthSession.created_at.desc()).limit(100)
    ).all()
    return [
        SessionResponse(
            id=str(row.id),
            client_id=row.client_id,
            ip_address=row.ip_address,
            user_agent=row.user_agent,
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
            expires_at=row.expires_at,
            revoked_at=row.revoked_at,
            current=row.id == context.session.id,
        )
        for row in rows
    ]


@router.delete("/sessions/{session_id}", status_code=204)
def revoke_session(
    session_id: uuid.UUID,
    request: Request,
    context: AuthContext = Depends(authenticated_context),
    db: Session = Depends(get_db),
) -> None:
    row = db.get(AuthSession, session_id)
    if row is None or row.user_id != context.user.id:
        raise HTTPException(status_code=404, detail="session not found")
    if row.revoked_at is None:
        row.revoked_at = utcnow()
        row.revoked_reason = "revoked by user"
    record_audit(db, event_type="session_revoked", user=context.user, client_id=row.client_id, request=request, details={"session_id": str(row.id)})
    db.commit()


@router.post("/sessions/revoke-others")
def revoke_other_sessions(
    request: Request,
    context: AuthContext = Depends(authenticated_context),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    count = revoke_sessions(db, user_id=context.user.id, reason="logout other devices", except_session_id=context.session.id)
    record_audit(db, event_type="other_sessions_revoked", user=context.user, request=request, details={"count": count})
    db.commit()
    return {"revoked": count}


@router.get("/security-events", response_model=list[AuditEventResponse])
def security_events(
    context: AuthContext = Depends(authenticated_context),
    db: Session = Depends(get_db),
) -> list[AuditEventResponse]:
    rows = db.scalars(
        select(AuditEvent).where(AuditEvent.user_id == context.user.id).order_by(AuditEvent.created_at.desc()).limit(100)
    ).all()
    result: list[AuditEventResponse] = []
    for row in rows:
        details = None
        if row.details_json:
            try:
                parsed = json.loads(row.details_json)
                details = parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                details = None
        result.append(
            AuditEventResponse(
                id=str(row.id),
                event_type=row.event_type,
                success=row.success,
                client_id=row.client_id,
                ip_address=row.ip_address,
                details=details,
                created_at=row.created_at,
            )
        )
    return result
