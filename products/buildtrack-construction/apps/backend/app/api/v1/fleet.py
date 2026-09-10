from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import (
    Branch,
    CompanySetting,
    CostCentre,
    Document,
    Employee,
    FleetAsset,
    FleetAssignment,
    FleetAuditEvent,
    FleetCompliance,
    FleetDefect,
    FleetFuelTransaction,
    FleetInspection,
    FleetMaintenanceJob,
    FleetMaintenancePlan,
    FleetMeterReading,
    NumberSequence,
    Permission,
    Role,
    RolePermission,
    Site,
)
from app.security.access import Principal, current_principal

router = APIRouter(prefix="/fleet", tags=["Phase 4 - Fleet & Plant"])
MONEY = Decimal("0.01")

PHASE4_PERMISSIONS: dict[str, tuple[str, str, str]] = {
    "fleet.view": ("fleet", "view", "View fleet and plant records"),
    "fleet.manage": ("fleet", "manage", "Create and maintain fleet and plant master records"),
    "fleet.assign": ("fleet", "assign", "Assign fleet and plant to branches, sites and operators"),
    "fleet.inspect": ("fleet", "inspect", "Capture inspections and defects"),
    "fleet.inspect.approve": ("fleet", "inspect_approve", "Approve fleet and plant inspections"),
    "fleet.fuel": ("fleet", "fuel", "Capture fuel transactions and meter evidence"),
    "fleet.maintenance": ("fleet", "maintenance", "Create maintenance plans and repair jobs"),
    "fleet.approve": ("fleet", "approve", "Approve controlled fleet maintenance actions"),
    "fleet.costs": ("fleet", "costs", "View fleet fuel, compliance and maintenance costs"),
    "fleet.export": ("fleet", "export", "Export fleet and plant registers and cost evidence"),
}

ROLE_PERMISSION_REQUIREMENTS: dict[str, set[str]] = {
    "SYSTEM_ADMIN": set(PHASE4_PERMISSIONS),
    "HQ_EXECUTIVE": {"fleet.view", "fleet.inspect.approve", "fleet.approve", "fleet.costs", "fleet.export"},
    "BRANCH_MANAGER": {"fleet.view", "fleet.assign", "fleet.inspect", "fleet.inspect.approve", "fleet.fuel", "fleet.maintenance", "fleet.costs"},
    "SITE_MANAGER": {"fleet.view", "fleet.assign", "fleet.inspect", "fleet.fuel", "fleet.maintenance"},
    "APPROVER": {"fleet.inspect.approve", "fleet.approve"},
    "AUDITOR": {"fleet.view", "fleet.costs", "fleet.export"},
    "FLEET_MANAGER": set(PHASE4_PERMISSIONS),
    "FLEET_OFFICER": {"fleet.view", "fleet.manage", "fleet.assign", "fleet.inspect", "fleet.fuel", "fleet.maintenance", "fleet.costs", "fleet.export"},
    "FLEET_INSPECTOR": {"fleet.view", "fleet.inspect"},
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def row_dict(row: Any) -> dict[str, Any]:
    return {column.name: json_value(getattr(row, column.name)) for column in row.__table__.columns}


def money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def commit(db: Session, detail: str = "The fleet record conflicts with existing data") -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=detail) from error


def require_company(principal: Principal, permission: str) -> None:
    if not principal.has_company_permission(permission):
        raise HTTPException(status_code=403, detail=f"Company-level permission required: {permission}")


def require_scope(principal: Principal, permission: str, branch_id: int | None, site_id: int | None = None) -> None:
    if not principal.can(permission, branch_id=branch_id, site_id=site_id):
        raise HTTPException(status_code=403, detail=f"Permission required in this branch/site: {permission}")


def ensure_scope(db: Session, principal: Principal, branch_id: int, site_id: int | None = None, cost_centre_id: int | None = None) -> None:
    branch = db.get(Branch, branch_id)
    if not branch or branch.company_id != principal.user.company_id:
        raise HTTPException(status_code=422, detail="Branch does not belong to the active company")
    if site_id is not None:
        site = db.get(Site, site_id)
        if not site or site.company_id != principal.user.company_id or site.branch_id != branch_id:
            raise HTTPException(status_code=422, detail="Site does not belong to the selected branch")
    if cost_centre_id is not None:
        centre = db.get(CostCentre, cost_centre_id)
        if not centre or centre.company_id != principal.user.company_id:
            raise HTTPException(status_code=422, detail="Cost centre does not belong to the active company")
        if centre.branch_id is not None and centre.branch_id != branch_id:
            raise HTTPException(status_code=422, detail="Cost centre is outside the selected branch")
        if site_id is not None and centre.site_id is not None and centre.site_id != site_id:
            raise HTTPException(status_code=422, detail="Cost centre is outside the selected site")


def asset_or_404(db: Session, principal: Principal, asset_id: int, permission: str = "fleet.view") -> FleetAsset:
    asset = db.get(FleetAsset, asset_id)
    if not asset or asset.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Fleet/plant asset not found")
    require_scope(principal, permission, asset.branch_id, asset.site_id)
    return asset


def employee_or_422(db: Session, principal: Principal, employee_id: int | None, branch_id: int, site_id: int | None = None) -> Employee | None:
    if employee_id is None:
        return None
    employee = db.get(Employee, employee_id)
    if not employee or employee.company_id != principal.user.company_id or employee.employment_status not in {"active", "on_leave"}:
        raise HTTPException(status_code=422, detail="Operator/driver is not an active employee of this company")
    if employee.branch_id != branch_id and site_id is not None and employee.site_id not in {None, site_id}:
        raise HTTPException(status_code=422, detail="Operator/driver is outside the assignment branch/site")
    return employee


def audit(db: Session, principal: Principal, action: str, entity_type: str, entity_id: str | int | None, *, asset_id: int | None = None, branch_id: int | None = None, detail: dict[str, Any] | None = None) -> None:
    db.add(FleetAuditEvent(
        company_id=principal.user.company_id,
        asset_id=asset_id,
        branch_id=branch_id,
        actor=principal.user.full_name,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        detail=detail or {},
    ))


def issue_reference(db: Session, company_id: int, code: str, fallback_prefix: str) -> str:
    sequence = db.scalar(select(NumberSequence).where(NumberSequence.company_id == company_id, NumberSequence.code == code))
    if not sequence:
        sequence = NumberSequence(company_id=company_id, code=code, name=code.replace("_", " ").title(), prefix=fallback_prefix, next_number=1, padding=5, reset_period="yearly")
        db.add(sequence); db.flush()
    now = utcnow()
    reset_key = str(now.year) if sequence.reset_period == "yearly" else (now.strftime("%Y-%m") if sequence.reset_period == "monthly" else "never")
    if sequence.reset_period != "never" and sequence.last_reset_key != reset_key:
        sequence.next_number = 1; sequence.last_reset_key = reset_key
    number = sequence.next_number; sequence.next_number += 1
    suffix = f"-{reset_key}" if sequence.reset_period == "yearly" else (f"-{reset_key.replace('-', '')}" if sequence.reset_period == "monthly" else "")
    return f"{sequence.prefix}{suffix}-{number:0{sequence.padding}d}"


