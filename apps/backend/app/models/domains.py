import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class DomainStatus(str, enum.Enum):
    pending_verification = "pending_verification"
    verified = "verified"
    suspended = "suspended"
    archived = "archived"


class DomainDnsMode(str, enum.Enum):
    external = "external"
    platform = "platform"


class DomainVerificationMethod(str, enum.Enum):
    txt = "txt"
    nameserver = "nameserver"


class Domain(Base):
    __tablename__ = "domains"
    __table_args__ = (UniqueConstraint("ascii_name", name="uq_domains_ascii_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    ascii_name: Mapped[str] = mapped_column(String(253), nullable=False, index=True)
    unicode_name: Mapped[str] = mapped_column(String(253), nullable=False)
    status: Mapped[DomainStatus] = mapped_column(Enum(DomainStatus), default=DomainStatus.pending_verification, nullable=False, index=True)
    dns_mode: Mapped[DomainDnsMode] = mapped_column(Enum(DomainDnsMode), default=DomainDnsMode.platform, nullable=False)
    mail_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_method: Mapped[str] = mapped_column(String(20), default=DomainVerificationMethod.txt.value, nullable=False)
    verification_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    verification_token_hint: Mapped[str] = mapped_column(String(16), nullable=False)
    verification_record_name: Mapped[str] = mapped_column(String(320), nullable=False)
    ownership_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    verification_attempts: Mapped[list["DomainVerificationAttempt"]] = relationship(back_populates="domain", cascade="all, delete-orphan")
    events: Mapped[list["DomainEvent"]] = relationship(back_populates="domain", cascade="all, delete-orphan")


class DomainVerificationAttempt(Base):
    __tablename__ = "domain_verification_attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("domains.id", ondelete="CASCADE"), index=True, nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    observed_values_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    domain: Mapped[Domain] = relationship(back_populates="verification_attempts")


class DomainEvent(Base):
    __tablename__ = "domain_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("domains.id", ondelete="CASCADE"), index=True, nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    domain: Mapped[Domain] = relationship(back_populates="events")
