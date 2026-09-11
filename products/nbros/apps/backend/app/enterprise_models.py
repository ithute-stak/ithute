from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, Uuid, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OperationsSetting(Base):
    __tablename__ = "operations_settings"

    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), primary_key=True)
    workshop_approval_threshold: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("5000"))
    procurement_approval_threshold: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("20000"))
    vehicle_replacement_age_years: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    vehicle_replacement_mileage: Mapped[int] = mapped_column(Integer, nullable=False, default=250000)


class Supplier(Base):
    __tablename__ = "operations_suppliers"
    __table_args__ = (UniqueConstraint("branch_id", "name", name="uq_operations_supplier_branch_name"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    supplier_type: Mapped[str] = mapped_column(String(60), nullable=False, default="general")
    contact_person: Mapped[str | None] = mapped_column(String(160))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(80))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class WorkshopTechnician(Base):
    __tablename__ = "workshop_technicians"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    employee_number: Mapped[str | None] = mapped_column(String(80))
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    specialty: Mapped[str | None] = mapped_column(String(160))
    hourly_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class WorkshopBay(Base):
    __tablename__ = "workshop_bays"
    __table_args__ = (UniqueConstraint("branch_id", "code", name="uq_workshop_bay_branch_code"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class WorkshopJobCard(Base):
    __tablename__ = "workshop_job_cards"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False)
    maintenance_work_order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("maintenance_work_orders.id", ondelete="SET NULL"))
    technician_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workshop_technicians.id", ondelete="SET NULL"))
    bay_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workshop_bays.id", ondelete="SET NULL"))
    external_supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("operations_suppliers.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="open")
    priority: Mapped[str] = mapped_column(String(30), nullable=False, default="normal")
    complaint: Mapped[str] = mapped_column(Text, nullable=False)
    diagnosis: Mapped[str | None] = mapped_column(Text)
    work_performed: Mapped[str | None] = mapped_column(Text)
    expected_release_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    labour_hours: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    labour_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    external_quote: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    external_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    service_type: Mapped[str | None] = mapped_column(String(100))
    service_mileage: Mapped[int | None] = mapped_column(Integer)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkshopJobPart(Base):
    __tablename__ = "workshop_job_parts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workshop_job_cards.id", ondelete="CASCADE"), nullable=False)
    inventory_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fleet_inventory_items.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class PurchaseRequisition(Base):
    __tablename__ = "purchase_requisitions"
    __table_args__ = (UniqueConstraint("branch_id", "reference", name="uq_purchase_requisition_branch_reference"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    reference: Mapped[str] = mapped_column(String(80), nullable=False)
    requested_by_profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    total_estimate: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending_approval")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class PurchaseRequisitionItem(Base):
    __tablename__ = "purchase_requisition_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    requisition_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("purchase_requisitions.id", ondelete="CASCADE"), nullable=False)
    inventory_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fleet_inventory_items.id", ondelete="SET NULL"))
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    estimated_unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (UniqueConstraint("branch_id", "reference", name="uq_purchase_order_branch_reference"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    requisition_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("purchase_requisitions.id", ondelete="RESTRICT"), nullable=False)
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("operations_suppliers.id", ondelete="RESTRICT"), nullable=False)
    reference: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="issued")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    expected_at: Mapped[date | None] = mapped_column(Date)


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False)
    inventory_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fleet_inventory_items.id", ondelete="SET NULL"))
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    received_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)


class GoodsReceipt(Base):
    __tablename__ = "goods_receipts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("purchase_orders.id", ondelete="RESTRICT"), nullable=False)
    reference: Mapped[str] = mapped_column(String(100), nullable=False)
    received_by_profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))
    notes: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class TyreAsset(Base):
    __tablename__ = "tyre_assets"
    __table_args__ = (UniqueConstraint("branch_id", "serial_number", name="uq_tyre_branch_serial"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    serial_number: Mapped[str] = mapped_column(String(120), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(100))
    size: Mapped[str | None] = mapped_column(String(80))
    purchase_date: Mapped[date | None] = mapped_column(Date)
    purchase_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="in_stock")
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vehicles.id", ondelete="SET NULL"))
    wheel_position: Mapped[str | None] = mapped_column(String(80))
    fitted_at_mileage: Mapped[int | None] = mapped_column(Integer)
    current_tread_mm: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    fitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DriverCredential(Base):
    __tablename__ = "driver_credentials"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    driver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("drivers.id", ondelete="CASCADE"), nullable=False)
    credential_type: Mapped[str] = mapped_column(String(100), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(160))
    issue_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)


class DispatchRequest(Base):
    __tablename__ = "dispatch_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    requested_by_profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))
    vehicle_type: Mapped[str] = mapped_column(String(100), nullable=False)
    driver_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("drivers.id", ondelete="SET NULL"))
    assigned_vehicle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vehicles.id", ondelete="SET NULL"))
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vehicle_reservations.id", ondelete="SET NULL"))
    trip_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("trips.id", ondelete="SET NULL"))
    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(String(255), nullable=False)
    passenger_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    load_description: Mapped[str | None] = mapped_column(Text)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    approved_by_profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class InsuranceClaim(Base):
    __tablename__ = "insurance_claims"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False)
    accident_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("accident_records.id", ondelete="SET NULL"))
    insurer: Mapped[str | None] = mapped_column(String(160))
    claim_number: Mapped[str | None] = mapped_column(String(160))
    police_reference: Mapped[str | None] = mapped_column(String(160))
    claim_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    excess_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="open")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TelematicsEvent(Base):
    __tablename__ = "telematics_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False, default="manual")
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    odometer_km: Mapped[int | None] = mapped_column(Integer)
    speed_kph: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    payload_json: Mapped[str | None] = mapped_column(Text)


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    workflow_key: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    requested_by_profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    reason: Mapped[str | None] = mapped_column(Text)
    decided_by_profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))
    decision_note: Mapped[str | None] = mapped_column(Text)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branches.id", ondelete="SET NULL"))
    actor_profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(120))
    detail_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class BranchFleetBudget(Base):
    __tablename__ = "branch_fleet_budgets"
    __table_args__ = (UniqueConstraint("branch_id", "year", "month", name="uq_branch_fleet_budget_period"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    budget_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
