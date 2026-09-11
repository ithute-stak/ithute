from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import current_claims
from .db import SessionLocal
from .enterprise_models import (
    ApprovalRequest,
    AuditEvent,
    BranchFleetBudget,
    DispatchRequest,
    DriverCredential,
    GoodsReceipt,
    InsuranceClaim,
    OperationsSetting,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseRequisition,
    PurchaseRequisitionItem,
    Supplier,
    TelematicsEvent,
    TyreAsset,
    WorkshopBay,
    WorkshopJobCard,
    WorkshopJobPart,
    WorkshopTechnician,
)
from .fleet import _driver, _profile, _require_branch, _vehicle
from .fleet_engine import evaluate_vehicle, match_vehicles
from .fleet_inventory import InventoryItem, InventoryMovement
from .models import AccidentRecord, Driver, FuelRecord, MaintenanceWorkOrder, Reservation, ServiceRecord, Trip, Vehicle

router = APIRouter(prefix="/api/v1/operations", tags=["operations"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _money(value: Decimal | None) -> float:
    return float(value or Decimal("0"))


def _setting(db: Session, branch_id: uuid.UUID) -> OperationsSetting:
    row = db.get(OperationsSetting, branch_id)
    if row is None:
        row = OperationsSetting(branch_id=branch_id)
        db.add(row)
        db.flush()
    return row


def _audit(db: Session, profile_id: uuid.UUID | None, branch_id: uuid.UUID | None, action: str, entity_type: str, entity_id: Any = None, detail: dict[str, Any] | None = None) -> None:
    db.add(AuditEvent(branch_id=branch_id, actor_profile_id=profile_id, action=action, entity_type=entity_type, entity_id=str(entity_id) if entity_id is not None else None, detail_json=json.dumps(detail, default=str, ensure_ascii=False) if detail else None))


def _branch_row(db: Session, model, row_id: uuid.UUID, branch_id: uuid.UUID, label: str):
    row = db.get(model, row_id)
    if row is None or getattr(row, "branch_id", None) != branch_id:
        raise HTTPException(status_code=404, detail=f"{label} not found in branch")
    return row


def _approval(db: Session, *, branch_id: uuid.UUID, profile_id: uuid.UUID, workflow_key: str, entity_type: str, entity_id: uuid.UUID, amount: Decimal | None, reason: str) -> ApprovalRequest:
    existing = db.scalar(select(ApprovalRequest).where(ApprovalRequest.branch_id == branch_id, ApprovalRequest.entity_type == entity_type, ApprovalRequest.entity_id == entity_id, ApprovalRequest.status == "pending"))
    if existing:
        return existing
    row = ApprovalRequest(branch_id=branch_id, workflow_key=workflow_key, entity_type=entity_type, entity_id=entity_id, requested_by_profile_id=profile_id, amount=amount, reason=reason)
    db.add(row)
    db.flush()
    return row


class OperationsSettingUpdate(BaseModel):
    workshop_approval_threshold: Decimal = Field(ge=0)
    procurement_approval_threshold: Decimal = Field(ge=0)
    vehicle_replacement_age_years: int = Field(ge=1, le=50)
    vehicle_replacement_mileage: int = Field(ge=10000, le=2_000_000)


class SupplierCreate(BaseModel):
    branch_id: uuid.UUID
    name: str = Field(min_length=1, max_length=180)
    supplier_type: str = Field(default="general", max_length=60)
    contact_person: str | None = Field(default=None, max_length=160)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=80)


class TechnicianCreate(BaseModel):
    branch_id: uuid.UUID
    full_name: str = Field(min_length=1, max_length=160)
    employee_number: str | None = Field(default=None, max_length=80)
    specialty: str | None = Field(default=None, max_length=160)
    hourly_rate: Decimal | None = Field(default=None, ge=0)


class BayCreate(BaseModel):
    branch_id: uuid.UUID
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=120)


class WorkshopJobCreate(BaseModel):
    branch_id: uuid.UUID
    vehicle_id: uuid.UUID
    complaint: str = Field(min_length=1, max_length=4000)
    priority: str = Field(default="normal", pattern=r"^(low|normal|high|critical)$")
    technician_id: uuid.UUID | None = None
    bay_id: uuid.UUID | None = None
    external_supplier_id: uuid.UUID | None = None
    external_quote: Decimal | None = Field(default=None, ge=0)
    expected_release_at: datetime | None = None
    service_type: str | None = Field(default=None, max_length=100)
    service_mileage: int | None = Field(default=None, ge=0)


class WorkshopJobUpdate(BaseModel):
    status: str | None = Field(default=None, pattern=r"^(open|diagnosing|waiting_parts|pending_approval|in_progress|completed|cancelled)$")
    diagnosis: str | None = Field(default=None, max_length=8000)
    work_performed: str | None = Field(default=None, max_length=8000)
    technician_id: uuid.UUID | None = None
    bay_id: uuid.UUID | None = None
    expected_release_at: datetime | None = None
    labour_hours: Decimal | None = Field(default=None, ge=0)
    labour_cost: Decimal | None = Field(default=None, ge=0)
    external_cost: Decimal | None = Field(default=None, ge=0)


class WorkshopPartIssue(BaseModel):
    inventory_item_id: uuid.UUID
    quantity: Decimal = Field(gt=0)
    unit_cost: Decimal | None = Field(default=None, ge=0)


class RequisitionLine(BaseModel):
    inventory_item_id: uuid.UUID | None = None
    description: str = Field(min_length=1, max_length=255)
    quantity: Decimal = Field(gt=0)
    estimated_unit_cost: Decimal | None = Field(default=None, ge=0)


class RequisitionCreate(BaseModel):
    branch_id: uuid.UUID
    purpose: str = Field(min_length=1, max_length=4000)
    lines: list[RequisitionLine] = Field(min_length=1, max_length=100)


class RequisitionDecision(BaseModel):
    decision: str = Field(pattern=r"^(approve|reject)$")
    note: str | None = Field(default=None, max_length=2000)


class PurchaseOrderCreate(BaseModel):
    supplier_id: uuid.UUID
    expected_at: date | None = None


class ReceiptLine(BaseModel):
    purchase_order_item_id: uuid.UUID
    quantity: Decimal = Field(gt=0)


class GoodsReceiptCreate(BaseModel):
    reference: str = Field(min_length=1, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)
    lines: list[ReceiptLine] = Field(min_length=1, max_length=100)


class TyreCreate(BaseModel):
    branch_id: uuid.UUID
    serial_number: str = Field(min_length=1, max_length=120)
    brand: str | None = Field(default=None, max_length=100)
    size: str | None = Field(default=None, max_length=80)
    purchase_date: date | None = None
    purchase_cost: Decimal | None = Field(default=None, ge=0)
    current_tread_mm: Decimal | None = Field(default=None, ge=0)


