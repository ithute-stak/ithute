from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Subcontractor(Base):
    __tablename__ = "subcontractors"
    __table_args__ = (UniqueConstraint("company_id", "subcontractor_code", name="uq_subcontractor_company_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    subcontractor_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    legal_name: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    trading_name: Mapped[str | None] = mapped_column(String(240))
    registration_number: Mapped[str | None] = mapped_column(String(120))
    tax_number: Mapped[str | None] = mapped_column(String(120))
    contact_name: Mapped[str | None] = mapped_column(String(180))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(64))
    address: Mapped[str | None] = mapped_column(Text)
    trade_categories: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    safety_rating: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    performance_rating: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", index=True)
    compliance_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    insurance_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    approved_by: Mapped[str | None] = mapped_column(String(255))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class SubcontractPackage(Base):
    __tablename__ = "subcontract_packages"
    __table_args__ = (UniqueConstraint("project_id", "package_code", name="uq_subcontract_package_project_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True)
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id", ondelete="SET NULL"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    cost_centre_id: Mapped[int | None] = mapped_column(ForeignKey("cost_centres.id", ondelete="SET NULL"), index=True)
    package_number: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    package_code: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    trade_category: Mapped[str | None] = mapped_column(String(100), index=True)
    planned_start_date: Mapped[date | None] = mapped_column(Date)
    planned_completion_date: Mapped[date | None] = mapped_column(Date, index=True)
    budget_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft", index=True)
    selected_bid_id: Mapped[int | None] = mapped_column(ForeignKey("subcontract_bids.id", use_alter=True, name="fk_package_selected_bid", ondelete="SET NULL"), index=True)
    award_approval_request_id: Mapped[int | None] = mapped_column(ForeignKey("approval_requests.id", ondelete="SET NULL"), index=True)
    award_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class SubcontractPackageLine(Base):
    __tablename__ = "subcontract_package_lines"
    __table_args__ = (UniqueConstraint("package_id", "line_number", name="uq_subcontract_package_line_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("subcontract_packages.id", ondelete="CASCADE"), nullable=False, index=True)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    specification: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=Decimal("1"))
    unit: Mapped[str] = mapped_column(String(40), nullable=False, default="item")
    budget_rate: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    budget_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    milestone_id: Mapped[int | None] = mapped_column(ForeignKey("project_milestones.id", ondelete="SET NULL"), index=True)
    notes: Mapped[str | None] = mapped_column(Text)


class SubcontractInvitation(Base):
    __tablename__ = "subcontract_invitations"
    __table_args__ = (UniqueConstraint("package_id", "subcontractor_id", name="uq_subcontract_invitation_package_subcontractor"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("subcontract_packages.id", ondelete="CASCADE"), nullable=False, index=True)
    subcontractor_id: Mapped[int] = mapped_column(ForeignKey("subcontractors.id", ondelete="RESTRICT"), nullable=False, index=True)
    invitation_number: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    invited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    due_date: Mapped[date | None] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="invited", index=True)
    invitation_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    invited_by: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class SubcontractBid(Base):
    __tablename__ = "subcontract_bids"
    __table_args__ = (UniqueConstraint("package_id", "subcontractor_id", "bid_reference", name="uq_subcontract_bid_package_vendor_reference"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("subcontract_packages.id", ondelete="CASCADE"), nullable=False, index=True)
    subcontractor_id: Mapped[int] = mapped_column(ForeignKey("subcontractors.id", ondelete="RESTRICT"), nullable=False, index=True)
    bid_number: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    bid_reference: Mapped[str] = mapped_column(String(120), nullable=False)
    bid_date: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date)
    planned_duration_days: Mapped[int | None] = mapped_column(Integer)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="received", index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    exclusions: Mapped[str | None] = mapped_column(Text)
    submitted_by: Mapped[str] = mapped_column(String(255), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class SubcontractBidLine(Base):
    __tablename__ = "subcontract_bid_lines"
    __table_args__ = (UniqueConstraint("bid_id", "package_line_id", name="uq_subcontract_bid_package_line"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    bid_id: Mapped[int] = mapped_column(ForeignKey("subcontract_bids.id", ondelete="CASCADE"), nullable=False, index=True)
    package_line_id: Mapped[int] = mapped_column(ForeignKey("subcontract_package_lines.id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit_rate: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class SubcontractEvaluation(Base):
    __tablename__ = "subcontract_evaluations"
    __table_args__ = (UniqueConstraint("package_id", "bid_id", name="uq_subcontract_evaluation_package_bid"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("subcontract_packages.id", ondelete="CASCADE"), nullable=False, index=True)
    bid_id: Mapped[int] = mapped_column(ForeignKey("subcontract_bids.id", ondelete="CASCADE"), nullable=False, index=True)
    technical_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=Decimal("0"))
    commercial_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=Decimal("0"))
    hse_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=Decimal("0"))
    programme_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=Decimal("0"))
    total_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=Decimal("0"), index=True)
    recommendation: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    evaluation_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    notes: Mapped[str | None] = mapped_column(Text)
    evaluated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class SubcontractContract(Base):
    __tablename__ = "subcontract_contracts"
    __table_args__ = (UniqueConstraint("company_id", "contract_number", name="uq_subcontract_contract_company_number"), UniqueConstraint("package_id", name="uq_subcontract_contract_package"))

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True)
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id", ondelete="SET NULL"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("subcontract_packages.id", ondelete="RESTRICT"), nullable=False, index=True)
    subcontractor_id: Mapped[int] = mapped_column(ForeignKey("subcontractors.id", ondelete="RESTRICT"), nullable=False, index=True)
    selected_bid_id: Mapped[int | None] = mapped_column(ForeignKey("subcontract_bids.id", ondelete="SET NULL"), index=True)
    cost_centre_id: Mapped[int | None] = mapped_column(ForeignKey("cost_centres.id", ondelete="SET NULL"), index=True)
    contract_number: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    contract_reference: Mapped[str | None] = mapped_column(String(160))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    completion_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="LSL")
    original_contract_sum: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    retention_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False, default=Decimal("5"))
    retention_cap: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    advance_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    certified_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    retention_held: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft", index=True)
    approval_request_id: Mapped[int | None] = mapped_column(ForeignKey("approval_requests.id", ondelete="SET NULL"), index=True)
    contract_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    approved_snapshot: Mapped[dict | None] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SubcontractVariation(Base):
    __tablename__ = "subcontract_variations"
    __table_args__ = (UniqueConstraint("contract_id", "variation_number", name="uq_subcontract_variation_contract_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("subcontract_contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    variation_number: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    time_extension_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft", index=True)
    approval_request_id: Mapped[int | None] = mapped_column(ForeignKey("approval_requests.id", ondelete="SET NULL"), index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SubcontractCertificate(Base):
    __tablename__ = "subcontract_certificates"
    __table_args__ = (UniqueConstraint("contract_id", "certificate_number", name="uq_subcontract_certificate_contract_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("subcontract_contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    certificate_number: Mapped[str] = mapped_column(String(80), nullable=False)
    certificate_type: Mapped[str] = mapped_column(String(24), nullable=False, default="interim", index=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    gross_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    previous_certified: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    cumulative_certified: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    retention_deduction: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    other_deductions: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    net_payable: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft", index=True)
    approval_request_id: Mapped[int | None] = mapped_column(ForeignKey("approval_requests.id", ondelete="SET NULL"), index=True)
    evidence_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    approved_snapshot: Mapped[dict | None] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text)
    prepared_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SubcontractPayment(Base):
    __tablename__ = "subcontract_payments"
    __table_args__ = (UniqueConstraint("company_id", "payment_reference", name="uq_subcontract_payment_reference"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    certificate_id: Mapped[int] = mapped_column(ForeignKey("subcontract_certificates.id", ondelete="RESTRICT"), nullable=False, index=True)
    payment_reference: Mapped[str] = mapped_column(String(120), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    payment_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    notes: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[str] = mapped_column(String(255), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class SubcontractPerformanceReview(Base):
    __tablename__ = "subcontract_performance_reviews"
    __table_args__ = (UniqueConstraint("contract_id", "review_date", name="uq_subcontract_performance_review_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("subcontract_contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    review_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    quality_score: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False)
    programme_score: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False)
    safety_score: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False)
    commercial_score: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False)
    overall_score: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open", index=True)
    improvement_action: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[date | None] = mapped_column(Date)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    reviewed_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class SubcontractAuditEvent(Base):
    __tablename__ = "subcontract_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id", ondelete="SET NULL"), index=True)
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id", ondelete="SET NULL"), index=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_id: Mapped[str | None] = mapped_column(String(100))
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