def record_meter(db: Session, principal: Principal, asset: FleetAsset, *, odometer_km: Decimal | None = None, engine_hours: Decimal | None = None, source: str, source_id: str | int | None = None, notes: str | None = None) -> None:
    if odometer_km is None and engine_hours is None:
        return
    if odometer_km is not None:
        odometer_km = Decimal(str(odometer_km))
        if odometer_km < Decimal(asset.current_odometer_km or 0):
            raise HTTPException(status_code=422, detail="Odometer reading cannot move backwards")
        asset.current_odometer_km = odometer_km
    if engine_hours is not None:
        engine_hours = Decimal(str(engine_hours))
        if engine_hours < Decimal(asset.current_engine_hours or 0):
            raise HTTPException(status_code=422, detail="Engine-hour reading cannot move backwards")
        asset.current_engine_hours = engine_hours
    db.add(FleetMeterReading(company_id=asset.company_id, asset_id=asset.id, reading_at=utcnow(), odometer_km=odometer_km, engine_hours=engine_hours, source=source, source_id=str(source_id) if source_id is not None else None, notes=notes, recorded_by=principal.user.full_name))


def reconcile_permissions(db: Session, company_id: int) -> None:
    permissions = {p.code: p for p in db.scalars(select(Permission)).all()}
    for code, (module, action, description) in PHASE4_PERMISSIONS.items():
        if code not in permissions:
            permission = Permission(code=code, module=module, action=action, description=description)
            db.add(permission); db.flush(); permissions[code] = permission

    roles = {role.code: role for role in db.scalars(select(Role).where(Role.company_id == company_id)).all()}
    for code, name, scope in (("FLEET_MANAGER", "Fleet Manager", "company"), ("FLEET_OFFICER", "Fleet Officer", "branch"), ("FLEET_INSPECTOR", "Fleet Inspector", "site")):
        if code not in roles:
            role = Role(company_id=company_id, code=code, name=name, description=f"Phase 4 {name.lower()} role", scope_level=scope, is_system=True, is_active=True)
            db.add(role); db.flush(); roles[code] = role

    for role_code, required_codes in ROLE_PERMISSION_REQUIREMENTS.items():
        role = roles.get(role_code)
        if not role:
            continue
        existing = set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id == role.id)).all())
        for permission_code in required_codes:
            permission = permissions[permission_code]
            if permission.id not in existing:
                db.add(RolePermission(role_id=role.id, permission_id=permission.id)); existing.add(permission.id)

    for code, prefix, name in (("FLEET", "FLT", "Fleet asset numbers"), ("FLEET_DEFECT", "FDF", "Fleet defect numbers"), ("FLEET_JOB", "FMJ", "Fleet maintenance jobs")):
        if not db.scalar(select(NumberSequence).where(NumberSequence.company_id == company_id, NumberSequence.code == code)):
            db.add(NumberSequence(company_id=company_id, code=code, name=name, prefix=prefix, next_number=1, padding=5, reset_period="yearly"))

    if not db.scalar(select(CompanySetting).where(CompanySetting.company_id == company_id, CompanySetting.key == "fleet_policy")):
        db.add(CompanySetting(company_id=company_id, key="fleet_policy", value={"compliance_reminder_days": 30, "maintenance_due_warning_days": 14, "require_maintenance_approval": True, "critical_defect_blocks_operation": True}))


class AssetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch_id: int
    site_id: int | None = None
    cost_centre_id: int | None = None
    asset_number: str | None = Field(default=None, max_length=64)
    asset_type: Literal["vehicle", "truck", "bus", "light_plant", "heavy_plant", "generator", "trailer", "equipment", "other"]
    category: str | None = Field(default=None, max_length=80)
    registration_number: str | None = Field(default=None, max_length=80)
    make: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=120)
    manufacture_year: int | None = Field(default=None, ge=1900, le=2200)
    vin_serial_number: str | None = Field(default=None, max_length=160)
    engine_number: str | None = Field(default=None, max_length=120)
    fuel_type: str | None = Field(default=None, max_length=40)
    ownership_type: Literal["owned", "leased", "hired", "financed"] = "owned"
    supplier_owner: str | None = Field(default=None, max_length=200)
    acquisition_date: date | None = None
    acquisition_cost: Decimal | None = Field(default=None, ge=0)
    meter_type: Literal["odometer", "engine_hours", "both", "none"] = "odometer"
    current_odometer_km: Decimal = Field(default=0, ge=0)
    current_engine_hours: Decimal = Field(default=0, ge=0)
    status: Literal["active", "standby", "maintenance", "out_of_service", "disposed"] = "active"
    serviceability: Literal["serviceable", "restricted", "unserviceable"] = "serviceable"
    colour: str | None = Field(default=None, max_length=60)
    capacity_description: str | None = Field(default=None, max_length=160)
    notes: str | None = None


class AssetStatusInput(BaseModel):
    status: Literal["active", "standby", "maintenance", "out_of_service", "disposed"]
    serviceability: Literal["serviceable", "restricted", "unserviceable"] | None = None
    notes: str | None = None


class MeterInput(BaseModel):
    odometer_km: Decimal | None = Field(default=None, ge=0)
    engine_hours: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None


class AssignmentInput(BaseModel):
    employee_id: int | None = None
    branch_id: int
    site_id: int | None = None
    assigned_from: datetime | None = None
    purpose: str | None = None


class VehicleRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    driver_name: str = Field(min_length=2, max_length=200)
    licence_number: str = Field(min_length=2, max_length=80)
    licence_category: str = Field(min_length=1, max_length=40)
    requested_asset_type: Literal["vehicle", "truck", "bus", "light_plant", "heavy_plant", "generator", "trailer", "equipment", "other"]
    purpose: str = Field(min_length=2, max_length=500)
    destination: str = Field(min_length=2, max_length=200)
    required_from: datetime
    expected_return: datetime


class ComplianceInput(BaseModel):
    compliance_type: Literal["licence", "insurance", "roadworthy", "permit", "registration", "operator_certificate", "other"]
    reference_number: str | None = Field(default=None, max_length=120)
    provider: str | None = Field(default=None, max_length=200)
    issue_date: date | None = None
    expiry_date: date | None = None
    reminder_days: int = Field(default=30, ge=0, le=365)
    cost: Decimal = Field(default=0, ge=0)
    document_id: int | None = None
    notes: str | None = None


class DefectInput(BaseModel):
    severity: Literal["minor", "major", "critical"] = "minor"
    description: str = Field(min_length=2)


class InspectionInput(BaseModel):
    inspection_date: date
    inspection_type: Literal["pre_start", "daily", "weekly", "monthly", "handover", "post_repair", "other"] = "pre_start"
    inspector_employee_id: int | None = None
    odometer_km: Decimal | None = Field(default=None, ge=0)
    engine_hours: Decimal | None = Field(default=None, ge=0)
    checklist: dict[str, Any] = Field(default_factory=dict)
    safe_to_operate: bool = True
    notes: str | None = None
    defects: list[DefectInput] = Field(default_factory=list, max_length=50)