class TyreFit(BaseModel):
    vehicle_id: uuid.UUID
    wheel_position: str = Field(min_length=1, max_length=80)
    fitted_at_mileage: int = Field(ge=0)
    current_tread_mm: Decimal | None = Field(default=None, ge=0)


class CredentialCreate(BaseModel):
    branch_id: uuid.UUID
    driver_id: uuid.UUID
    credential_type: str = Field(min_length=1, max_length=100)
    reference: str | None = Field(default=None, max_length=160)
    issue_date: date | None = None
    expiry_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)


class DispatchCreate(BaseModel):
    branch_id: uuid.UUID
    vehicle_type: str = Field(min_length=1, max_length=100)
    driver_id: uuid.UUID | None = None
    destination: str = Field(min_length=1, max_length=255)
    purpose: str = Field(min_length=1, max_length=255)
    passenger_count: int = Field(default=0, ge=0, le=200)
    load_description: str | None = Field(default=None, max_length=4000)
    start_at: datetime
    end_at: datetime


class DispatchApprove(BaseModel):
    vehicle_id: uuid.UUID | None = None


class ClaimCreate(BaseModel):
    branch_id: uuid.UUID
    vehicle_id: uuid.UUID
    accident_id: uuid.UUID | None = None
    insurer: str | None = Field(default=None, max_length=160)
    claim_number: str | None = Field(default=None, max_length=160)
    police_reference: str | None = Field(default=None, max_length=160)
    claim_amount: Decimal | None = Field(default=None, ge=0)
    excess_amount: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=4000)


class ClaimUpdate(BaseModel):
    status: str | None = Field(default=None, pattern=r"^(open|submitted|assessing|approved|rejected|paid|closed)$")
    claim_number: str | None = Field(default=None, max_length=160)
    claim_amount: Decimal | None = Field(default=None, ge=0)
    excess_amount: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=4000)


class TelematicsCreate(BaseModel):
    branch_id: uuid.UUID
    vehicle_id: uuid.UUID
    provider: str = Field(default="manual", max_length=100)
    event_type: str = Field(min_length=1, max_length=80)
    occurred_at: datetime
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    odometer_km: int | None = Field(default=None, ge=0)
    speed_kph: Decimal | None = Field(default=None, ge=0)
    payload: dict[str, Any] | None = None


class ApprovalDecision(BaseModel):
    decision: str = Field(pattern=r"^(approve|reject)$")
    note: str | None = Field(default=None, max_length=2000)


class BudgetUpsert(BaseModel):
    branch_id: uuid.UUID
    year: int = Field(ge=2000, le=2200)
    month: int = Field(ge=1, le=12)
    budget_amount: Decimal = Field(ge=0)
    notes: str | None = Field(default=None, max_length=2000)


def _job_out(row: WorkshopJobCard) -> dict[str, Any]:
    return {"id": str(row.id), "branch_id": str(row.branch_id), "vehicle_id": str(row.vehicle_id), "maintenance_work_order_id": str(row.maintenance_work_order_id) if row.maintenance_work_order_id else None, "status": row.status, "priority": row.priority, "complaint": row.complaint, "diagnosis": row.diagnosis, "work_performed": row.work_performed, "technician_id": str(row.technician_id) if row.technician_id else None, "bay_id": str(row.bay_id) if row.bay_id else None, "external_supplier_id": str(row.external_supplier_id) if row.external_supplier_id else None, "external_quote": _money(row.external_quote), "labour_hours": _money(row.labour_hours), "labour_cost": _money(row.labour_cost), "external_cost": _money(row.external_cost), "expected_release_at": row.expected_release_at.isoformat() if row.expected_release_at else None, "opened_at": row.opened_at.isoformat(), "completed_at": row.completed_at.isoformat() if row.completed_at else None}


def _requisition_out(db: Session, row: PurchaseRequisition) -> dict[str, Any]:
    lines = list(db.scalars(select(PurchaseRequisitionItem).where(PurchaseRequisitionItem.requisition_id == row.id)))
    return {"id": str(row.id), "reference": row.reference, "purpose": row.purpose, "total_estimate": _money(row.total_estimate), "status": row.status, "created_at": row.created_at.isoformat(), "lines": [{"id": str(line.id), "inventory_item_id": str(line.inventory_item_id) if line.inventory_item_id else None, "description": line.description, "quantity": float(line.quantity), "estimated_unit_cost": _money(line.estimated_unit_cost)} for line in lines]}


def _tco_rows(db: Session, branch_id: uuid.UUID) -> list[dict[str, Any]]:
    vehicles = list(db.scalars(select(Vehicle).where(Vehicle.branch_id == branch_id).order_by(Vehicle.registration_plate)))
    rows: list[dict[str, Any]] = []
    for vehicle in vehicles:
        fuel = db.scalar(select(func.coalesce(func.sum(FuelRecord.cost), 0)).where(FuelRecord.vehicle_id == vehicle.id)) or 0
        service = db.scalar(select(func.coalesce(func.sum(ServiceRecord.cost), 0)).where(ServiceRecord.vehicle_id == vehicle.id)) or 0
        labour = db.scalar(select(func.coalesce(func.sum(WorkshopJobCard.labour_cost), 0)).where(WorkshopJobCard.vehicle_id == vehicle.id, WorkshopJobCard.status == "completed")) or 0
        external = db.scalar(select(func.coalesce(func.sum(WorkshopJobCard.external_cost), 0)).where(WorkshopJobCard.vehicle_id == vehicle.id, WorkshopJobCard.status == "completed")) or 0
        tyres = db.scalar(select(func.coalesce(func.sum(TyreAsset.purchase_cost), 0)).where(TyreAsset.vehicle_id == vehicle.id)) or 0
        claims_excess = db.scalar(select(func.coalesce(func.sum(InsuranceClaim.excess_amount), 0)).where(InsuranceClaim.vehicle_id == vehicle.id)) or 0
        total = Decimal(str(fuel)) + Decimal(str(service)) + Decimal(str(labour)) + Decimal(str(external)) + Decimal(str(tyres)) + Decimal(str(claims_excess))
        kilometres = max(vehicle.current_mileage, 0)
        rows.append({"vehicle_id": str(vehicle.id), "registration_plate": vehicle.registration_plate, "make": vehicle.make, "model": vehicle.model, "current_mileage": kilometres, "known_cost": float(total), "cost_per_recorded_km": round(float(total) / kilometres, 2) if kilometres else None, "fuel": float(fuel), "service": float(service), "workshop_labour": float(labour), "external_repairs": float(external), "tyres": float(tyres), "insurance_excess": float(claims_excess)})
    return rows


