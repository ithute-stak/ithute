from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SiteOperationsActivation(Base):
    __tablename__ = "site_operations_activations"
    __table_args__ = (UniqueConstraint("project_id", "site_id", name="uq_site_ops_project_site"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    project_readiness_snapshot_id: Mapped[int] = mapped_column(ForeignKey("project_readiness_snapshots.id", ondelete="RESTRICT"), nullable=False, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, index=True)
    cost_centre_id: Mapped[int] = mapped_column(ForeignKey("cost_centres.id", ondelete="RESTRICT"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active", index=True)
    activated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)


class SiteDailyReport(Base):
    __tablename__ = "site_daily_reports"
    __table_args__ = (UniqueConstraint("project_id", "site_id", "report_date", "shift", name="uq_site_daily_report_shift"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    activation_id: Mapped[int] = mapped_column(ForeignKey("site_operations_activations.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, index=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    shift: Mapped[str] = mapped_column(String(24), nullable=False, default="day")
    weather_summary: Mapped[str | None] = mapped_column(String(240))
    rain_hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=Decimal("0"))
    work_summary: Mapped[str | None] = mapped_column(Text)
    planned_work: Mapped[str | None] = mapped_column(Text)
    blockers: Mapped[str | None] = mapped_column(Text)
    safety_summary: Mapped[str | None] = mapped_column(Text)
    visitor_summary: Mapped[str | None] = mapped_column(Text)
    no_work_reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft", index=True)
    approval_request_id: Mapped[int | None] = mapped_column(ForeignKey("approval_requests.id", ondelete="SET NULL"), index=True)
    approved_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    submitted_by: Mapped[str | None] = mapped_column(String(255))
    approved_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class SiteLabourEntry(Base):
    __tablename__ = "site_labour_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    daily_report_id: Mapped[int] = mapped_column(ForeignKey("site_daily_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, index=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    crew_name: Mapped[str | None] = mapped_column(String(160))
    worker_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    regular_hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=Decimal("0"))
    overtime_hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=Decimal("0"))
    activity: Mapped[str] = mapped_column(String(300), nullable=False)
    work_area: Mapped[str | None] = mapped_column(String(200))
    cost_centre_id: Mapped[int | None] = mapped_column(ForeignKey("cost_centres.id", ondelete="SET NULL"), index=True)
    timesheet_entry_id: Mapped[int | None] = mapped_column(ForeignKey("timesheet_entries.id", ondelete="SET NULL"), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[str] = mapped_column(String(255), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class SitePlantUsage(Base):
    __tablename__ = "site_plant_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    daily_report_id: Mapped[int] = mapped_column(ForeignKey("site_daily_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("fleet_assets.id", ondelete="RESTRICT"), nullable=False, index=True)
    operator_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    usage_hours: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False, default=Decimal("0"))
    idle_hours: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False, default=Decimal("0"))
    start_odometer_km: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    end_odometer_km: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    start_engine_hours: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    end_engine_hours: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    activity: Mapped[str] = mapped_column(String(300), nullable=False)
    breakdown: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[str] = mapped_column(String(255), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class SiteMaterialEntry(Base):
    __tablename__ = "site_material_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    daily_report_id: Mapped[int] = mapped_column(ForeignKey("site_daily_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, index=True)
    movement_type: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    material_code: Mapped[str | None] = mapped_column(String(80), index=True)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    total_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    supplier_or_source: Mapped[str | None] = mapped_column(String(240))
    source_reference: Mapped[str | None] = mapped_column(String(160))
    work_area: Mapped[str | None] = mapped_column(String(200))
    waste_reason: Mapped[str | None] = mapped_column(Text)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[str] = mapped_column(String(255), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class SiteProgressEntry(Base):
    __tablename__ = "site_progress_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    daily_report_id: Mapped[int] = mapped_column(ForeignKey("site_daily_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, index=True)
    milestone_id: Mapped[int | None] = mapped_column(ForeignKey("project_milestones.id", ondelete="SET NULL"), index=True)
    work_item: Mapped[str] = mapped_column(String(300), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(40))
    planned_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    period_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    cumulative_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    progress_pct: Mapped[Decimal] = mapped_column(Numeric(7, 3), nullable=False, default=Decimal("0"))
    measurement_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    narrative: Mapped[str | None] = mapped_column(Text)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), index=True)
    recorded_by: Mapped[str] = mapped_column(String(255), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class SiteEvidence(Base):
    __tablename__ = "site_evidence"
    __table_args__ = (UniqueConstraint("daily_report_id", "document_id", "evidence_type", name="uq_site_report_evidence"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    daily_report_id: Mapped[int] = mapped_column(ForeignKey("site_daily_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False, index=True)
    evidence_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    caption: Mapped[str | None] = mapped_column(String(300))
    work_area: Mapped[str | None] = mapped_column(String(200))
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    added_by: Mapped[str] = mapped_column(String(255), nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class SiteIncident(Base):
    __tablename__ = "site_incidents"
    __table_args__ = (UniqueConstraint("company_id", "incident_number", name="uq_site_incident_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    activation_id: Mapped[int] = mapped_column(ForeignKey("site_operations_activations.id", ondelete="CASCADE"), nullable=False, index=True)
    daily_report_id: Mapped[int | None] = mapped_column(ForeignKey("site_daily_reports.id", ondelete="SET NULL"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, index=True)
    incident_number: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    incident_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    persons_involved: Mapped[str | None] = mapped_column(Text)
    lost_time: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    immediate_action: Mapped[str | None] = mapped_column(Text)
    root_cause: Mapped[str | None] = mapped_column(Text)
    corrective_action: Mapped[str | None] = mapped_column(Text)
    owner_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    due_date: Mapped[date | None] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open", index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recorded_by: Mapped[str] = mapped_column(String(255), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class SiteQualityCheck(Base):
    __tablename__ = "site_quality_checks"
    __table_args__ = (UniqueConstraint("company_id", "inspection_number", name="uq_site_quality_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    activation_id: Mapped[int] = mapped_column(ForeignKey("site_operations_activations.id", ondelete="CASCADE"), nullable=False, index=True)
    daily_report_id: Mapped[int | None] = mapped_column(ForeignKey("site_daily_reports.id", ondelete="SET NULL"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, index=True)
    inspection_number: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    check_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    work_item: Mapped[str] = mapped_column(String(300), nullable=False)
    specification_reference: Mapped[str | None] = mapped_column(String(200))
    inspected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    inspector_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    result: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    nonconformance_number: Mapped[str | None] = mapped_column(String(100), index=True)
    corrective_action: Mapped[str | None] = mapped_column(Text)
    owner_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    due_date: Mapped[date | None] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open", index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class SiteOperationsAuditEvent(Base):
    __tablename__ = "site_operations_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id", ondelete="SET NULL"), index=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_id: Mapped[str | None] = mapped_column(String(100), index=True)
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
