import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class FinanceExpense(Base):
    """Operating expense used for management P&L reporting."""

    __tablename__ = "finance_expenses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    expense_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    vendor: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(1000), default="", server_default="", nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_minor: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    payment_method: Mapped[str] = mapped_column(String(80), default="bank_transfer", server_default="bank_transfer", nullable=False)
    reference: Mapped[str] = mapped_column(String(180), default="", server_default="", nullable=False, index=True)
    recurring: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="posted", server_default="posted", nullable=False, index=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class FinanceBankTransaction(Base):
    """Imported bank movement waiting for or linked to invoice reconciliation."""

    __tablename__ = "finance_bank_transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(1000), default="", server_default="", nullable=False)
    reference: Mapped[str] = mapped_column(String(255), default="", server_default="", nullable=False, index=True)
    source_name: Mapped[str] = mapped_column(String(120), default="LPB", server_default="LPB", nullable=False)
    import_batch: Mapped[str] = mapped_column(String(120), default="manual", server_default="manual", nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), default="unmatched", server_default="unmatched", nullable=False, index=True)
    matched_invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("finance_invoices.id", ondelete="SET NULL"), index=True, nullable=True
    )
    matched_payment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("finance_payments.id", ondelete="SET NULL"), index=True, nullable=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FinanceServiceBillingLink(Base):
    """Links a live Ithute service/product to a recurring finance schedule."""

    __tablename__ = "finance_service_billing_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("finance_clients.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(80), default="ithute_product", server_default="ithute_product", nullable=False, index=True)
    source_ref: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    service_label: Mapped[str] = mapped_column(String(500), nullable=False)
    details: Mapped[str] = mapped_column(String(1200), default="", server_default="", nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    rate_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_minor: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    send_day: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    due_days: Mapped[int] = mapped_column(Integer, default=7, server_default="7", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False, index=True)
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("finance_invoice_schedules.id", ondelete="SET NULL"), index=True, nullable=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