@router.get("/summary")
def operations_summary(branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id)
        vehicles = list(db.scalars(select(Vehicle).where(Vehicle.branch_id == branch_id, Vehicle.is_active.is_(True))))
        snapshots = [evaluate_vehicle(db, vehicle) for vehicle in vehicles]
        return {"fleet": {"vehicles": len(vehicles), "ready": sum(1 for x in snapshots if x["readiness"] == "green"), "attention": sum(1 for x in snapshots if x["readiness"] == "orange"), "blocked": sum(1 for x in snapshots if x["readiness"] == "red")}, "workshop": {"open_jobs": db.scalar(select(func.count()).select_from(WorkshopJobCard).where(WorkshopJobCard.branch_id == branch_id, WorkshopJobCard.status.notin_(["completed", "cancelled"]))) or 0, "waiting_parts": db.scalar(select(func.count()).select_from(WorkshopJobCard).where(WorkshopJobCard.branch_id == branch_id, WorkshopJobCard.status == "waiting_parts")) or 0}, "stores": {"low_stock": db.scalar(select(func.count()).select_from(InventoryItem).where(InventoryItem.branch_id == branch_id, InventoryItem.quantity_on_hand <= InventoryItem.reorder_level)) or 0, "out_of_stock": db.scalar(select(func.count()).select_from(InventoryItem).where(InventoryItem.branch_id == branch_id, InventoryItem.quantity_on_hand <= 0)) or 0}, "procurement": {"pending_requisitions": db.scalar(select(func.count()).select_from(PurchaseRequisition).where(PurchaseRequisition.branch_id == branch_id, PurchaseRequisition.status.in_(["pending_approval", "approved", "ordered"]))) or 0, "open_orders": db.scalar(select(func.count()).select_from(PurchaseOrder).where(PurchaseOrder.branch_id == branch_id, PurchaseOrder.status.in_(["issued", "part_received"]))) or 0}, "dispatch": {"pending": db.scalar(select(func.count()).select_from(DispatchRequest).where(DispatchRequest.branch_id == branch_id, DispatchRequest.status == "pending")) or 0, "active": db.scalar(select(func.count()).select_from(DispatchRequest).where(DispatchRequest.branch_id == branch_id, DispatchRequest.status.in_(["approved", "active"]))) or 0}, "risk": {"open_claims": db.scalar(select(func.count()).select_from(InsuranceClaim).where(InsuranceClaim.branch_id == branch_id, InsuranceClaim.status.notin_(["paid", "closed", "rejected"]))) or 0, "pending_approvals": db.scalar(select(func.count()).select_from(ApprovalRequest).where(ApprovalRequest.branch_id == branch_id, ApprovalRequest.status == "pending")) or 0}}


@router.get("/settings")
def get_operations_settings(branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id); row = _setting(db, branch_id)
        return {"workshop_approval_threshold": _money(row.workshop_approval_threshold), "procurement_approval_threshold": _money(row.procurement_approval_threshold), "vehicle_replacement_age_years": row.vehicle_replacement_age_years, "vehicle_replacement_mileage": row.vehicle_replacement_mileage}


@router.put("/settings")
def update_operations_settings(payload: OperationsSettingUpdate, branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id, write=True); row = _setting(db, branch_id)
        for key, value in payload.model_dump().items(): setattr(row, key, value)
        _audit(db, profile.id, branch_id, "operations.settings.updated", "operations_setting", branch_id, payload.model_dump()); db.commit(); return payload.model_dump()


@router.get("/suppliers")
def list_suppliers(branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id)
        rows = list(db.scalars(select(Supplier).where(Supplier.branch_id == branch_id).order_by(Supplier.name)))
        return [{"id": str(row.id), "name": row.name, "supplier_type": row.supplier_type, "contact_person": row.contact_person, "email": row.email, "phone": row.phone, "is_active": row.is_active} for row in rows]


@router.post("/suppliers", status_code=201)
def create_supplier(payload: SupplierCreate, claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, payload.branch_id, write=True); row = Supplier(**payload.model_dump()); row.name = row.name.strip(); db.add(row)
        try: db.flush()
        except IntegrityError: db.rollback(); raise HTTPException(status_code=409, detail="supplier already exists in branch") from None
        _audit(db, profile.id, payload.branch_id, "supplier.created", "supplier", row.id, {"name": row.name}); db.commit(); return {"id": str(row.id), "name": row.name}


@router.get("/workshop")
def workshop_board(branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id)
        jobs = list(db.scalars(select(WorkshopJobCard).where(WorkshopJobCard.branch_id == branch_id).order_by(WorkshopJobCard.opened_at.desc()).limit(200)))
        technicians = list(db.scalars(select(WorkshopTechnician).where(WorkshopTechnician.branch_id == branch_id, WorkshopTechnician.is_active.is_(True)).order_by(WorkshopTechnician.full_name)))
        bays = list(db.scalars(select(WorkshopBay).where(WorkshopBay.branch_id == branch_id, WorkshopBay.is_active.is_(True)).order_by(WorkshopBay.code)))
        return {"jobs": [_job_out(row) for row in jobs], "technicians": [{"id": str(row.id), "full_name": row.full_name, "specialty": row.specialty, "hourly_rate": _money(row.hourly_rate)} for row in technicians], "bays": [{"id": str(row.id), "code": row.code, "name": row.name} for row in bays]}


@router.post("/workshop/technicians", status_code=201)
def create_technician(payload: TechnicianCreate, claims: dict = Depends(current_claims)) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, payload.branch_id, write=True); row = WorkshopTechnician(**payload.model_dump()); db.add(row); db.flush(); _audit(db, profile.id, payload.branch_id, "workshop.technician.created", "workshop_technician", row.id, {"name": row.full_name}); db.commit(); return {"id": str(row.id)}


@router.post("/workshop/bays", status_code=201)
def create_bay(payload: BayCreate, claims: dict = Depends(current_claims)) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, payload.branch_id, write=True); row = WorkshopBay(branch_id=payload.branch_id, code=payload.code.strip().upper(), name=payload.name.strip()); db.add(row)
        try: db.flush()
        except IntegrityError: db.rollback(); raise HTTPException(status_code=409, detail="workshop bay code already exists") from None
        _audit(db, profile.id, payload.branch_id, "workshop.bay.created", "workshop_bay", row.id, {"code": row.code}); db.commit(); return {"id": str(row.id)}


