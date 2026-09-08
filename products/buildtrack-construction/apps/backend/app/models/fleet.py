from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FleetAsset(Base):
    __tablename__ = "fleet_assets"
    __table_args__ = (
        UniqueConstraint("company_id", "asset_number", name="uq_fleet_asset_company_number"),
        UniqueConstraint("company_id", "registration_number", name="uq_fleet_asset_company_registration"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True)
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id", ondelete="SET NULL"), index=True)
    cost_centre_id: Mapped[int | None] = mapped_column(ForeignKey("cost_centres.id", ondelete="SET NULL"), index=True)
    asset_number: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(80))
    registration_number: Mapped[str | None] = mapped_column(String(80))
    make: Mapped[str] = mapped_column(String(120), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    manufacture_year: Mapped[int | None] = mapped_column(Integer)
    vin_serial_number: Mapped[str | None] = mapped_column(String(160), index=True)
    engine_number: Mapped[str | None] = mapped_column(String(120))
    fuel_type: Mapped[str | None] = mapped_column(String(40))
    ownership_type: Mapped[str] = mapped_column(String(32), nullable=False, default="owned")
    supplier_owner: Mapped[str | None] = mapped_column(String(200))
    acquisition_date: Mapped[date | None] = mapped_column(Date)
    acquisition_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    meter_type: Mapped[str] = mapped_column(String(24), nullable=False, default="odometer")
    current_odometer_km: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0"))
    current_engine_hours: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    serviceability: Mapped[str] = mapped_column(String(32), nullable=False, default="serviceable", index=True)
    colour: Mapped[str | None] = mapped_column(String(60))
    capacity_description: Mapped[str | None] = mapped_column(String(160))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class FleetAssignment(Base):
    __tablename__ = "fleet_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("fleet_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True)
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id", ondelete="SET NULL"), index=True)
    assigned_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    assigned_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purpose: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active", index=True)
    assigned_by: Mapped[str] = mapped_column(String(255), nullable=False)
    completed_by: Mapped[str | None] = mapped_column(String(255))


class FleetMeterReading(Base):
    __tablename__ = "fleet_meter_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("fleet_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    reading_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    odometer_km: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    engine_hours: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    source_id: Mapped[str | None] = mapped_column(String(80))
    notes: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[str] = mapped_column(String(255), nullable=False)


class FleetCompliance(Base):
    __tablename__ = "fleet_compliance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("fleet_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    compliance_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    reference_number: Mapped[str | None] = mapped_column(String(120))
    provider: Mapped[str | None] = mapped_column(String(200))
    issue_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date, index=True)
    reminder_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class FleetInspection(Base):
    __tablename__ = "fleet_inspections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("fleet_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True)
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id", ondelete="SET NULL"), index=True)
    inspector_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    inspection_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    inspection_type: Mapped[str] = mapped_column(String(32), nullable=False, default="pre_start")
    odometer_km: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    engine_hours: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    checklist: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    defects_found: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    safe_to_operate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="submitted", index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    inspected_by: Mapped[str] = mapped_column(String(255), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(255))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class FleetDefect(Base):
    __tablename__ = "fleet_defects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("fleet_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    inspection_id: Mapped[int | None] = mapped_column(ForeignKey("fleet_inspections.id", ondelete="SET NULL"), index=True)
    defect_number: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(24), nullable=False, default="minor", index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open", index=True)
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    reported_by: Mapped[str] = mapped_column(String(255), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(String(255))
    resolution_notes: Mapped[str | None] = mapped_column(Text)


class FleetFuelTransaction(Base):
    __tablename__ = "fleet_fuel_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("fleet_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True)
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id", ondelete="SET NULL"), index=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    transaction_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    fuel_type: Mapped[str] = mapped_column(String(40), nullable=False)
    litres: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    vendor: Mapped[str | None] = mapped_column(String(200))
    receipt_reference: Mapped[str | None] = mapped_column(String(120))
    odometer_km: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    engine_hours: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    full_tank: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[str] = mapped_column(String(255), nullable=False)


class FleetMaintenancePlan(Base):
    __tablename__ = "fleet_maintenance_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("fleet_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    interval_km: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    interval_hours: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    interval_days: Mapped[int | None] = mapped_column(Integer)
    last_service_date: Mapped[date | None] = mapped_column(Date)
    last_odometer_km: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    last_engine_hours: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    next_due_date: Mapped[date | None] = mapped_column(Date, index=True)
    next_due_odometer_km: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    next_due_engine_hours: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)


class FleetMaintenanceJob(Base):
    __tablename__ = "fleet_maintenance_jobs"
    __table_args__ = (UniqueConstraint("company_id", "job_number", name="uq_fleet_job_company_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("fleet_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("fleet_maintenance_plans.id", ondelete="SET NULL"))
    defect_id: Mapped[int | None] = mapped_column(ForeignKey("fleet_defects.id", ondelete="SET NULL"))
    job_number: Mapped[str] = mapped_column(String(80), nullable=False)
    maintenance_type: Mapped[str] = mapped_column(String(32), nullable=False, default="scheduled")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    vendor: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft", index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    approved_by: Mapped[str | None] = mapped_column(String(255))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    downtime_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    downtime_ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    odometer_km: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    engine_hours: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    labour_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    parts_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    other_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    total_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    invoice_reference: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)


class FleetAuditEvent(Base):
    __tablename__ = "fleet_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("fleet_assets.id", ondelete="SET NULL"), index=True)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id", ondelete="SET NULL"), index=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(80))
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
