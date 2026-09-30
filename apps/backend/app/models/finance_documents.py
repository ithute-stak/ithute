import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class FinanceCommercialDocument(Base):
    """Quotation, pro-forma invoice or credit note issued by Ithute Finance."""

    __tablename__ = "finance_commercial_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_number: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    document_type: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), index=True, default="draft", server_default="draft", nullable=False)
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("finance_clients.id", ondelete="SET NULL"), index=True, nullable=True
    )
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("finance_commercial_documents.id", ondelete="SET NULL"), nullable=True
    )
    source_invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("finance_invoices.id", ondelete="SET NULL"), index=True, nullable=True
    )
    converted_invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("finance_invoices.id", ondelete="SET NULL"), nullable=True
    )
    client_name: Mapped[str] = mapped_column(String(180), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(320), index=True, nullable=False)
    client_address: Mapped[str] = mapped_column(String(500), default="", server_default="", nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="LSL", server_default="LSL", nullable=False)
    subtotal_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_minor: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    total_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    items: Mapped[list["FinanceCommercialDocumentItem"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True, order_by="FinanceCommercialDocumentItem.position"
    )


class FinanceCommercialDocumentItem(Base):
    __tablename__ = "finance_commercial_document_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("finance_commercial_documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    details: Mapped[str] = mapped_column(String(1200), default="", server_default="", nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    unit_rate_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_minor: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    line_subtotal_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total_minor: Mapped[int] = mapped_column(Integer, nullable=False)

    document: Mapped[FinanceCommercialDocument] = relationship(back_populates="items")


class FinanceAuditEvent(Base):
    """Append-only audit record for important Finance actions."""

    __tablename__ = "finance_audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True, nullable=True)
    action: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    summary: Mapped[str] = mapped_column(String(1000), default="", server_default="", nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