class InspectionDecisionInput(BaseModel):
    decision: Literal["approve", "reject"]
    comment: str | None = None


class DefectResolutionInput(BaseModel):
    status: Literal["in_progress", "resolved", "deferred"]
    resolution_notes: str | None = None


class FuelInput(BaseModel):
    transaction_date: datetime | None = None
    employee_id: int | None = None
    fuel_type: str = Field(min_length=1, max_length=40)
    litres: Decimal = Field(gt=0)
    unit_cost: Decimal = Field(gt=0)
    vendor: str | None = Field(default=None, max_length=200)
    receipt_reference: str | None = Field(default=None, max_length=120)
    odometer_km: Decimal | None = Field(default=None, ge=0)
    engine_hours: Decimal | None = Field(default=None, ge=0)
    full_tank: bool = False
    notes: str | None = None


class MaintenancePlanInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    interval_km: Decimal | None = Field(default=None, gt=0)
    interval_hours: Decimal | None = Field(default=None, gt=0)
    interval_days: int | None = Field(default=None, gt=0, le=3650)
    last_service_date: date | None = None
    last_odometer_km: Decimal | None = Field(default=None, ge=0)
    last_engine_hours: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None


class MaintenanceJobInput(BaseModel):
    plan_id: int | None = None
    defect_id: int | None = None
    maintenance_type: Literal["scheduled", "repair", "breakdown", "tyres", "bodywork", "electrical", "inspection", "other"] = "scheduled"
    description: str = Field(min_length=2)
    vendor: str | None = Field(default=None, max_length=200)
    labour_cost: Decimal = Field(default=0, ge=0)
    parts_cost: Decimal = Field(default=0, ge=0)
    other_cost: Decimal = Field(default=0, ge=0)
    invoice_reference: str | None = Field(default=None, max_length=120)
    notes: str | None = None


class MaintenanceStatusInput(BaseModel):
    status: Literal["approved", "in_progress", "completed", "cancelled"]
    odometer_km: Decimal | None = Field(default=None, ge=0)
    engine_hours: Decimal | None = Field(default=None, ge=0)
    labour_cost: Decimal | None = Field(default=None, ge=0)
    parts_cost: Decimal | None = Field(default=None, ge=0)
    other_cost: Decimal | None = Field(default=None, ge=0)
    invoice_reference: str | None = Field(default=None, max_length=120)
    notes: str | None = None