@router.post("/workshop/jobs", status_code=201)
def create_workshop_job(payload: WorkshopJobCreate, claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, payload.branch_id, write=True); vehicle = _vehicle(db, payload.branch_id, payload.vehicle_id)
        if payload.technician_id: _branch_row(db, WorkshopTechnician, payload.technician_id, payload.branch_id, "technician")
        if payload.bay_id: _branch_row(db, WorkshopBay, payload.bay_id, payload.branch_id, "workshop bay")
        if payload.external_supplier_id: _branch_row(db, Supplier, payload.external_supplier_id, payload.branch_id, "supplier")
        maintenance = MaintenanceWorkOrder(branch_id=payload.branch_id, vehicle_id=vehicle.id, description=payload.complaint, status="open", expected_release_at=payload.expected_release_at); db.add(maintenance); db.flush()
        row = WorkshopJobCard(**payload.model_dump(), maintenance_work_order_id=maintenance.id); setting = _setting(db, payload.branch_id)
        if row.external_quote is not None and row.external_quote >= setting.workshop_approval_threshold: row.status = "pending_approval"
        db.add(row); db.flush()
        if row.status == "pending_approval": _approval(db, branch_id=payload.branch_id, profile_id=profile.id, workflow_key="workshop_high_value", entity_type="workshop_job", entity_id=row.id, amount=row.external_quote, reason="External repair quote exceeds the branch approval threshold.")
        _audit(db, profile.id, payload.branch_id, "workshop.job.created", "workshop_job", row.id, {"vehicle_id": str(vehicle.id), "complaint": row.complaint}); db.commit(); db.refresh(row); return _job_out(row)


@router.patch("/workshop/jobs/{job_id}")
def update_workshop_job(job_id: uuid.UUID, payload: WorkshopJobUpdate, branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id, write=True); row = _branch_row(db, WorkshopJobCard, job_id, branch_id, "workshop job"); values = payload.model_dump(exclude_unset=True)
        if values.get("technician_id"): _branch_row(db, WorkshopTechnician, values["technician_id"], branch_id, "technician")
        if values.get("bay_id"): _branch_row(db, WorkshopBay, values["bay_id"], branch_id, "workshop bay")
        for key, value in values.items(): setattr(row, key, value)
        maintenance = db.get(MaintenanceWorkOrder, row.maintenance_work_order_id) if row.maintenance_work_order_id else None
        if maintenance:
            maintenance.expected_release_at = row.expected_release_at
            if row.status in {"open", "diagnosing", "waiting_parts", "pending_approval"}: maintenance.status = "open"
            elif row.status == "in_progress": maintenance.status = "in_progress"
            elif row.status in {"completed", "cancelled"}: maintenance.status = "closed"; maintenance.closed_at = maintenance.closed_at or _utcnow()
        _audit(db, profile.id, branch_id, "workshop.job.updated", "workshop_job", row.id, values); db.commit(); db.refresh(row); return _job_out(row)


@router.post("/workshop/jobs/{job_id}/parts", status_code=201)
def issue_workshop_part(job_id: uuid.UUID, payload: WorkshopPartIssue, branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id, write=True); job = _branch_row(db, WorkshopJobCard, job_id, branch_id, "workshop job")
        if job.status in {"completed", "cancelled"}: raise HTTPException(status_code=409, detail="job is already closed")
        item = db.get(InventoryItem, payload.inventory_item_id)
        if item is None or item.branch_id != branch_id: raise HTTPException(status_code=404, detail="inventory item not found in branch")
        if item.quantity_on_hand < payload.quantity: job.status = "waiting_parts"; db.commit(); raise HTTPException(status_code=409, detail=f"insufficient stock for {item.name}; workshop job moved to waiting_parts")
        item.quantity_on_hand -= payload.quantity; db.add(WorkshopJobPart(branch_id=branch_id, job_id=job.id, inventory_item_id=item.id, quantity=payload.quantity, unit_cost=payload.unit_cost)); db.add(InventoryMovement(branch_id=branch_id, item_id=item.id, quantity_delta=-payload.quantity, movement_type="issue", reference_type="workshop_job", reference_id=str(job.id), notes=f"Issued to workshop job {job.id}.", recorded_by_profile_id=profile.id))
        if job.status == "waiting_parts": job.status = "in_progress"
        _audit(db, profile.id, branch_id, "workshop.part.issued", "workshop_job", job.id, {"sku": item.sku, "quantity": str(payload.quantity)}); db.commit(); return {"job_id": str(job.id), "inventory_item_id": str(item.id), "quantity_on_hand": float(item.quantity_on_hand)}


@router.post("/workshop/jobs/{job_id}/complete")
def complete_workshop_job(job_id: uuid.UUID, branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id, write=True); job = _branch_row(db, WorkshopJobCard, job_id, branch_id, "workshop job")
        pending = db.scalar(select(ApprovalRequest.id).where(ApprovalRequest.entity_type == "workshop_job", ApprovalRequest.entity_id == job.id, ApprovalRequest.status == "pending"))
        if pending: raise HTTPException(status_code=409, detail="workshop job still has a pending approval")
        if job.status == "completed": return _job_out(job)
        job.status = "completed"; job.completed_at = _utcnow(); maintenance = db.get(MaintenanceWorkOrder, job.maintenance_work_order_id) if job.maintenance_work_order_id else None
        if maintenance: maintenance.status = "closed"; maintenance.closed_at = job.completed_at
        parts = list(db.scalars(select(WorkshopJobPart).where(WorkshopJobPart.job_id == job.id))); parts_cost = sum((part.quantity * (part.unit_cost or Decimal("0")) for part in parts), Decimal("0")); total = (job.labour_cost or Decimal("0")) + (job.external_cost or Decimal("0")) + parts_cost; vehicle = _vehicle(db, branch_id, job.vehicle_id)
        if job.service_type and job.service_mileage is not None:
            db.add(ServiceRecord(branch_id=branch_id, vehicle_id=vehicle.id, service_date=job.completed_at.date(), mileage=job.service_mileage, service_type=job.service_type, mechanic=None, cost=total))
            if job.service_mileage > vehicle.current_mileage: vehicle.current_mileage = job.service_mileage
        _audit(db, profile.id, branch_id, "workshop.job.completed", "workshop_job", job.id, {"total_known_cost": str(total)}); db.commit(); db.refresh(job); return {**_job_out(job), "total_known_cost": float(total)}


