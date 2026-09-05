import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator[datetime]):
    """Persist timestamps as UTC and always return timezone-aware UTC values.

    PostgreSQL preserves timezone information for TIMESTAMPTZ. SQLite does not,
    even when SQLAlchemy is configured with DateTime(timezone=True). Normalizing
    at the type boundary keeps lifecycle ordering and revocation comparisons
    portable across both databases and prevents naive/aware comparison errors.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class PushEndpoint(Base):
    __tablename__ = "push_endpoints"
    __table_args__ = (
        UniqueConstraint("auth_user_id", "application_id", "device_key", name="uq_push_endpoint_identity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    auth_user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    auth_session_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    application_id: Mapped[str] = mapped_column(String(120), index=True)
    device_key: Mapped[str] = mapped_column(String(200), index=True)
    platform: Mapped[str] = mapped_column(String(24))
    provider: Mapped[str] = mapped_column(String(24))
    endpoint_ciphertext: Mapped[str] = mapped_column(Text)
    endpoint_hash: Mapped[str] = mapped_column(String(64), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    deliveries: Mapped[list["Delivery"]] = relationship(back_populates="endpoint")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("source_client_id", "idempotency_key", name="uq_message_source_idempotency"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_client_id: Mapped[str] = mapped_column(String(120), index=True)
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(String(500))
    route: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sound: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    deliveries: Mapped[list["Delivery"]] = relationship(back_populates="message", cascade="all, delete-orphan")


class Delivery(Base):
    __tablename__ = "deliveries"
    __table_args__ = (UniqueConstraint("message_id", "endpoint_id", name="uq_delivery_message_endpoint"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    endpoint_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("push_endpoints.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(300), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    message: Mapped[Message] = relationship(back_populates="deliveries")
    endpoint: Mapped[PushEndpoint] = relationship(back_populates="deliveries")


class AuthLifecycleEvent(Base):
    __tablename__ = "auth_lifecycle_events"

    event_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    auth_user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    auth_session_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    application_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    details_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class RevokedAuthSession(Base):
    __tablename__ = "revoked_auth_sessions"

    session_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    auth_user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    application_id: Mapped[str] = mapped_column(String(120), index=True)
    revoked_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(nullable=False)


class AuthUserState(Base):
    __tablename__ = "auth_user_states"

    auth_user_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(nullable=False)


class ApplicationState(Base):
    __tablename__ = "application_states"

    application_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
