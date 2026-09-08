from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Tender(Base):
    __tablename__ = "tenders"
    __table_args__ = (
        UniqueConstraint("company_id", "tender_number", name="uq_tender_company_number"),
        UniqueConstraint("company_id", "external_reference", name="uq_tender_company_external_reference"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True)
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id", ondelete="SET NULL"), index=True)
    cost_centre_id: Mapped[int | None] = mapped_column(ForeignKey("cost_centres.id", ondelete="SET NULL"), index=True)
    lead_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    tender_number: Mapped[str] = mapped_column(String(80), nullable=False)
    external_reference: Mapped[str | None] = mapped_column(String(160))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    client_name: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    client_contact: Mapped[str | None] = mapped_column(String(240))
    procurement_method: Mapped[str | None] = mapped_column(String(100))
    source: Mapped[str | None] = mapped_column(String(120))
    category: Mapped[str | None] = mapped_column(String(120), index=True)
    location: Mapped[str | None] = mapped_column(String(240))
    issue_date: Mapped[date | None] = mapped_column(Date)
    briefing_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    site_visit_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    site_visit_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    clarification_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submission_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    opening_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validity_days: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="LSL")
    estimated_contract_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    direct_cost_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    tender_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    gross_margin: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    gross_margin_pct: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False, default=Decimal("0"))
    win_probability: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    priority: Mapped[str] = mapped_column(String(24), nullable=False, default="normal", index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="identified", index=True)
    bid_decision: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", index=True)
    bid_decision_reason: Mapped[str | None] = mapped_column(Text)
    bid_decided_by: Mapped[str | None] = mapped_column(String(255))
    bid_decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    commercial_approval_request_id: Mapped[int | None] = mapped_column(ForeignKey("approval_requests.id", ondelete="SET NULL"), index=True)
    submission_approval_request_id: Mapped[int | None] = mapped_column(ForeignKey("approval_requests.id", ondelete="SET NULL"), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class TenderTeamMember(Base):
    __tablename__ = "tender_team_members"
    __table_args__ = (UniqueConstraint("tender_id", "employee_id", "role", name="uq_tender_team_member_role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    added_by: Mapped[str] = mapped_column(String(255), nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class TenderChecklistItem(Base):
    __tablename__ = "tender_checklist_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="missing", index=True)
    owner_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class TenderEstimateItem(Base):
    __tablename__ = "tender_estimate_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False, index=True)
    section: Mapped[str | None] = mapped_column(String(160), index=True)
    item_code: Mapped[str | None] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="item")
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("1"))
    material_unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    labour_unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    plant_unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    subcontract_unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    other_unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    direct_unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    direct_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    markup_pct: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False, default=Decimal("0"))
    selling_rate: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    selling_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class TenderSecurity(Base):
    __tablename__ = "tender_securities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False, index=True)
    security_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    provider: Mapped[str | None] = mapped_column(String(200))
    reference_number: Mapped[str | None] = mapped_column(String(160))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    issue_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="required", index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class TenderClarification(Base):
    __tablename__ = "tender_clarifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False, index=True)
    clarification_number: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    sent_to: Mapped[str | None] = mapped_column(String(240))
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open", index=True)
    response: Mapped[str | None] = mapped_column(Text)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    raised_by: Mapped[str] = mapped_column(String(255), nullable=False)


class TenderSubmission(Base):
    __tablename__ = "tender_submissions"
    __table_args__ = (UniqueConstraint("tender_id", "version", name="uq_tender_submission_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False, index=True)
    approval_request_id: Mapped[int | None] = mapped_column(ForeignKey("approval_requests.id", ondelete="SET NULL"), index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    submission_method: Mapped[str] = mapped_column(String(60), nullable=False)
    submission_location: Mapped[str | None] = mapped_column(String(300))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    submitted_by: Mapped[str] = mapped_column(String(255), nullable=False)
    acknowledgement_reference: Mapped[str | None] = mapped_column(String(200))
    acknowledgement_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    tender_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class TenderOutcome(Base):
    __tablename__ = "tender_outcomes"
    __table_args__ = (UniqueConstraint("tender_id", name="uq_tender_outcome_tender"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False, index=True)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    decision_date: Mapped[date | None] = mapped_column(Date)
    awarded_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    winning_bidder: Mapped[str | None] = mapped_column(String(240))
    winning_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    loss_reason: Mapped[str | None] = mapped_column(Text)
    lessons_learned: Mapped[str | None] = mapped_column(Text)
    award_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    recorded_by: Mapped[str] = mapped_column(String(255), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class TenderAuditEvent(Base):
    __tablename__ = "tender_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    tender_id: Mapped[int | None] = mapped_column(ForeignKey("tenders.id", ondelete="SET NULL"), index=True)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id", ondelete="SET NULL"), index=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(100))
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