@router.get("/procurement")
def procurement_board(branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id); requisitions = list(db.scalars(select(PurchaseRequisition).where(PurchaseRequisition.branch_id == branch_id).order_by(PurchaseRequisition.created_at.desc()).limit(100))); orders = list(db.scalars(select(PurchaseOrder).where(PurchaseOrder.branch_id == branch_id).order_by(PurchaseOrder.issued_at.desc()).limit(100)))
        return {"requisitions": [_requisition_out(db, row) for row in requisitions], "orders": [{"id": str(row.id), "reference": row.reference, "requisition_id": str(row.requisition_id), "supplier_id": str(row.supplier_id), "status": row.status, "total_amount": _money(row.total_amount), "expected_at": row.expected_at.isoformat() if row.expected_at else None} for row in orders]}


@router.post("/procurement/requisitions", status_code=201)
def create_requisition(payload: RequisitionCreate, claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, payload.branch_id, write=True); total = Decimal("0")
        for line in payload.lines:
            if line.inventory_item_id:
                item = db.get(InventoryItem, line.inventory_item_id)
                if item is None or item.branch_id != payload.branch_id: raise HTTPException(status_code=404, detail="inventory item not found in branch")
            total += line.quantity * (line.estimated_unit_cost or Decimal("0"))
        reference = f"REQ-{_utcnow():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"; row = PurchaseRequisition(branch_id=payload.branch_id, reference=reference, requested_by_profile_id=profile.id, purpose=payload.purpose, total_estimate=total, status="pending_approval"); db.add(row); db.flush()
        for line in payload.lines: db.add(PurchaseRequisitionItem(requisition_id=row.id, **line.model_dump()))
        setting = _setting(db, payload.branch_id); workflow = "procurement_high_value" if total >= setting.procurement_approval_threshold else "procurement_standard"; _approval(db, branch_id=payload.branch_id, profile_id=profile.id, workflow_key=workflow, entity_type="purchase_requisition", entity_id=row.id, amount=total, reason=payload.purpose); _audit(db, profile.id, payload.branch_id, "procurement.requisition.created", "purchase_requisition", row.id, {"reference": reference, "total": str(total)}); db.commit(); db.refresh(row); return _requisition_out(db, row)


@router.post("/procurement/requisitions/{requisition_id}/decision")
def decide_requisition(requisition_id: uuid.UUID, payload: RequisitionDecision, branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id, write=True); row = _branch_row(db, PurchaseRequisition, requisition_id, branch_id, "requisition"); approval = db.scalar(select(ApprovalRequest).where(ApprovalRequest.entity_type == "purchase_requisition", ApprovalRequest.entity_id == row.id, ApprovalRequest.status == "pending"))
        if approval is None: raise HTTPException(status_code=409, detail="no pending approval exists for this requisition")
        approval.status = "approved" if payload.decision == "approve" else "rejected"; approval.decided_by_profile_id = profile.id; approval.decision_note = payload.note; approval.decided_at = _utcnow(); row.status = approval.status; _audit(db, profile.id, branch_id, f"procurement.requisition.{approval.status}", "purchase_requisition", row.id, {"note": payload.note}); db.commit(); return {"status": row.status}


@router.post("/procurement/requisitions/{requisition_id}/order", status_code=201)
def create_purchase_order(requisition_id: uuid.UUID, payload: PurchaseOrderCreate, branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id, write=True); requisition = _branch_row(db, PurchaseRequisition, requisition_id, branch_id, "requisition")
        if requisition.status != "approved": raise HTTPException(status_code=409, detail="requisition must be approved before ordering")
        supplier = _branch_row(db, Supplier, payload.supplier_id, branch_id, "supplier"); reference = f"PO-{_utcnow():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"; order = PurchaseOrder(branch_id=branch_id, requisition_id=requisition.id, supplier_id=supplier.id, reference=reference, total_amount=requisition.total_estimate, expected_at=payload.expected_at); db.add(order); db.flush(); lines = list(db.scalars(select(PurchaseRequisitionItem).where(PurchaseRequisitionItem.requisition_id == requisition.id)))
        for line in lines: db.add(PurchaseOrderItem(purchase_order_id=order.id, inventory_item_id=line.inventory_item_id, description=line.description, quantity=line.quantity, unit_cost=line.estimated_unit_cost or Decimal("0")))
        requisition.status = "ordered"; _audit(db, profile.id, branch_id, "procurement.order.created", "purchase_order", order.id, {"reference": reference, "supplier": supplier.name}); db.commit(); return {"id": str(order.id), "reference": reference, "status": order.status, "total_amount": _money(order.total_amount)}


@router.post("/procurement/purchase-orders/{purchase_order_id}/receive", status_code=201)
def receive_purchase_order(purchase_order_id: uuid.UUID, payload: GoodsReceiptCreate, branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id, write=True); order = _branch_row(db, PurchaseOrder, purchase_order_id, branch_id, "purchase order")
        if order.status == "received": raise HTTPException(status_code=409, detail="purchase order is already fully received")
        receipt = GoodsReceipt(branch_id=branch_id, purchase_order_id=order.id, reference=payload.reference, received_by_profile_id=profile.id, notes=payload.notes); db.add(receipt); db.flush()
        for line in payload.lines:
            order_line = db.get(PurchaseOrderItem, line.purchase_order_item_id)
            if order_line is None or order_line.purchase_order_id != order.id: raise HTTPException(status_code=404, detail="purchase order line not found")
            outstanding = order_line.quantity - order_line.received_quantity
            if line.quantity > outstanding: raise HTTPException(status_code=409, detail=f"receipt quantity exceeds outstanding quantity for {order_line.description}")
            order_line.received_quantity += line.quantity
            if order_line.inventory_item_id:
                item = db.get(InventoryItem, order_line.inventory_item_id)
                if item and item.branch_id == branch_id: item.quantity_on_hand += line.quantity; db.add(InventoryMovement(branch_id=branch_id, item_id=item.id, quantity_delta=line.quantity, movement_type="receipt", reference_type="purchase_order", reference_id=str(order.id), notes=f"Goods receipt {receipt.reference}.", recorded_by_profile_id=profile.id))
        all_lines = list(db.scalars(select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == order.id))); order.status = "received" if all(line.received_quantity >= line.quantity for line in all_lines) else "part_received"
        if order.status == "received":
            requisition = db.get(PurchaseRequisition, order.requisition_id)
            if requisition: requisition.status = "received"
        _audit(db, profile.id, branch_id, "procurement.goods.received", "goods_receipt", receipt.id, {"purchase_order_id": str(order.id), "reference": receipt.reference}); db.commit(); return {"receipt_id": str(receipt.id), "purchase_order_status": order.status}


