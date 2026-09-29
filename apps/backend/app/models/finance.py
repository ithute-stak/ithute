import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class FinanceInvoice(Base):
    """Internal Ithute invoice record used by the Finance module.

    This is intentionally separate from tenant subscription billing invoices. It
    represents invoices Ithute Digital Solutions sends to arbitrary customers
    for iMail and other services.
    """

    __tablename__ = "finance_invoices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_number: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    client_name: Mapped[str] = mapped_column(String(180), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(320), index=True, nullable=False)
    client_address: Mapped[str] = mapped_column(String(500), default="", server_default="", nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    details: Mapped[str] = mapped_column(String(1200), default="", server_default="", nullable=False)
    service_period: Mapped[str] = mapped_column(String(160), default="", server_default="", nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    rate_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    subtotal_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    total_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="LSL", server_default="LSL", nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="draft", server_default="draft", nullable=False, index=True)
    email_subject: Mapped[str] = mapped_column(String(300), nullable=False)
    email_body: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class FinanceSenderConfiguration(Base):
    """Singleton SMTP sender configured and verified by the platform owner.

    The SMTP password is encrypted with Ithute's application encryption key and
    is never returned by the API. Any change to connection/authentication fields
    invalidates verification until a real SMTP AUTH succeeds again.
    """

    __tablename__ = "finance_sender_configurations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sender_email: Mapped[str] = mapped_column(String(320), nullable=False)
    smtp_username: Mapped[str] = mapped_column(String(320), nullable=False)
    smtp_password_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    smtp_host: Mapped[str] = mapped_column(String(255), nullable=False)
    smtp_port: Mapped[int] = mapped_column(Integer, nullable=False)
    security_mode: Mapped[str] = mapped_column(String(20), default="starttls", server_default="starttls", nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_verification_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
