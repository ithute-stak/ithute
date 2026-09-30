import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class FinanceClient(Base):
    """Reusable Ithute finance customer profile."""

    __tablename__ = "finance_clients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(180), index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), index=True, nullable=False)
    address: Mapped[str] = mapped_column(String(500), default="", server_default="", nullable=False)
    phone: Mapped[str] = mapped_column(String(80), default="", server_default="", nullable=False)
    default_service: Mapped[str] = mapped_column(String(500), default="", server_default="", nullable=False)
    default_details: Mapped[str] = mapped_column(String(1200), default="", server_default="", nullable=False)
    default_quantity: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    default_rate_minor: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    default_tax_minor: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=7, server_default="7", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False, index=True)
    notes: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class FinanceInvoice(Base):
    """Internal Ithute invoice record used by the Finance module."""

    __tablename__ = "finance_invoices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_number: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("finance_clients.id", ondelete="SET NULL"), index=True, nullable=True
    )
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
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    payments: Mapped[list["FinancePayment"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", passive_deletes=True
    )


class FinancePayment(Base):
    """Payment or partial payment allocated to a finance invoice."""

    __tablename__ = "finance_payments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("finance_invoices.id", ondelete="CASCADE"), index=True, nullable=False
    )
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(80), default="bank_transfer", server_default="bank_transfer", nullable=False)
    reference: Mapped[str] = mapped_column(String(180), default="", server_default="", nullable=False)
    note: Mapped[str] = mapped_column(String(1000), default="", server_default="", nullable=False)
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    invoice: Mapped[FinanceInvoice] = relationship(back_populates="payments")


class FinanceInvoiceSchedule(Base):
    """Monthly invoice template that automatically generates and sends an invoice."""

    __tablename__ = "finance_invoice_schedules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("finance_clients.id", ondelete="SET NULL"), index=True, nullable=True
    )
    client_name: Mapped[str] = mapped_column(String(180), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(320), index=True, nullable=False)
    client_address: Mapped[str] = mapped_column(String(500), default="", server_default="", nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    details: Mapped[str] = mapped_column(String(1200), default="", server_default="", nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    rate_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_minor: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="LSL", server_default="LSL", nullable=False)
    send_day: Mapped[int] = mapped_column(Integer, nullable=False)
    due_days: Mapped[int] = mapped_column(Integer, default=7, server_default="7", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False, index=True)
    last_sent_period: Mapped[str | None] = mapped_column(String(7), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class FinanceSenderConfiguration(Base):
    """Singleton SMTP sender configured and verified by the platform owner."""

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