@router.get("/dispatch")
def dispatch_board(branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id); rows = list(db.scalars(select(DispatchRequest).where(DispatchRequest.branch_id == branch_id).order_by(DispatchRequest.created_at.desc()).limit(200)))
        return [{"id": str(row.id), "vehicle_type": row.vehicle_type, "driver_id": str(row.driver_id) if row.driver_id else None, "assigned_vehicle_id": str(row.assigned_vehicle_id) if row.assigned_vehicle_id else None, "destination": row.destination, "purpose": row.purpose, "start_at": row.start_at.isoformat(), "end_at": row.end_at.isoformat(), "status": row.status} for row in rows]


@router.post("/dispatch/requests", status_code=201)
def create_dispatch_request(payload: DispatchCreate, claims: dict = Depends(current_claims)) -> dict[str, Any]:
    if payload.end_at <= payload.start_at: raise HTTPException(status_code=422, detail="dispatch end must be after start")
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, payload.branch_id, write=True)
        if payload.driver_id: _driver(db, payload.branch_id, payload.driver_id)
        row = DispatchRequest(**payload.model_dump(), requested_by_profile_id=profile.id); db.add(row); db.flush(); _audit(db, profile.id, payload.branch_id, "dispatch.request.created", "dispatch_request", row.id, {"destination": row.destination, "vehicle_type": row.vehicle_type}); db.commit(); return {"id": str(row.id), "status": row.status}


@router.get("/dispatch/requests/{request_id}/recommend")
def recommend_dispatch(request_id: uuid.UUID, branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id); row = _branch_row(db, DispatchRequest, request_id, branch_id, "dispatch request"); return match_vehicles(db, branch_id=branch_id, vehicle_type=row.vehicle_type, start_at=row.start_at, end_at=row.end_at, driver_id=row.driver_id)


@router.post("/dispatch/requests/{request_id}/approve")
def approve_dispatch(request_id: uuid.UUID, payload: DispatchApprove, branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id, write=True); row = _branch_row(db, DispatchRequest, request_id, branch_id, "dispatch request")
        if row.status != "pending": raise HTTPException(status_code=409, detail="dispatch request is not pending")
        matching = match_vehicles(db, branch_id=branch_id, vehicle_type=row.vehicle_type, start_at=row.start_at, end_at=row.end_at, driver_id=row.driver_id)
        if matching.get("driver_error"): raise HTTPException(status_code=409, detail=matching["driver_error"])
        recommended = matching.get("recommended"); vehicle_id = payload.vehicle_id or (uuid.UUID(recommended["vehicle"]["id"]) if recommended else None)
        if vehicle_id is None: raise HTTPException(status_code=409, detail="no suitable vehicle is available")
        available_ids = {item["vehicle"]["id"] for item in matching["available"]}
        if str(vehicle_id) not in available_ids: raise HTTPException(status_code=409, detail="selected vehicle does not pass Fleet eligibility for the requested period")
        vehicle = _vehicle(db, branch_id, vehicle_id); reservation = Reservation(branch_id=branch_id, vehicle_id=vehicle.id, driver_id=row.driver_id, purpose=f"Dispatch: {row.purpose}", start_at=row.start_at, end_at=row.end_at, status="active"); db.add(reservation); db.flush(); row.assigned_vehicle_id = vehicle.id; row.reservation_id = reservation.id; row.approved_by_profile_id = profile.id; row.status = "approved"; _audit(db, profile.id, branch_id, "dispatch.request.approved", "dispatch_request", row.id, {"vehicle_id": str(vehicle.id)}); db.commit(); return {"status": row.status, "vehicle_id": str(vehicle.id), "reservation_id": str(reservation.id)}


@router.post("/dispatch/requests/{request_id}/start")
def start_dispatch(request_id: uuid.UUID, branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id, write=True); row = _branch_row(db, DispatchRequest, request_id, branch_id, "dispatch request")
        if row.status != "approved" or not row.assigned_vehicle_id or not row.driver_id: raise HTTPException(status_code=409, detail="dispatch request needs an approved vehicle and driver before departure")
        if row.reservation_id:
            reservation = db.get(Reservation, row.reservation_id)
            if reservation: reservation.status = "cancelled"
        trip = Trip(branch_id=branch_id, vehicle_id=row.assigned_vehicle_id, driver_id=row.driver_id, destination=row.destination, purpose=row.purpose, start_at=_utcnow(), expected_return_at=row.end_at, status="active"); db.add(trip); db.flush(); row.trip_id = trip.id; row.status = "active"; _audit(db, profile.id, branch_id, "dispatch.trip.started", "dispatch_request", row.id, {"trip_id": str(trip.id)}); db.commit(); return {"status": row.status, "trip_id": str(trip.id)}


@router.post("/dispatch/requests/{request_id}/complete")
def complete_dispatch(request_id: uuid.UUID, branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id, write=True); row = _branch_row(db, DispatchRequest, request_id, branch_id, "dispatch request")
        if row.trip_id:
            trip = db.get(Trip, row.trip_id)
            if trip: trip.status = "completed"; trip.actual_return_at = _utcnow()
        row.status = "completed"; _audit(db, profile.id, branch_id, "dispatch.trip.completed", "dispatch_request", row.id); db.commit(); return {"status": row.status}


@router.get("/tyres")
def list_tyres(branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id); rows = list(db.scalars(select(TyreAsset).where(TyreAsset.branch_id == branch_id).order_by(TyreAsset.serial_number))); return [{"id": str(row.id), "serial_number": row.serial_number, "brand": row.brand, "size": row.size, "status": row.status, "vehicle_id": str(row.vehicle_id) if row.vehicle_id else None, "wheel_position": row.wheel_position, "current_tread_mm": float(row.current_tread_mm) if row.current_tread_mm is not None else None, "purchase_cost": _money(row.purchase_cost)} for row in rows]


@router.post("/tyres", status_code=201)
def create_tyre(payload: TyreCreate, claims: dict = Depends(current_claims)) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, payload.branch_id, write=True); row = TyreAsset(**payload.model_dump()); row.serial_number = row.serial_number.strip().upper(); db.add(row)
        try: db.flush()
        except IntegrityError: db.rollback(); raise HTTPException(status_code=409, detail="tyre serial number already exists in branch") from None
        _audit(db, profile.id, payload.branch_id, "tyre.created", "tyre", row.id, {"serial_number": row.serial_number}); db.commit(); return {"id": str(row.id)}


