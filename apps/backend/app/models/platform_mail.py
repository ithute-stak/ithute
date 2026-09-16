import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class PlatformMailDomainGrant(Base):
    __tablename__ = "platform_mail_domain_grants"
    __table_args__ = (
        UniqueConstraint("service_client_id", "domain_id", name="uq_platform_mail_grant_client_domain"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_client_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    domain_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("domains.id", ondelete="CASCADE"), nullable=False, index=True
    )
    local_part_prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PlatformMailboxBinding(Base):
    __tablename__ = "platform_mailbox_bindings"
    __table_args__ = (
        UniqueConstraint(
            "service_client_id",
            "external_reference",
            name="uq_platform_mailbox_binding_client_reference",
        ),
        UniqueConstraint("mailbox_id", name="uq_platform_mailbox_binding_mailbox"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_client_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    external_reference: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    mailbox_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    domain_grant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_mail_domain_grants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    inbound_forward_to: Mapped[str | None] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PlatformMailOutboundDelivery(Base):
    """One product-owned outbound submission keyed by a caller reference.

    The caller reference is unique only within a managed service client. This lets
    a product retry an HTTP request without silently generating another SMTP
    submission after the first call has already been accepted.
    """

    __tablename__ = "platform_mail_outbound_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "service_client_id",
            "external_reference",
            name="uq_platform_mail_outbound_client_reference",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_client_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    external_reference: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    mailbox_binding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_mailbox_bindings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recipient: Mapped[str] = mapped_column(String(320), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    transactional_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactional_messages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(320), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="submitting", nullable=False, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
