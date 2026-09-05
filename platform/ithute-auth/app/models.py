import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, event, inspect, select
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True, index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    phone_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    totp_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    security_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    password_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    sessions: Mapped[list["AuthSession"]] = relationship(back_populates="user")
    devices: Mapped[list["Device"]] = relationship(back_populates="user")
    recovery_codes: Mapped[list["MfaRecoveryCode"]] = relationship(back_populates="user")
    passkeys: Mapped[list["PasskeyCredential"]] = relationship(back_populates="user")


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    client_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AuthorizationCode(Base):
    __tablename__ = "authorization_codes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[str] = mapped_column(String(120), index=True)
    redirect_uri: Mapped[str] = mapped_column(Text)
    code_challenge: Mapped[str] = mapped_column(String(128))
    nonce: Mapped[str] = mapped_column(String(512))
    scope: Mapped[str] = mapped_column(String(512), default="openid", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[str] = mapped_column(String(120), index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(160), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="sessions")


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("user_id", "device_key", name="uq_device_user_key"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    device_key: Mapped[str] = mapped_column(String(200), index=True)
    platform: Mapped[str] = mapped_column(String(32))
    label: Mapped[str | None] = mapped_column(String(160), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="devices")


class SecurityToken(Base):
    __tablename__ = "security_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(40), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    target: Mapped[str | None] = mapped_column(String(320), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class MfaRecoveryCode(Base):
    __tablename__ = "mfa_recovery_codes"
    __table_args__ = (UniqueConstraint("user_id", "code_hash", name="uq_mfa_recovery_user_code"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="recovery_codes")


class PasskeyCredential(Base):
    __tablename__ = "passkey_credentials"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    credential_id: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False, index=True)
    public_key: Mapped[str] = mapped_column(Text, nullable=False)
    sign_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    device_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    backed_up: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    transports_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    label: Mapped[str | None] = mapped_column(String(160), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="passkeys")


class WebAuthnChallenge(Base):
    __tablename__ = "webauthn_challenges"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    purpose: Mapped[str] = mapped_column(String(32), index=True)
    challenge: Mapped[str] = mapped_column(String(256), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    client_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class AuthEventOutbox(Base):
    __tablename__ = "auth_event_outbox"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    subject_user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    client_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


def _revoke_scope_sessions(session: Session, rows: list[AuthSession], *, reason: str) -> None:
    now = utcnow()
    for row in rows:
        # A route may already have revoked this session before the lifecycle hook
        # runs. In that case the AuthSession branch below publishes the event.
        if row.revoked_at is not None:
            continue
        row.revoked_at = now
        row.revoked_reason = reason[:160]
        # Rows dirtied by this hook were not necessarily present in the initial
        # session.dirty snapshot, so publish their event explicitly here.
        session.add(
            AuthEventOutbox(
                event_type="session.revoked",
                subject_user_id=row.user_id,
                session_id=row.id,
                client_id=row.client_id,
                payload_json=json.dumps(
                    {"reason": row.revoked_reason, "revoked_at": now.isoformat()},
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            )
        )


@event.listens_for(Session, "before_flush")
def _queue_identity_status_events(session: Session, flush_context, instances) -> None:
    # Centralize lifecycle propagation at the ORM transaction boundary so API,
    # browser portal, scripts and future callers cannot bypass Push state.
    dirty = list(session.dirty)
    for obj in dirty:
        if isinstance(obj, User):
            history = inspect(obj).attrs.is_active.history
            if history.has_changes():
                session.add(
                    AuthEventOutbox(
                        event_type="account.enabled" if obj.is_active else "account.disabled",
                        subject_user_id=obj.id,
                        payload_json=json.dumps({"active": obj.is_active}, separators=(",", ":")),
                    )
                )
                if not obj.is_active:
                    rows = session.scalars(
                        select(AuthSession).where(
                            AuthSession.user_id == obj.id,
                            AuthSession.revoked_at.is_(None),
                        )
                    ).all()
                    _revoke_scope_sessions(session, list(rows), reason="account disabled")

        elif isinstance(obj, Application):
            history = inspect(obj).attrs.is_active.history
            if history.has_changes():
                session.add(
                    AuthEventOutbox(
                        event_type="application.enabled" if obj.is_active else "application.disabled",
                        client_id=obj.client_id,
                        payload_json=json.dumps({"active": obj.is_active}, separators=(",", ":")),
                    )
                )
                if not obj.is_active:
                    rows = session.scalars(
                        select(AuthSession).where(
                            AuthSession.client_id == obj.client_id,
                            AuthSession.revoked_at.is_(None),
                        )
                    ).all()
                    _revoke_scope_sessions(session, list(rows), reason="application disabled")

        elif isinstance(obj, AuthSession):
            history = inspect(obj).attrs.revoked_at.history
            if history.has_changes() and obj.revoked_at is not None:
                session.add(
                    AuthEventOutbox(
                        event_type="session.revoked",
                        subject_user_id=obj.user_id,
                        session_id=obj.id,
                        client_id=obj.client_id,
                        payload_json=json.dumps(
                            {
                                "reason": obj.revoked_reason or "revoked",
                                "revoked_at": obj.revoked_at.isoformat(),
                            },
                            separators=(",", ":"),
                            sort_keys=True,
                        ),
                    )
                )