@router.post("/tyres/{tyre_id}/fit")
def fit_tyre(tyre_id: uuid.UUID, payload: TyreFit, branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id, write=True); row = _branch_row(db, TyreAsset, tyre_id, branch_id, "tyre"); _vehicle(db, branch_id, payload.vehicle_id)
        if row.vehicle_id and row.status == "fitted": raise HTTPException(status_code=409, detail="tyre is already fitted")
        row.vehicle_id = payload.vehicle_id; row.wheel_position = payload.wheel_position; row.fitted_at_mileage = payload.fitted_at_mileage; row.current_tread_mm = payload.current_tread_mm; row.fitted_at = _utcnow(); row.removed_at = None; row.status = "fitted"; _audit(db, profile.id, branch_id, "tyre.fitted", "tyre", row.id, {"vehicle_id": str(payload.vehicle_id), "position": payload.wheel_position}); db.commit(); return {"status": row.status}


@router.post("/tyres/{tyre_id}/remove")
def remove_tyre(tyre_id: uuid.UUID, branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id, write=True); row = _branch_row(db, TyreAsset, tyre_id, branch_id, "tyre"); row.vehicle_id = None; row.wheel_position = None; row.removed_at = _utcnow(); row.status = "in_stock"; _audit(db, profile.id, branch_id, "tyre.removed", "tyre", row.id); db.commit(); return {"status": row.status}


@router.get("/drivers/credentials")
def list_driver_credentials(branch_id: uuid.UUID = Query(...), driver_id: uuid.UUID | None = Query(default=None), claims: dict = Depends(current_claims)) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id); query = select(DriverCredential).where(DriverCredential.branch_id == branch_id)
        if driver_id: _driver(db, branch_id, driver_id); query = query.where(DriverCredential.driver_id == driver_id)
        rows = list(db.scalars(query.order_by(DriverCredential.expiry_date))); return [{"id": str(row.id), "driver_id": str(row.driver_id), "credential_type": row.credential_type, "reference": row.reference, "issue_date": row.issue_date.isoformat() if row.issue_date else None, "expiry_date": row.expiry_date.isoformat() if row.expiry_date else None, "notes": row.notes} for row in rows]


@router.post("/drivers/credentials", status_code=201)
def create_driver_credential(payload: CredentialCreate, claims: dict = Depends(current_claims)) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, payload.branch_id, write=True); _driver(db, payload.branch_id, payload.driver_id); row = DriverCredential(**payload.model_dump()); db.add(row); db.flush(); _audit(db, profile.id, payload.branch_id, "driver.credential.created", "driver_credential", row.id, {"type": row.credential_type, "driver_id": str(row.driver_id)}); db.commit(); return {"id": str(row.id)}


@router.get("/insurance/claims")
def list_claims(branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id); rows = list(db.scalars(select(InsuranceClaim).where(InsuranceClaim.branch_id == branch_id).order_by(InsuranceClaim.created_at.desc()))); return [{"id": str(row.id), "vehicle_id": str(row.vehicle_id), "accident_id": str(row.accident_id) if row.accident_id else None, "insurer": row.insurer, "claim_number": row.claim_number, "police_reference": row.police_reference, "claim_amount": _money(row.claim_amount), "excess_amount": _money(row.excess_amount), "status": row.status, "notes": row.notes, "created_at": row.created_at.isoformat()} for row in rows]


@router.post("/insurance/claims", status_code=201)
def create_claim(payload: ClaimCreate, claims: dict = Depends(current_claims)) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, payload.branch_id, write=True); _vehicle(db, payload.branch_id, payload.vehicle_id)
        if payload.accident_id:
            accident = db.get(AccidentRecord, payload.accident_id)
            if accident is None or accident.branch_id != payload.branch_id or accident.vehicle_id != payload.vehicle_id: raise HTTPException(status_code=404, detail="accident record does not match vehicle and branch")
        row = InsuranceClaim(**payload.model_dump()); db.add(row); db.flush(); _audit(db, profile.id, payload.branch_id, "insurance.claim.created", "insurance_claim", row.id, {"vehicle_id": str(row.vehicle_id)}); db.commit(); return {"id": str(row.id)}


@router.patch("/insurance/claims/{claim_id}")
def update_claim(claim_id: uuid.UUID, payload: ClaimUpdate, branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id, write=True); row = _branch_row(db, InsuranceClaim, claim_id, branch_id, "insurance claim"); values = payload.model_dump(exclude_unset=True)
        for key, value in values.items(): setattr(row, key, value)
        if row.status in {"paid", "closed", "rejected"}: row.resolved_at = row.resolved_at or _utcnow()
        _audit(db, profile.id, branch_id, "insurance.claim.updated", "insurance_claim", row.id, values); db.commit(); return {"status": row.status}


@router.get("/telematics/events")
def list_telematics_events(branch_id: uuid.UUID = Query(...), vehicle_id: uuid.UUID | None = Query(default=None), claims: dict = Depends(current_claims)) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id); query = select(TelematicsEvent).where(TelematicsEvent.branch_id == branch_id)
        if vehicle_id: _vehicle(db, branch_id, vehicle_id); query = query.where(TelematicsEvent.vehicle_id == vehicle_id)
        rows = list(db.scalars(query.order_by(TelematicsEvent.occurred_at.desc()).limit(500))); return [{"id": str(row.id), "vehicle_id": str(row.vehicle_id), "provider": row.provider, "event_type": row.event_type, "occurred_at": row.occurred_at.isoformat(), "latitude": float(row.latitude) if row.latitude is not None else None, "longitude": float(row.longitude) if row.longitude is not None else None, "odometer_km": row.odometer_km, "speed_kph": float(row.speed_kph) if row.speed_kph is not None else None} for row in rows]


@router.post("/telematics/events", status_code=201)
def create_telematics_event(payload: TelematicsCreate, claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, payload.branch_id, write=True); vehicle = _vehicle(db, payload.branch_id, payload.vehicle_id); values = payload.model_dump(exclude={"payload"}); row = TelematicsEvent(**values, payload_json=json.dumps(payload.payload, default=str) if payload.payload else None); db.add(row)
        if payload.odometer_km is not None and payload.odometer_km > vehicle.current_mileage: vehicle.current_mileage = payload.odometer_km
        _audit(db, profile.id, payload.branch_id, "telematics.event.recorded", "telematics_event", row.id, {"event_type": row.event_type, "provider": row.provider}); db.commit(); return {"id": str(row.id), "vehicle_mileage": vehicle.current_mileage}


@router.get("/finance/tco")
def tco(branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id); rows = _tco_rows(db, branch_id); return {"vehicles": rows, "total_known_cost": round(sum(row["known_cost"] for row in rows), 2)}


@router.get("/finance/budgets")
def list_budgets(branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id); rows = list(db.scalars(select(BranchFleetBudget).where(BranchFleetBudget.branch_id == branch_id).order_by(BranchFleetBudget.year.desc(), BranchFleetBudget.month.desc()))); return [{"id": str(row.id), "year": row.year, "month": row.month, "budget_amount": _money(row.budget_amount), "notes": row.notes} for row in rows]


