import ipaddress
import json
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .models import AuditEvent, AuthEventOutbox, AuthSession, MfaRecoveryCode, User, utcnow
from .security import decrypt_totp_secret, hash_recovery_code, verify_totp


_FAILED_LOGIN_EVENT_TYPES = {
    "login_failed",
    "mfa_challenge_failed",
    "oidc_login_failed",
    "oidc_mfa_failed",
}


def _trusted_proxy(peer: str | None, settings: Settings) -> bool:
    if not peer:
        return False
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return False
    return any(address in network for network in settings.trusted_proxy_networks)


def client_ip(request: Any, settings: Settings | None = None) -> str | None:
    if request is None:
        return None
    config = settings or get_settings()
    peer = str(request.client.host)[:64] if request.client else None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and _trusted_proxy(peer, config):
        values = [value.strip() for value in forwarded.split(",") if value.strip()]
        if values:
            for value in reversed(values):
                candidate = value[:64]
                try:
                    address = ipaddress.ip_address(candidate)
                except ValueError:
                    continue
                if not any(address in network for network in config.trusted_proxy_networks):
                    return candidate
    return peer


def record_audit(
    db: Session,
    *,
    event_type: str,
    user: User | None = None,
    success: bool = True,
    client_id: str | None = None,
    request: Any = None,
    details: dict[str, object] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        user_id=user.id if user else None,
        event_type=event_type,
        success=success,
        client_id=client_id,
        ip_address=client_ip(request),
        user_agent=(request.headers.get("user-agent")[:2000] if request and request.headers.get("user-agent") else None),
        details_json=json.dumps(details, separators=(",", ":"), sort_keys=True) if details else None,
    )
    db.add(event)
    return event


def enqueue_auth_event(
    db: Session,
    *,
    event_type: str,
    user_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    client_id: str | None = None,
    details: dict[str, object] | None = None,
) -> AuthEventOutbox:
    event = AuthEventOutbox(
        event_type=event_type,
        subject_user_id=user_id,
        session_id=session_id,
        client_id=client_id,
        payload_json=json.dumps(details or {}, separators=(",", ":"), sort_keys=True),
    )
    db.add(event)
    return event


def login_rate_limited(db: Session, *, request: Any, settings: Settings) -> bool:
    ip_address = client_ip(request, settings)
    if not ip_address or settings.login_rate_max_failures_per_ip <= 0:
        return False
    cutoff = utcnow() - timedelta(seconds=settings.login_rate_window_seconds)
    failures = db.scalar(
        select(func.count(AuditEvent.id)).where(
            AuditEvent.ip_address == ip_address,
            AuditEvent.success.is_(False),
            AuditEvent.event_type.in_(_FAILED_LOGIN_EVENT_TYPES),
            AuditEvent.created_at >= cutoff,
        )
    )
    return int(failures or 0) >= settings.login_rate_max_failures_per_ip


def recovery_request_rate_limited(
    db: Session,
    *,
    request: Any,
    user: User | None,
    settings: Settings,
) -> bool:
    cutoff = utcnow() - timedelta(seconds=settings.recovery_rate_window_seconds)
    ip_address = client_ip(request, settings)
    if ip_address and settings.recovery_max_requests_per_ip > 0:
        ip_count = db.scalar(
            select(func.count(AuditEvent.id)).where(
                AuditEvent.ip_address == ip_address,
                AuditEvent.event_type == "password_reset_requested",
                AuditEvent.created_at >= cutoff,
            )
        )
        if int(ip_count or 0) >= settings.recovery_max_requests_per_ip:
            return True
    if user is not None and settings.recovery_max_requests_per_user > 0:
        user_count = db.scalar(
            select(func.count(AuditEvent.id)).where(
                AuditEvent.user_id == user.id,
                AuditEvent.event_type == "password_reset_requested",
                AuditEvent.created_at >= cutoff,
            )
        )
        if int(user_count or 0) >= settings.recovery_max_requests_per_user:
            return True
    return False


def verification_request_rate_limited(db: Session, *, user: User, settings: Settings) -> bool:
    if settings.verification_max_requests_per_user <= 0:
        return False
    cutoff = utcnow() - timedelta(seconds=settings.verification_rate_window_seconds)
    count = db.scalar(
        select(func.count(AuditEvent.id)).where(
            AuditEvent.user_id == user.id,
            AuditEvent.event_type.in_({"email_verification_requested", "phone_verification_requested"}),
            AuditEvent.created_at >= cutoff,
        )
    )
    return int(count or 0) >= settings.verification_max_requests_per_user


def verification_confirmation_rate_limited(db: Session, *, user_id: uuid.UUID, settings: Settings) -> bool:
    if settings.verification_confirm_max_failures_per_user <= 0:
        return False
    cutoff = utcnow() - timedelta(seconds=settings.verification_confirm_rate_window_seconds)
    count = db.scalar(
        select(func.count(AuditEvent.id)).where(
            AuditEvent.user_id == user_id,
            AuditEvent.success.is_(False),
            AuditEvent.event_type.in_({"email_verification_failed", "phone_verification_failed"}),
            AuditEvent.created_at >= cutoff,
        )
    )
    return int(count or 0) >= settings.verification_confirm_max_failures_per_user


def verify_second_factor(
    db: Session,
    *,
    user: User,
    code: str | None,
    settings: Settings,
) -> bool:
    if not user.totp_enabled:
        return True
    if not code:
        return False

    if user.totp_secret_encrypted:
        secret = decrypt_totp_secret(user.totp_secret_encrypted, settings)
        if verify_totp(secret, code):
            return True

    code_hash = hash_recovery_code(code)
    recovery = db.scalar(
        select(MfaRecoveryCode).where(
            MfaRecoveryCode.user_id == user.id,
            MfaRecoveryCode.code_hash == code_hash,
            MfaRecoveryCode.used_at.is_(None),
        )
    )
    if recovery is None:
        return False
    recovery.used_at = utcnow()
    return True


def revoke_sessions(
    db: Session,
    *,
    user_id: uuid.UUID,
    reason: str,
    except_session_id: uuid.UUID | None = None,
) -> int:
    rows = db.scalars(
        select(AuthSession).where(
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
        )
    ).all()
    now = utcnow()
    count = 0
    for row in rows:
        if except_session_id is not None and row.id == except_session_id:
            continue
        row.revoked_at = now
        row.revoked_reason = reason[:160]
        count += 1
    return count
