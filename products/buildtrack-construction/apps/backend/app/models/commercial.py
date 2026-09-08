from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ClientContract(Base):
    __tablename__ = "client_contracts"
    __table_args__ = (
        UniqueConstraint("company_id", "contract_number", name="uq_client_contract_company_number"),
        UniqueConstraint("project_id", name="uq_client_contract_project"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    cost_centre_id: Mapped[int] = mapped_column(ForeignKey("cost_centres.id", ondelete="RESTRICT"), nullable=False, index=True)
    contract_number: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    client_name: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    client_reference: Mapped[str | None] = mapped_column(String(180))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    completion_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    original_contract_sum: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    retention_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False, default=Decimal("5"))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft", index=True)
    contract_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    approval_request_id: Mapped[int | None] = mapped_column(ForeignKey("approval_requests.id", ondelete="SET NULL"), index=True)
    approved_snapshot: Mapped[dict | None] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ClientVariation(Base):
    __tablename__ = "client_variations"
    __table_args__ = (UniqueConstraint("contract_id", "variation_number", name="uq_client_variation_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("client_contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    variation_number: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    time_extension_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft", index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    approval_request_id: Mapped[int | None] = mapped_column(ForeignKey("approval_requests.id", ondelete="SET NULL"), index=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProjectCostTransaction(Base):
    __tablename__ = "project_cost_transactions"
    __table_args__ = (UniqueConstraint("company_id", "transaction_number", name="uq_project_cost_transaction_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    cost_centre_id: Mapped[int] = mapped_column(ForeignKey("cost_centres.id", ondelete="RESTRICT"), nullable=False, index=True)
    transaction_number: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    transaction_type: Mapped[str] = mapped_column(String(32), nullable=False, default="actual", index=True)
    cost_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    cost_code: Mapped[str | None] = mapped_column(String(80), index=True)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    source_type: Mapped[str | None] = mapped_column(String(64), index=True)
    source_reference: Mapped[str | None] = mapped_column(String(160))
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="posted", index=True)
    reversal_of_id: Mapped[int | None] = mapped_column(ForeignKey("project_cost_transactions.id", ondelete="SET NULL"), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[str] = mapped_column(String(255), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)


class ClientValuation(Base):
    __tablename__ = "client_valuations"
    __table_args__ = (UniqueConstraint("contract_id", "valuation_number", name="uq_client_valuation_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("client_contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    valuation_number: Mapped[str] = mapped_column(String(80), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    gross_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    previous_certified: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    cumulative_certified: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    retention_deduction: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    other_deductions: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    net_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft", index=True)
    evidence_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    approval_request_id: Mapped[int | None] = mapped_column(ForeignKey("approval_requests.id", ondelete="SET NULL"), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    prepared_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ClientInvoice(Base):
    __tablename__ = "client_invoices"
    __table_args__ = (UniqueConstraint("company_id", "invoice_number", name="uq_client_invoice_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("client_contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    valuation_id: Mapped[int] = mapped_column(ForeignKey("client_valuations.id", ondelete="RESTRICT"), nullable=False, index=True, unique=True)
    invoice_number: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    due_date: Mapped[date | None] = mapped_column(Date, index=True)
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    retention_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    net_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft", index=True)
    invoice_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    approval_request_id: Mapped[int | None] = mapped_column(ForeignKey("approval_requests.id", ondelete="SET NULL"), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ClientReceipt(Base):
    __tablename__ = "client_receipts"
    __table_args__ = (UniqueConstraint("company_id", "receipt_reference", name="uq_client_receipt_reference"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("client_invoices.id", ondelete="RESTRICT"), nullable=False, index=True)
    receipt_reference: Mapped[str] = mapped_column(String(120), nullable=False)
    receipt_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    payment_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    notes: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[str] = mapped_column(String(255), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ClientClaim(Base):
    __tablename__ = "client_claims"
    __table_args__ = (UniqueConstraint("company_id", "claim_number", name="uq_client_claim_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("client_contracts.id", ondelete="SET NULL"), index=True)
    claim_number: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    claim_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    basis: Mapped[str] = mapped_column(Text, nullable=False)
    claimed_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    assessed_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    notice_date: Mapped[date | None] = mapped_column(Date, index=True)
    response_due_date: Mapped[date | None] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft", index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    approval_request_id: Mapped[int | None] = mapped_column(ForeignKey("approval_requests.id", ondelete="SET NULL"), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProjectCashFlowForecast(Base):
    __tablename__ = "project_cash_flow_forecasts"
    __table_args__ = (UniqueConstraint("project_id", "forecast_month", name="uq_project_cash_flow_month"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    forecast_month: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    expected_inflow: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    expected_outflow: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    net_cash: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    source: Mapped[str] = mapped_column(String(48), nullable=False, default="manual")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="forecast", index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    prepared_by: Mapped[str] = mapped_column(String(255), nullable=False)
    prepared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class CommercialAuditEvent(Base):
    __tablename__ = "commercial_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id", ondelete="SET NULL"), index=True)
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id", ondelete="SET NULL"), index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_id: Mapped[str | None] = mapped_column(String(100))
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