@router.put("/finance/budgets")
def upsert_budget(payload: BudgetUpsert, claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, payload.branch_id, write=True); row = db.scalar(select(BranchFleetBudget).where(BranchFleetBudget.branch_id == payload.branch_id, BranchFleetBudget.year == payload.year, BranchFleetBudget.month == payload.month))
        if row is None: row = BranchFleetBudget(**payload.model_dump()); db.add(row)
        else: row.budget_amount = payload.budget_amount; row.notes = payload.notes
        db.flush(); _audit(db, profile.id, payload.branch_id, "fleet.budget.updated", "branch_fleet_budget", row.id, {"year": payload.year, "month": payload.month, "amount": str(payload.budget_amount)}); db.commit(); return {"id": str(row.id), "budget_amount": _money(row.budget_amount)}


@router.get("/approvals")
def list_approvals(branch_id: uuid.UUID = Query(...), status_filter: str | None = Query(default=None), claims: dict = Depends(current_claims)) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id); query = select(ApprovalRequest).where(ApprovalRequest.branch_id == branch_id)
        if status_filter: query = query.where(ApprovalRequest.status == status_filter)
        rows = list(db.scalars(query.order_by(ApprovalRequest.requested_at.desc()).limit(300))); return [{"id": str(row.id), "workflow_key": row.workflow_key, "entity_type": row.entity_type, "entity_id": str(row.entity_id), "status": row.status, "amount": _money(row.amount), "reason": row.reason, "requested_at": row.requested_at.isoformat(), "decided_at": row.decided_at.isoformat() if row.decided_at else None} for row in rows]


@router.post("/approvals/{approval_id}/decision")
def decide_approval(approval_id: uuid.UUID, payload: ApprovalDecision, branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id, write=True); row = _branch_row(db, ApprovalRequest, approval_id, branch_id, "approval")
        if row.status != "pending": raise HTTPException(status_code=409, detail="approval has already been decided")
        approved = payload.decision == "approve"; row.status = "approved" if approved else "rejected"; row.decided_by_profile_id = profile.id; row.decision_note = payload.note; row.decided_at = _utcnow()
        if row.entity_type == "workshop_job":
            job = db.get(WorkshopJobCard, row.entity_id)
            if job and job.branch_id == branch_id:
                job.status = "in_progress" if approved else "cancelled"; maintenance = db.get(MaintenanceWorkOrder, job.maintenance_work_order_id) if job.maintenance_work_order_id else None
                if maintenance: maintenance.status = "in_progress" if approved else "closed"; maintenance.closed_at = None if approved else _utcnow()
        elif row.entity_type == "purchase_requisition":
            requisition = db.get(PurchaseRequisition, row.entity_id)
            if requisition and requisition.branch_id == branch_id: requisition.status = row.status
        _audit(db, profile.id, branch_id, f"approval.{row.status}", row.entity_type, row.entity_id, {"note": payload.note}); db.commit(); return {"status": row.status}


@router.get("/audit")
def list_audit(branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id); rows = list(db.scalars(select(AuditEvent).where(AuditEvent.branch_id == branch_id).order_by(AuditEvent.created_at.desc()).limit(500))); return [{"id": str(row.id), "actor_profile_id": str(row.actor_profile_id) if row.actor_profile_id else None, "action": row.action, "entity_type": row.entity_type, "entity_id": row.entity_id, "detail": json.loads(row.detail_json) if row.detail_json else None, "created_at": row.created_at.isoformat()} for row in rows]


@router.get("/executive")
def executive_command_centre(branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id); setting = _setting(db, branch_id); vehicles = list(db.scalars(select(Vehicle).where(Vehicle.branch_id == branch_id, Vehicle.is_active.is_(True)))); snapshots = [evaluate_vehicle(db, vehicle) for vehicle in vehicles]; tco_rows = _tco_rows(db, branch_id); current_year = _utcnow().year; replacement_candidates = []
        for vehicle in vehicles:
            age = current_year - vehicle.year if vehicle.year else None
            if (age is not None and age >= setting.vehicle_replacement_age_years) or vehicle.current_mileage >= setting.vehicle_replacement_mileage: replacement_candidates.append({"vehicle_id": str(vehicle.id), "registration_plate": vehicle.registration_plate, "age_years": age, "current_mileage": vehicle.current_mileage})
        drivers = list(db.scalars(select(Driver).where(Driver.branch_id == branch_id, Driver.is_active.is_(True))))
        return {"fleet": {"total": len(vehicles), "ready": sum(1 for x in snapshots if x["readiness"] == "green"), "attention": sum(1 for x in snapshots if x["readiness"] == "orange"), "blocked": sum(1 for x in snapshots if x["readiness"] == "red"), "available_now": sum(1 for x in snapshots if x["availability"]["label"] == "AVAILABLE NOW"), "replacement_candidates": replacement_candidates}, "drivers": {"active": len(drivers), "licences_expiring_or_expired_30d": sum(1 for driver in drivers if (driver.license_expiry - date.today()).days <= 30)}, "workshop": {"open_jobs": db.scalar(select(func.count()).select_from(WorkshopJobCard).where(WorkshopJobCard.branch_id == branch_id, WorkshopJobCard.status.notin_(["completed", "cancelled"]))) or 0}, "stores": {"low_stock": db.scalar(select(func.count()).select_from(InventoryItem).where(InventoryItem.branch_id == branch_id, InventoryItem.quantity_on_hand <= InventoryItem.reorder_level)) or 0}, "procurement": {"pending": db.scalar(select(func.count()).select_from(PurchaseRequisition).where(PurchaseRequisition.branch_id == branch_id, PurchaseRequisition.status.in_(["pending_approval", "approved", "ordered"]))) or 0}, "dispatch": {"pending": db.scalar(select(func.count()).select_from(DispatchRequest).where(DispatchRequest.branch_id == branch_id, DispatchRequest.status == "pending")) or 0, "active": db.scalar(select(func.count()).select_from(DispatchRequest).where(DispatchRequest.branch_id == branch_id, DispatchRequest.status == "active")) or 0}, "risk": {"open_claims": db.scalar(select(func.count()).select_from(InsuranceClaim).where(InsuranceClaim.branch_id == branch_id, InsuranceClaim.status.notin_(["paid", "closed", "rejected"]))) or 0, "pending_approvals": db.scalar(select(func.count()).select_from(ApprovalRequest).where(ApprovalRequest.branch_id == branch_id, ApprovalRequest.status == "pending")) or 0}, "finance": {"known_operating_cost": round(sum(row["known_cost"] for row in tco_rows), 2), "vehicles": tco_rows}}