@router.post("/bootstrap")
def bootstrap_fleet(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if not principal.has_company_permission("company.manage") and not principal.has_company_permission("people.manage"):
        raise HTTPException(status_code=403, detail="Company administration permission is required to initialise Phase 4")
    reconcile_permissions(db, principal.user.company_id)
    audit(db, principal, "fleet.bootstrap", "phase", "4", detail={"status": "operational"})
    commit(db)
    return {"status": "operational", "phase": 4, "permissions": sorted(PHASE4_PERMISSIONS)}


@router.get("/status")
def fleet_status(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    initialized = bool(db.scalar(select(Permission.id).where(Permission.code == "fleet.manage")))
    return {"initialized": initialized, "status": "operational" if initialized else "not_initialized", "phase": 4}


@router.get("/catalog")
def fleet_catalog(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if not principal.can("fleet.view") and not principal.can("fleet.manage"):
        raise HTTPException(status_code=403, detail="fleet.view is required")
    company_id = principal.user.company_id
    branches = [row_dict(row) for row in db.scalars(select(Branch).where(Branch.company_id == company_id, Branch.is_active.is_(True)).order_by(Branch.name)).all() if principal.can("fleet.view", branch_id=row.id) or principal.can("fleet.manage", branch_id=row.id)]
    visible_branch_ids = {row["id"] for row in branches}
    sites = [row_dict(row) for row in db.scalars(select(Site).where(Site.company_id == company_id, Site.is_active.is_(True)).order_by(Site.name)).all() if row.branch_id in visible_branch_ids and (principal.can("fleet.view", branch_id=row.branch_id, site_id=row.id) or principal.can("fleet.manage", branch_id=row.branch_id, site_id=row.id))]
    employees = []
    for employee in db.scalars(select(Employee).where(Employee.company_id == company_id, Employee.employment_status.in_(["active", "on_leave"])).order_by(Employee.first_name, Employee.last_name)).all():
        if principal.can("fleet.view", branch_id=employee.branch_id, site_id=employee.site_id) or principal.can("fleet.assign", branch_id=employee.branch_id, site_id=employee.site_id):
            employees.append({"id": employee.id, "employee_number": employee.employee_number, "full_name": " ".join(filter(None, [employee.first_name, employee.middle_names, employee.last_name])), "branch_id": employee.branch_id, "site_id": employee.site_id, "job_title": employee.job_title})
    cost_centres = [row_dict(row) for row in db.scalars(select(CostCentre).where(CostCentre.company_id == company_id, CostCentre.is_active.is_(True)).order_by(CostCentre.code)).all() if row.branch_id is None or row.branch_id in visible_branch_ids]
    permissions = sorted(code for code in PHASE4_PERMISSIONS if principal.can(code))
    return {"branches": branches, "sites": sites, "cost_centres": cost_centres, "employees": employees, "permissions": permissions, "asset_types": ["vehicle", "truck", "bus", "light_plant", "heavy_plant", "generator", "trailer", "equipment", "other"]}


@router.get("/assets")
def list_assets(db: Session = Depends(get_db), principal: Principal = Depends(current_principal), status_filter: str | None = Query(default=None, alias="status")) -> list[dict[str, Any]]:
    rows = db.scalars(select(FleetAsset).where(FleetAsset.company_id == principal.user.company_id).order_by(FleetAsset.asset_number)).all()
    return [row_dict(row) for row in rows if (not status_filter or row.status == status_filter) and principal.can("fleet.view", branch_id=row.branch_id, site_id=row.site_id)]


@router.post("/assets", status_code=status.HTTP_201_CREATED)
def create_asset(payload: AssetInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_scope(principal, "fleet.manage", payload.branch_id, payload.site_id)
    ensure_scope(db, principal, payload.branch_id, payload.site_id, payload.cost_centre_id)
    values = payload.model_dump()
    values["asset_number"] = values.get("asset_number") or issue_reference(db, principal.user.company_id, "FLEET", "FLT")
    asset = FleetAsset(company_id=principal.user.company_id, created_by=principal.user.full_name, **values)
    db.add(asset); db.flush()
    if asset.current_odometer_km or asset.current_engine_hours:
        db.add(FleetMeterReading(company_id=asset.company_id, asset_id=asset.id, reading_at=utcnow(), odometer_km=asset.current_odometer_km or None, engine_hours=asset.current_engine_hours or None, source="opening", recorded_by=principal.user.full_name))
    audit(db, principal, "fleet.asset.created", "fleet_asset", asset.id, asset_id=asset.id, branch_id=asset.branch_id, detail={"asset_number": asset.asset_number, "asset_type": asset.asset_type})
    commit(db, "Asset number or registration already exists")
    db.refresh(asset); return row_dict(asset)


@router.get("/assets/{asset_id}")
def asset_detail(asset_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    asset = asset_or_404(db, principal, asset_id)
    result = row_dict(asset)
    result["assignments"] = [row_dict(r) for r in db.scalars(select(FleetAssignment).where(FleetAssignment.asset_id == asset.id).order_by(FleetAssignment.assigned_from.desc())).all()]
    result["compliance"] = [row_dict(r) for r in db.scalars(select(FleetCompliance).where(FleetCompliance.asset_id == asset.id).order_by(FleetCompliance.expiry_date)).all()]
    result["maintenance_plans"] = [row_dict(r) for r in db.scalars(select(FleetMaintenancePlan).where(FleetMaintenancePlan.asset_id == asset.id)).all()]
    result["open_defects"] = [row_dict(r) for r in db.scalars(select(FleetDefect).where(FleetDefect.asset_id == asset.id, FleetDefect.status != "resolved")).all()]
    return result


@router.post("/assets/{asset_id}/status")
def change_asset_status(asset_id: int, payload: AssetStatusInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    asset = asset_or_404(db, principal, asset_id, "fleet.manage")
    if payload.status == "active" and db.scalar(select(FleetDefect.id).where(FleetDefect.asset_id == asset.id, FleetDefect.severity == "critical", FleetDefect.status != "resolved")):
        raise HTTPException(status_code=422, detail="Critical defects must be resolved before returning the asset to active service")
    old = {"status": asset.status, "serviceability": asset.serviceability}
    asset.status = payload.status
    if payload.serviceability is not None: asset.serviceability = payload.serviceability
    if payload.status in {"out_of_service", "disposed"}: asset.serviceability = "unserviceable"
    audit(db, principal, "fleet.asset.status_changed", "fleet_asset", asset.id, asset_id=asset.id, branch_id=asset.branch_id, detail={"from": old, "to": {"status": asset.status, "serviceability": asset.serviceability}, "notes": payload.notes})
    commit(db); return row_dict(asset)


@router.post("/assets/{asset_id}/meters", status_code=status.HTTP_201_CREATED)
def add_meter(asset_id: int, payload: MeterInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    asset = asset_or_404(db, principal, asset_id, "fleet.manage")
    record_meter(db, principal, asset, odometer_km=payload.odometer_km, engine_hours=payload.engine_hours, source="manual", notes=payload.notes)
    audit(db, principal, "fleet.meter.recorded", "fleet_asset", asset.id, asset_id=asset.id, branch_id=asset.branch_id, detail=payload.model_dump(mode="json"))
    commit(db); return row_dict(asset)


@router.post("/assets/{asset_id}/assignments", status_code=status.HTTP_201_CREATED)
def create_assignment(asset_id: int, payload: AssignmentInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    asset = asset_or_404(db, principal, asset_id, "fleet.assign")
    require_scope(principal, "fleet.assign", payload.branch_id, payload.site_id)
    ensure_scope(db, principal, payload.branch_id, payload.site_id)
    employee_or_422(db, principal, payload.employee_id, payload.branch_id, payload.site_id)
    if db.scalar(select(FleetAssignment.id).where(FleetAssignment.asset_id == asset.id, FleetAssignment.status == "active")):
        raise HTTPException(status_code=409, detail="Asset already has an active assignment")
    readiness = readiness_for_asset(db, principal, asset)
    if readiness["decision"] != "allowed":
        reasons = "; ".join(readiness["blockers"] or readiness["warnings"])
        raise HTTPException(status_code=422, detail=f"Asset is not available for assignment: {reasons}")
    assignment = FleetAssignment(company_id=asset.company_id, asset_id=asset.id, employee_id=payload.employee_id, branch_id=payload.branch_id, site_id=payload.site_id, assigned_from=payload.assigned_from or utcnow(), purpose=payload.purpose, status="active", assigned_by=principal.user.full_name)
    db.add(assignment); db.flush()
    asset.branch_id = payload.branch_id; asset.site_id = payload.site_id
    audit(db, principal, "fleet.assignment.created", "fleet_assignment", assignment.id, asset_id=asset.id, branch_id=payload.branch_id, detail={"employee_id": payload.employee_id, "site_id": payload.site_id})
    commit(db); return row_dict(assignment)


@router.post("/assignments/{assignment_id}/complete")
def complete_assignment(assignment_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    assignment = db.get(FleetAssignment, assignment_id)
    if not assignment or assignment.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Assignment not found")
    require_scope(principal, "fleet.assign", assignment.branch_id, assignment.site_id)
    if assignment.status != "active": raise HTTPException(status_code=409, detail="Assignment is already closed")
    assignment.status = "completed"; assignment.assigned_to = utcnow(); assignment.completed_by = principal.user.full_name
    audit(db, principal, "fleet.assignment.completed", "fleet_assignment", assignment.id, asset_id=assignment.asset_id, branch_id=assignment.branch_id)
    commit(db); return row_dict(assignment)


@router.post("/assets/{asset_id}/compliance", status_code=status.HTTP_201_CREATED)
def add_compliance(asset_id: int, payload: ComplianceInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    asset = asset_or_404(db, principal, asset_id, "fleet.manage")
    if payload.expiry_date and payload.issue_date and payload.expiry_date < payload.issue_date: raise HTTPException(status_code=422, detail="Expiry date cannot be before issue date")
    if payload.document_id is not None:
        document = db.get(Document, payload.document_id)
        if not document or document.company_id != asset.company_id: raise HTTPException(status_code=422, detail="Document does not belong to the active company")
    row = FleetCompliance(company_id=asset.company_id, asset_id=asset.id, created_by=principal.user.full_name, **payload.model_dump())
    db.add(row); db.flush(); audit(db, principal, "fleet.compliance.created", "fleet_compliance", row.id, asset_id=asset.id, branch_id=asset.branch_id, detail={"type": row.compliance_type, "expiry_date": json_value(row.expiry_date)})
    commit(db); return row_dict(row)


@router.post("/assets/{asset_id}/inspections", status_code=status.HTTP_201_CREATED)
def create_inspection(asset_id: int, payload: InspectionInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    asset = asset_or_404(db, principal, asset_id, "fleet.inspect")
    employee_or_422(db, principal, payload.inspector_employee_id, asset.branch_id, asset.site_id)
    inspection = FleetInspection(company_id=asset.company_id, asset_id=asset.id, branch_id=asset.branch_id, site_id=asset.site_id, inspector_employee_id=payload.inspector_employee_id, inspection_date=payload.inspection_date, inspection_type=payload.inspection_type, odometer_km=payload.odometer_km, engine_hours=payload.engine_hours, checklist=payload.checklist, defects_found=bool(payload.defects), safe_to_operate=payload.safe_to_operate and not any(d.severity == "critical" for d in payload.defects), status="submitted", notes=payload.notes, inspected_by=principal.user.full_name)
    db.add(inspection); db.flush(); record_meter(db, principal, asset, odometer_km=payload.odometer_km, engine_hours=payload.engine_hours, source="inspection", source_id=inspection.id)
    defects = []
    for item in payload.defects:
        defect = FleetDefect(company_id=asset.company_id, asset_id=asset.id, inspection_id=inspection.id, defect_number=issue_reference(db, asset.company_id, "FLEET_DEFECT", "FDF"), severity=item.severity, description=item.description, status="open", reported_by=principal.user.full_name)
        db.add(defect); db.flush(); defects.append(row_dict(defect))
    if not inspection.safe_to_operate:
        asset.serviceability = "unserviceable"; asset.status = "out_of_service"
    audit(db, principal, "fleet.inspection.submitted", "fleet_inspection", inspection.id, asset_id=asset.id, branch_id=asset.branch_id, detail={"safe_to_operate": inspection.safe_to_operate, "defect_count": len(defects)})
    commit(db)
    result = row_dict(inspection); result["defects"] = defects; return result


@router.post("/inspections/{inspection_id}/decision")
def decide_inspection(inspection_id: int, payload: InspectionDecisionInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    inspection = db.get(FleetInspection, inspection_id)
    if not inspection or inspection.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Inspection not found")
    require_scope(principal, "fleet.inspect.approve", inspection.branch_id, inspection.site_id)
    if inspection.status != "submitted": raise HTTPException(status_code=409, detail="Only submitted inspections can be decided")
    if inspection.inspected_by == principal.user.full_name:
        setting = db.scalar(select(CompanySetting).where(CompanySetting.company_id == principal.user.company_id, CompanySetting.key == "approval_control"))
        allow_self = bool(setting.value.get("allow_self_approval")) if setting and isinstance(setting.value, dict) else False
        if not allow_self: raise HTTPException(status_code=422, detail="Self-approval is disabled by company approval policy")
    inspection.status = "approved" if payload.decision == "approve" else "rejected"; inspection.approved_by = principal.user.full_name; inspection.approved_at = utcnow()
    audit(db, principal, f"fleet.inspection.{inspection.status}", "fleet_inspection", inspection.id, asset_id=inspection.asset_id, branch_id=inspection.branch_id, detail={"comment": payload.comment})
    commit(db); return row_dict(inspection)


@router.get("/defects")
def list_defects(db: Session = Depends(get_db), principal: Principal = Depends(current_principal), open_only: bool = True) -> list[dict[str, Any]]:
    rows = db.scalars(select(FleetDefect).where(FleetDefect.company_id == principal.user.company_id).order_by(FleetDefect.reported_at.desc())).all()
    result = []
    for row in rows:
        asset = db.get(FleetAsset, row.asset_id)
        if asset and principal.can("fleet.view", branch_id=asset.branch_id, site_id=asset.site_id) and (not open_only or row.status != "resolved"): result.append(row_dict(row))
    return result


@router.post("/defects/{defect_id}/status")
def change_defect(defect_id: int, payload: DefectResolutionInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    defect = db.get(FleetDefect, defect_id)
    if not defect or defect.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Defect not found")
    asset = asset_or_404(db, principal, defect.asset_id, "fleet.maintenance")
    defect.status = payload.status; defect.resolution_notes = payload.resolution_notes
    if payload.status == "resolved": defect.resolved_at = utcnow(); defect.resolved_by = principal.user.full_name
    if payload.status == "resolved" and not db.scalar(select(FleetDefect.id).where(FleetDefect.asset_id == asset.id, FleetDefect.severity == "critical", FleetDefect.status != "resolved", FleetDefect.id != defect.id)):
        if asset.status == "out_of_service": asset.status = "standby"
        asset.serviceability = "serviceable"
    audit(db, principal, f"fleet.defect.{payload.status}", "fleet_defect", defect.id, asset_id=asset.id, branch_id=asset.branch_id, detail={"resolution_notes": payload.resolution_notes})
    commit(db); return row_dict(defect)


@router.post("/assets/{asset_id}/fuel", status_code=status.HTTP_201_CREATED)
def add_fuel(asset_id: int, payload: FuelInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    asset = asset_or_404(db, principal, asset_id, "fleet.fuel")
    employee_or_422(db, principal, payload.employee_id, asset.branch_id, asset.site_id)
    total = money(payload.litres * payload.unit_cost)
    row = FleetFuelTransaction(company_id=asset.company_id, asset_id=asset.id, branch_id=asset.branch_id, site_id=asset.site_id, employee_id=payload.employee_id, transaction_date=payload.transaction_date or utcnow(), fuel_type=payload.fuel_type, litres=payload.litres, unit_cost=payload.unit_cost, total_cost=total, vendor=payload.vendor, receipt_reference=payload.receipt_reference, odometer_km=payload.odometer_km, engine_hours=payload.engine_hours, full_tank=payload.full_tank, notes=payload.notes, recorded_by=principal.user.full_name)
    db.add(row); db.flush(); record_meter(db, principal, asset, odometer_km=payload.odometer_km, engine_hours=payload.engine_hours, source="fuel", source_id=row.id)
    audit(db, principal, "fleet.fuel.recorded", "fleet_fuel", row.id, asset_id=asset.id, branch_id=asset.branch_id, detail={"litres": str(row.litres), "total_cost": str(row.total_cost), "receipt_reference": row.receipt_reference})
    commit(db); return row_dict(row)


@router.get("/fuel")
def list_fuel(db: Session = Depends(get_db), principal: Principal = Depends(current_principal), asset_id: int | None = None) -> list[dict[str, Any]]:
    statement = select(FleetFuelTransaction).where(FleetFuelTransaction.company_id == principal.user.company_id)
    if asset_id is not None: statement = statement.where(FleetFuelTransaction.asset_id == asset_id)
    rows = db.scalars(statement.order_by(FleetFuelTransaction.transaction_date.desc()).limit(500)).all()
    return [row_dict(row) for row in rows if principal.can("fleet.view", branch_id=row.branch_id, site_id=row.site_id)]


@router.post("/assets/{asset_id}/maintenance-plans", status_code=status.HTTP_201_CREATED)
def create_plan(asset_id: int, payload: MaintenancePlanInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    asset = asset_or_404(db, principal, asset_id, "fleet.maintenance")
    if not any((payload.interval_km, payload.interval_hours, payload.interval_days)): raise HTTPException(status_code=422, detail="At least one maintenance interval is required")
    last_date = payload.last_service_date or date.today(); last_km = payload.last_odometer_km if payload.last_odometer_km is not None else asset.current_odometer_km; last_hours = payload.last_engine_hours if payload.last_engine_hours is not None else asset.current_engine_hours
    row = FleetMaintenancePlan(company_id=asset.company_id, asset_id=asset.id, name=payload.name, interval_km=payload.interval_km, interval_hours=payload.interval_hours, interval_days=payload.interval_days, last_service_date=last_date, last_odometer_km=last_km, last_engine_hours=last_hours, next_due_date=(last_date + timedelta(days=payload.interval_days)) if payload.interval_days else None, next_due_odometer_km=(Decimal(last_km or 0) + payload.interval_km) if payload.interval_km else None, next_due_engine_hours=(Decimal(last_hours or 0) + payload.interval_hours) if payload.interval_hours else None, is_active=True, notes=payload.notes, created_by=principal.user.full_name)
    db.add(row); db.flush(); audit(db, principal, "fleet.maintenance_plan.created", "fleet_maintenance_plan", row.id, asset_id=asset.id, branch_id=asset.branch_id, detail={"name": row.name})
    commit(db); return row_dict(row)


@router.post("/assets/{asset_id}/maintenance-jobs", status_code=status.HTTP_201_CREATED)
def create_job(asset_id: int, payload: MaintenanceJobInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    asset = asset_or_404(db, principal, asset_id, "fleet.maintenance")
    if payload.plan_id is not None:
        plan = db.get(FleetMaintenancePlan, payload.plan_id)
        if not plan or plan.asset_id != asset.id: raise HTTPException(status_code=422, detail="Maintenance plan does not belong to this asset")
    if payload.defect_id is not None:
        defect = db.get(FleetDefect, payload.defect_id)
        if not defect or defect.asset_id != asset.id: raise HTTPException(status_code=422, detail="Defect does not belong to this asset")
    total = money(payload.labour_cost + payload.parts_cost + payload.other_cost)
    row = FleetMaintenanceJob(company_id=asset.company_id, asset_id=asset.id, plan_id=payload.plan_id, defect_id=payload.defect_id, job_number=issue_reference(db, asset.company_id, "FLEET_JOB", "FMJ"), maintenance_type=payload.maintenance_type, description=payload.description, vendor=payload.vendor, status="draft", labour_cost=money(payload.labour_cost), parts_cost=money(payload.parts_cost), other_cost=money(payload.other_cost), total_cost=total, invoice_reference=payload.invoice_reference, notes=payload.notes, requested_by=principal.user.full_name)
    db.add(row); db.flush(); audit(db, principal, "fleet.maintenance_job.created", "fleet_maintenance_job", row.id, asset_id=asset.id, branch_id=asset.branch_id, detail={"job_number": row.job_number, "total_cost": str(total)})
    commit(db); return row_dict(row)


@router.get("/maintenance-jobs")
def list_jobs(db: Session = Depends(get_db), principal: Principal = Depends(current_principal), status_filter: str | None = Query(default=None, alias="status")) -> list[dict[str, Any]]:
    rows = db.scalars(select(FleetMaintenanceJob).where(FleetMaintenanceJob.company_id == principal.user.company_id).order_by(FleetMaintenanceJob.requested_at.desc())).all()
    result = []
    for row in rows:
        asset = db.get(FleetAsset, row.asset_id)
        if asset and principal.can("fleet.view", branch_id=asset.branch_id, site_id=asset.site_id) and (not status_filter or row.status == status_filter): result.append(row_dict(row))
    return result


@router.post("/maintenance-jobs/{job_id}/status")
def change_job_status(job_id: int, payload: MaintenanceStatusInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    job = db.get(FleetMaintenanceJob, job_id)
    if not job or job.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Maintenance job not found")
    asset = asset_or_404(db, principal, job.asset_id, "fleet.maintenance" if payload.status != "approved" else "fleet.approve")
    transitions = {"draft": {"approved", "cancelled"}, "approved": {"in_progress", "cancelled"}, "in_progress": {"completed", "cancelled"}, "completed": set(), "cancelled": set()}
    if payload.status not in transitions.get(job.status, set()): raise HTTPException(status_code=409, detail=f"Invalid maintenance transition: {job.status} -> {payload.status}")
    if payload.status == "approved":
        if job.requested_by == principal.user.full_name:
            setting = db.scalar(select(CompanySetting).where(CompanySetting.company_id == asset.company_id, CompanySetting.key == "approval_control"))
            allow_self = bool(setting.value.get("allow_self_approval")) if setting and isinstance(setting.value, dict) else False
            if not allow_self: raise HTTPException(status_code=422, detail="Self-approval is disabled by company approval policy")
        job.approved_by = principal.user.full_name; job.approved_at = utcnow()
    elif payload.status == "in_progress":
        job.started_at = utcnow(); job.downtime_started_at = job.downtime_started_at or utcnow(); asset.status = "maintenance"; asset.serviceability = "unserviceable"
    elif payload.status == "completed":
        job.completed_at = utcnow(); job.downtime_ended_at = utcnow(); record_meter(db, principal, asset, odometer_km=payload.odometer_km, engine_hours=payload.engine_hours, source="maintenance", source_id=job.id)
        if payload.labour_cost is not None: job.labour_cost = money(payload.labour_cost)
        if payload.parts_cost is not None: job.parts_cost = money(payload.parts_cost)
        if payload.other_cost is not None: job.other_cost = money(payload.other_cost)
        job.total_cost = money(job.labour_cost + job.parts_cost + job.other_cost)
        if payload.invoice_reference is not None: job.invoice_reference = payload.invoice_reference
        if job.plan_id:
            plan = db.get(FleetMaintenancePlan, job.plan_id)
            if plan:
                plan.last_service_date = date.today(); plan.last_odometer_km = asset.current_odometer_km; plan.last_engine_hours = asset.current_engine_hours
                plan.next_due_date = (date.today() + timedelta(days=plan.interval_days)) if plan.interval_days else None
                plan.next_due_odometer_km = (Decimal(asset.current_odometer_km or 0) + plan.interval_km) if plan.interval_km else None
                plan.next_due_engine_hours = (Decimal(asset.current_engine_hours or 0) + plan.interval_hours) if plan.interval_hours else None
        if job.defect_id:
            defect = db.get(FleetDefect, job.defect_id)
            if defect: defect.status = "resolved"; defect.resolved_at = utcnow(); defect.resolved_by = principal.user.full_name; defect.resolution_notes = f"Resolved by maintenance job {job.job_number}"
        db.flush()
        critical_open = db.scalar(select(FleetDefect.id).where(FleetDefect.asset_id == asset.id, FleetDefect.severity == "critical", FleetDefect.status != "resolved"))
        asset.status = "standby"; asset.serviceability = "restricted" if critical_open else "serviceable"
    job.status = payload.status
    if payload.notes: job.notes = payload.notes
    audit(db, principal, f"fleet.maintenance_job.{payload.status}", "fleet_maintenance_job", job.id, asset_id=asset.id, branch_id=asset.branch_id, detail={"job_number": job.job_number, "total_cost": str(job.total_cost)})
    commit(db); return row_dict(job)


def due_state(asset: FleetAsset, plan: FleetMaintenancePlan, warning_days: int) -> tuple[str, list[str]]:
    reasons: list[str] = []
    today = date.today()
    if plan.next_due_date and plan.next_due_date <= today: reasons.append("date overdue")
    elif plan.next_due_date and plan.next_due_date <= today + timedelta(days=warning_days): reasons.append("date due soon")
    if plan.next_due_odometer_km is not None and Decimal(asset.current_odometer_km or 0) >= Decimal(plan.next_due_odometer_km): reasons.append("odometer overdue")
    if plan.next_due_engine_hours is not None and Decimal(asset.current_engine_hours or 0) >= Decimal(plan.next_due_engine_hours): reasons.append("engine hours overdue")
    return ("overdue" if any("overdue" in item for item in reasons) else ("due_soon" if reasons else "ok"), reasons)


def readiness_for_asset(db: Session, principal: Principal, asset: FleetAsset) -> dict[str, Any]:
    """Deterministic operational decision used by the Fleet & Plant control board."""
    company_id = asset.company_id
    policy_row = db.scalar(select(CompanySetting).where(CompanySetting.company_id == company_id, CompanySetting.key == "fleet_policy"))
    policy = policy_row.value if policy_row and isinstance(policy_row.value, dict) else {}
    warning_days = int(policy.get("maintenance_due_warning_days", 14))
    today = date.today()
    blockers: list[str] = []
    warnings: list[str] = []
    evidence: list[dict[str, Any]] = []

    if asset.status in {"maintenance", "out_of_service", "disposed"}:
        blockers.append(f"lifecycle status is {asset.status.replace("_", " ")}")
    if asset.serviceability == "unserviceable":
        blockers.append("mechanical condition is unserviceable")
    elif asset.serviceability == "restricted":
        warnings.append("mechanical condition is restricted")

    if db.scalar(select(FleetAssignment.id).where(FleetAssignment.asset_id == asset.id, FleetAssignment.status == "active")):
        blockers.append("asset has an active assignment")

    open_defects = db.scalars(select(FleetDefect).where(FleetDefect.asset_id == asset.id, FleetDefect.status != "resolved")).all()
    for defect in open_defects:
        message = f"{defect.severity} defect {defect.defect_number}: {defect.description}"
        if defect.severity == "critical":
            blockers.append(message)
        elif defect.severity == "major":
            warnings.append(message)

    required_by_type = {
        "vehicle": ["registration", "insurance", "roadworthy"],
        "truck": ["registration", "insurance", "roadworthy"],
        "bus": ["registration", "insurance", "roadworthy"],
        "trailer": ["registration", "insurance"],
        "light_plant": ["operator_certificate"],
        "heavy_plant": ["operator_certificate"],
        "generator": ["operator_certificate"],
    }
    required = required_by_type.get(asset.asset_type, [])
    records = db.scalars(select(FleetCompliance).where(FleetCompliance.asset_id == asset.id)).all()
    for compliance_type in required:
        rows = [row for row in records if row.compliance_type == compliance_type]
        if not rows:
            evidence.append({"type": compliance_type, "status": "missing"})
            blockers.append(f"required {compliance_type.replace("_", " ")} record is missing")
            continue
        row = max(rows, key=lambda item: item.expiry_date or date.max)
        if not row.expiry_date:
            evidence.append({"type": compliance_type, "status": "missing", "reference_number": row.reference_number})
            blockers.append(f"{compliance_type.replace("_", " ")} has no expiry date")
            continue
        days = (row.expiry_date - today).days
        state = "valid" if days > warning_days else ("soon" if days > 7 else ("critical" if days >= 0 else "expired"))
        evidence.append({"type": compliance_type, "status": state, "expiry_date": row.expiry_date.isoformat(), "reference_number": row.reference_number})
        if state in {"expired", "critical"}:
            blockers.append(f"{compliance_type.replace("_", " ")} is {state}")
        elif state == "soon":
            warnings.append(f"{compliance_type.replace("_", " ")} expires soon")

    latest_inspection = db.scalar(select(FleetInspection).where(FleetInspection.asset_id == asset.id).order_by(FleetInspection.inspection_date.desc(), FleetInspection.created_at.desc()))
    if not latest_inspection:
        blockers.append("no current inspection has been captured")
        inspection_status = "missing"
    elif latest_inspection.status != "approved" or not latest_inspection.safe_to_operate:
        blockers.append("latest inspection is not approved safe-to-operate")
        inspection_status = latest_inspection.status
    else:
        inspection_status = "approved"

    plans = db.scalars(select(FleetMaintenancePlan).where(FleetMaintenancePlan.asset_id == asset.id, FleetMaintenancePlan.is_active.is_(True))).all()
    maintenance: list[dict[str, Any]] = []
    for plan in plans:
        state, reasons = due_state(asset, plan, warning_days)
        maintenance.append({"plan_id": plan.id, "name": plan.name, "status": state, "reasons": reasons})
        if state == "overdue":
            blockers.append(f"maintenance overdue: {plan.name} ({'; '.join(reasons)})")
        elif state == "due_soon":
            warnings.append(f"maintenance due soon: {plan.name}")

    decision = "blocked" if blockers else ("restricted" if warnings else "allowed")
    return {
        "asset_id": asset.id,
        "asset_number": asset.asset_number,
        "asset": f"{asset.make} {asset.model}",
        "decision": decision,
        "blockers": blockers,
        "warnings": warnings,
        "document_status": evidence,
        "inspection_status": inspection_status,
        "maintenance": maintenance,
        "checked_at": utcnow().isoformat(),
    }


@router.get("/assets/{asset_id}/operational-readiness")
def operational_readiness(asset_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    asset = asset_or_404(db, principal, asset_id)
    return readiness_for_asset(db, principal, asset)


@router.get("/control-board")
def control_board(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    assets = db.scalars(select(FleetAsset).where(FleetAsset.company_id == principal.user.company_id).order_by(FleetAsset.asset_number)).all()
    return [readiness_for_asset(db, principal, asset) for asset in assets if principal.can("fleet.view", branch_id=asset.branch_id, site_id=asset.site_id)]


@router.post("/vehicle-requests/match")
def match_vehicle_request(payload: VehicleRequestInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if not principal.can("fleet.assign"):
        raise HTTPException(status_code=403, detail="fleet.assign is required")
    if payload.expected_return <= payload.required_from:
        raise HTTPException(status_code=422, detail="Expected return must be after the requested start time")
    candidates = db.scalars(select(FleetAsset).where(FleetAsset.company_id == principal.user.company_id, FleetAsset.asset_type == payload.requested_asset_type).order_by(FleetAsset.asset_number)).all()
    primary: list[dict[str, Any]] = []
    alternatives: list[dict[str, Any]] = []
    for asset in candidates:
        if not principal.can("fleet.view", branch_id=asset.branch_id, site_id=asset.site_id):
            continue
        readiness = readiness_for_asset(db, principal, asset)
        if readiness["decision"] == "allowed":
            primary.append(readiness)
        else:
            alternatives.append(readiness)
    request_detail = payload.model_dump(mode="json")
    audit(db, principal, "fleet.vehicle_request.matched", "fleet_vehicle_request", None, detail={**request_detail, "primary_match_count": len(primary), "alternative_count": len(alternatives)})
    commit(db)
    return {
        "request": request_detail,
        "decision": "match_found" if primary else "no_current_match",
        "primary_matches": primary,
        "alternatives": alternatives,
        "message": "Available assets are safe and compliant now." if primary else "No currently assignable asset matches. Review the alternative reasons or adjust the timing/type.",
    }


@router.get("/alerts")
def alerts(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    company_id = principal.user.company_id
    policy = db.scalar(select(CompanySetting).where(CompanySetting.company_id == company_id, CompanySetting.key == "fleet_policy"))
    warning_days = int(policy.value.get("maintenance_due_warning_days", 14)) if policy and isinstance(policy.value, dict) else 14
    result: list[dict[str, Any]] = []
    assets = {a.id: a for a in db.scalars(select(FleetAsset).where(FleetAsset.company_id == company_id)).all() if principal.can("fleet.view", branch_id=a.branch_id, site_id=a.site_id)}
    today = date.today()
    for item in db.scalars(select(FleetCompliance).where(FleetCompliance.company_id == company_id, FleetCompliance.expiry_date.is_not(None))).all():
        asset = assets.get(item.asset_id)
        if not asset or not item.expiry_date: continue
        days = (item.expiry_date - today).days
        if days <= item.reminder_days:
            result.append({"type": "compliance", "severity": "critical" if days < 0 else "warning", "asset_id": asset.id, "asset_number": asset.asset_number, "message": f"{item.compliance_type} {'expired' if days < 0 else 'expires'} on {item.expiry_date.isoformat()}", "due_date": item.expiry_date.isoformat()})
    for plan in db.scalars(select(FleetMaintenancePlan).where(FleetMaintenancePlan.company_id == company_id, FleetMaintenancePlan.is_active.is_(True))).all():
        asset = assets.get(plan.asset_id)
        if not asset: continue
        state, reasons = due_state(asset, plan, warning_days)
        if state != "ok": result.append({"type": "maintenance", "severity": "critical" if state == "overdue" else "warning", "asset_id": asset.id, "asset_number": asset.asset_number, "message": f"{plan.name}: {', '.join(reasons)}", "due_date": json_value(plan.next_due_date)})
    for defect in db.scalars(select(FleetDefect).where(FleetDefect.company_id == company_id, FleetDefect.status != "resolved")).all():
        asset = assets.get(defect.asset_id)
        if asset and defect.severity in {"major", "critical"}: result.append({"type": "defect", "severity": "critical" if defect.severity == "critical" else "warning", "asset_id": asset.id, "asset_number": asset.asset_number, "message": f"{defect.defect_number}: {defect.description}", "defect_id": defect.id})
    return sorted(result, key=lambda item: (item["severity"] != "critical", item["type"], item["asset_number"]))


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    assets = [a for a in db.scalars(select(FleetAsset).where(FleetAsset.company_id == principal.user.company_id)).all() if principal.can("fleet.view", branch_id=a.branch_id, site_id=a.site_id)]
    asset_ids = {a.id for a in assets}
    fuel_rows = db.scalars(select(FleetFuelTransaction).where(FleetFuelTransaction.company_id == principal.user.company_id)).all()
    jobs = db.scalars(select(FleetMaintenanceJob).where(FleetMaintenanceJob.company_id == principal.user.company_id)).all()
    defects = db.scalars(select(FleetDefect).where(FleetDefect.company_id == principal.user.company_id, FleetDefect.status != "resolved")).all()
    total_fuel = sum((Decimal(r.total_cost or 0) for r in fuel_rows if r.asset_id in asset_ids), Decimal("0"))
    total_maintenance = sum((Decimal(r.total_cost or 0) for r in jobs if r.asset_id in asset_ids and r.status == "completed"), Decimal("0"))
    active_assignments = db.scalars(select(FleetAssignment).where(FleetAssignment.company_id == principal.user.company_id, FleetAssignment.status == "active")).all()
    return {"assets_total": len(assets), "active": sum(a.status == "active" for a in assets), "standby": sum(a.status == "standby" for a in assets), "maintenance": sum(a.status == "maintenance" for a in assets), "out_of_service": sum(a.status == "out_of_service" for a in assets), "unserviceable": sum(a.serviceability == "unserviceable" for a in assets), "active_assignments": sum(a.asset_id in asset_ids for a in active_assignments), "open_defects": sum(d.asset_id in asset_ids for d in defects), "critical_defects": sum(d.asset_id in asset_ids and d.severity == "critical" for d in defects), "fuel_cost": str(money(total_fuel)), "maintenance_cost": str(money(total_maintenance)), "alerts": len(alerts(db, principal))}


@router.get("/costs")
def costs(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    if not principal.can("fleet.costs"): raise HTTPException(status_code=403, detail="fleet.costs is required")
    result = []
    assets = db.scalars(select(FleetAsset).where(FleetAsset.company_id == principal.user.company_id)).all()
    for asset in assets:
        if not principal.can("fleet.costs", branch_id=asset.branch_id, site_id=asset.site_id): continue
        fuel = db.scalar(select(func.coalesce(func.sum(FleetFuelTransaction.total_cost), 0)).where(FleetFuelTransaction.asset_id == asset.id)) or 0
        maintenance = db.scalar(select(func.coalesce(func.sum(FleetMaintenanceJob.total_cost), 0)).where(FleetMaintenanceJob.asset_id == asset.id, FleetMaintenanceJob.status == "completed")) or 0
        compliance = db.scalar(select(func.coalesce(func.sum(FleetCompliance.cost), 0)).where(FleetCompliance.asset_id == asset.id)) or 0
        result.append({"asset_id": asset.id, "asset_number": asset.asset_number, "registration_number": asset.registration_number, "branch_id": asset.branch_id, "fuel_cost": str(money(fuel)), "maintenance_cost": str(money(maintenance)), "compliance_cost": str(money(compliance)), "total_cost": str(money(Decimal(fuel) + Decimal(maintenance) + Decimal(compliance)))})
    return result


@router.get("/export.csv")
def export_fleet(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> StreamingResponse:
    if not principal.can("fleet.export"): raise HTTPException(status_code=403, detail="fleet.export is required")
    output = io.StringIO(); writer = csv.writer(output)
    writer.writerow(["Asset Number", "Type", "Registration", "Make", "Model", "Branch ID", "Site ID", "Status", "Serviceability", "Odometer km", "Engine hours", "Fuel cost", "Maintenance cost", "Compliance cost", "Total cost"])
    cost_map = {row["asset_id"]: row for row in costs(db, principal)}
    for asset in db.scalars(select(FleetAsset).where(FleetAsset.company_id == principal.user.company_id).order_by(FleetAsset.asset_number)).all():
        if not principal.can("fleet.export", branch_id=asset.branch_id, site_id=asset.site_id): continue
        c = cost_map.get(asset.id, {})
        writer.writerow([asset.asset_number, asset.asset_type, asset.registration_number or "", asset.make, asset.model, asset.branch_id, asset.site_id or "", asset.status, asset.serviceability, asset.current_odometer_km, asset.current_engine_hours, c.get("fuel_cost", "0.00"), c.get("maintenance_cost", "0.00"), c.get("compliance_cost", "0.00"), c.get("total_cost", "0.00")])
    data = output.getvalue().encode("utf-8-sig")
    return StreamingResponse(io.BytesIO(data), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=buildtrack-fleet-register.csv"})


@router.get("/audit")
def fleet_audit(db: Session = Depends(get_db), principal: Principal = Depends(current_principal), limit: int = Query(default=200, ge=1, le=1000)) -> list[dict[str, Any]]:
    rows = db.scalars(select(FleetAuditEvent).where(FleetAuditEvent.company_id == principal.user.company_id).order_by(FleetAuditEvent.occurred_at.desc()).limit(limit)).all()
    return [row_dict(row) for row in rows if row.branch_id is None or principal.can("fleet.view", branch_id=row.branch_id)]
