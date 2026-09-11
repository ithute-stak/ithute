from __future__ import annotations

import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import current_claims
from .config import settings
from .db import SessionLocal
from .fleet_engine import evaluate_vehicle, match_vehicles
from .models import (
    AccidentRecord,
    Assignment,
    Branch,
    BranchModule,
    DocumentRequirement,
    Driver,
    FleetSetting,
    FuelRecord,
    Inspection,
    MaintenanceWorkOrder,
    MechanicalFault,
    Profile,
    ProfileBranchAccess,
    Reservation,
    ServiceKitRule,
    ServiceRecord,
    Trip,
    Vehicle,
    VehicleTypeLicenseRule,
    VehicleDocument,
)
from .schemas import (
    AccidentRecordCreate,
    AssignmentCreate,
    BranchCreate,
    BranchOut,
    DocumentRequirementCreate,
    DriverCreate,
    FleetSettingUpdate,
    FuelRecordCreate,
    InspectionCreate,
    MaintenanceWorkOrderCreate,
    MechanicalFaultCreate,
    ReservationCreate,
    ServiceKitRuleCreate,
    ServiceRecordCreate,
    TripCreate,
    VehicleCreate,
    VehicleTypeLicenseRuleCreate,
    VehicleDocumentCreate,
    VehicleMatchRequest,
)

router = APIRouter(prefix="/api/v1/fleet", tags=["fleet"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _profile(db: Session, claims: dict[str, Any]) -> Profile:
    auth_user_id = uuid.UUID(str(claims["sub"]))
    profile = db.scalar(select(Profile).where(Profile.auth_user_id == auth_user_id))
    if profile is not None:
        return profile
    token_email = str(claims.get("email") or "").strip().lower()
    if token_email and token_email == settings.bootstrap_admin_email.strip().lower():
        profile = Profile(auth_user_id=auth_user_id, email_snapshot=token_email, role="admin")
        db.add(profile)
        db.commit()
        db.refresh(profile)
        return profile
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="NBros account is not provisioned")


def _require_admin(profile: Profile) -> None:
    if profile.role not in {"admin", "fleet_admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="administrator access required")


def _require_branch(db: Session, profile: Profile, branch_id: uuid.UUID, *, write: bool = False) -> Branch:
    branch = db.get(Branch, branch_id)
    if branch is None or not branch.is_active:
        raise HTTPException(status_code=404, detail="branch not found")
    module = db.scalar(
        select(BranchModule).where(
            BranchModule.branch_id == branch_id,
            BranchModule.module_key == "fleet",
            BranchModule.is_enabled.is_(True),
        )
    )
    if module is None:
        raise HTTPException(status_code=403, detail="fleet module is not enabled for this branch")
    if profile.role in {"admin", "fleet_admin"}:
        return branch
    membership = db.scalar(
        select(ProfileBranchAccess).where(
            ProfileBranchAccess.profile_id == profile.id,
            ProfileBranchAccess.branch_id == branch_id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="no access to this branch")
    if write and membership.role not in {"manager", "fleet_manager"}:
        raise HTTPException(status_code=403, detail="branch write access required")
    return branch


def _vehicle(db: Session, branch_id: uuid.UUID, vehicle_id: uuid.UUID) -> Vehicle:
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None or vehicle.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="vehicle not found in branch")
    return vehicle


def _driver(db: Session, branch_id: uuid.UUID, driver_id: uuid.UUID) -> Driver:
    driver = db.get(Driver, driver_id)
    if driver is None or driver.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="driver not found in branch")
    return driver


def _serialize_vehicle(vehicle: Vehicle) -> dict[str, Any]:
    return {
        "id": str(vehicle.id),
        "branch_id": str(vehicle.branch_id),
        "registration_plate": vehicle.registration_plate,
        "make": vehicle.make,
        "model": vehicle.model,
        "vehicle_type": vehicle.vehicle_type,
        "year": vehicle.year,
        "vin": vehicle.vin,
        "engine_number": vehicle.engine_number,
        "fuel_type": vehicle.fuel_type,
        "current_mileage": vehicle.current_mileage,
        "mechanical_condition": vehicle.mechanical_condition,
        "is_active": vehicle.is_active,
    }


@router.get("/branches", response_model=list[BranchOut])
def list_branches(claims: dict = Depends(current_claims)) -> list[Branch]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        if profile.role in {"admin", "fleet_admin"}:
            return list(db.scalars(select(Branch).join(BranchModule).where(BranchModule.module_key == "fleet").order_by(Branch.name)))
        branch_ids = select(ProfileBranchAccess.branch_id).where(ProfileBranchAccess.profile_id == profile.id)
        return list(
            db.scalars(
                select(Branch)
                .join(BranchModule)
                .where(Branch.id.in_(branch_ids), BranchModule.module_key == "fleet", BranchModule.is_enabled.is_(True))
                .order_by(Branch.name)
            )
        )


@router.post("/branches", response_model=BranchOut, status_code=201)
def create_branch(payload: BranchCreate, claims: dict = Depends(current_claims)) -> Branch:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_admin(profile)
        branch = Branch(code=payload.code.strip().upper(), name=payload.name.strip(), location=payload.location)
        db.add(branch)
        try:
            db.flush()
            db.add(BranchModule(branch_id=branch.id, module_key="fleet", is_enabled=True))
            db.add(FleetSetting(branch_id=branch.id))
            for document_type in (
                "VAT 11 / purchase documentation",
                "Vehicle certificate",
                "Disc",
                "Number plate record",
                "Insurance",
                "Operating permit",
                "Roadworthiness / inspection",
            ):
                db.add(DocumentRequirement(branch_id=branch.id, document_type=document_type, is_required=True))
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="branch code already exists") from None
        db.refresh(branch)
        return branch


@router.put("/branches/{branch_id}/settings")
def update_settings(branch_id: uuid.UUID, payload: FleetSettingUpdate, claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id, write=True)
        row = db.get(FleetSetting, branch_id) or FleetSetting(branch_id=branch_id)
        for key, value in payload.model_dump().items():
            setattr(row, key, value)
        db.add(row)
        db.commit()
        return payload.model_dump()


@router.post("/license-rules", status_code=201)
def create_license_rule(payload: VehicleTypeLicenseRuleCreate, claims: dict = Depends(current_claims)) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, payload.branch_id, write=True)
        row = VehicleTypeLicenseRule(**payload.model_dump())
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="licence rule already exists") from None
        return {"id": str(row.id)}


@router.post("/service-kit-rules", status_code=201)
def create_service_kit_rule(payload: ServiceKitRuleCreate, claims: dict = Depends(current_claims)) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, payload.branch_id, write=True)
        row = ServiceKitRule(**payload.model_dump())
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="service-kit rule already exists") from None
        return {"id": str(row.id)}


@router.post("/document-requirements", status_code=201)
def create_document_requirement(payload: DocumentRequirementCreate, claims: dict = Depends(current_claims)) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, payload.branch_id, write=True)
        row = DocumentRequirement(**payload.model_dump())
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="document requirement already exists") from None
        return {"id": str(row.id)}


@router.get("/vehicles")
def list_vehicles(branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id)
        rows = list(db.scalars(select(Vehicle).where(Vehicle.branch_id == branch_id).order_by(Vehicle.registration_plate)))
        return [{**_serialize_vehicle(row), "decision": evaluate_vehicle(db, row)} for row in rows]


@router.post("/vehicles", status_code=201)
def create_vehicle(payload: VehicleCreate, claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, payload.branch_id, write=True)
        row = Vehicle(**payload.model_dump())
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="registration plate or VIN already exists") from None
        db.refresh(row)
        return _serialize_vehicle(row)


@router.get("/vehicles/{vehicle_id}")
def vehicle_profile(vehicle_id: uuid.UUID, branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id)
        vehicle = _vehicle(db, branch_id, vehicle_id)
        history = {
            "documents": [
                {"id": str(x.id), "type": x.document_type, "number": x.document_number, "issue_date": x.issue_date, "expiry_date": x.expiry_date, "file_url": x.file_url}
                for x in db.scalars(select(VehicleDocument).where(VehicleDocument.vehicle_id == vehicle_id).order_by(VehicleDocument.created_at.desc()))
            ],
            "services": [
                {"id": str(x.id), "date": x.service_date, "mileage": x.mileage, "type": x.service_type, "cost": str(x.cost) if x.cost is not None else None, "next_date": x.next_service_date, "next_mileage": x.next_service_mileage, "service_kit": x.service_kit}
                for x in db.scalars(select(ServiceRecord).where(ServiceRecord.vehicle_id == vehicle_id).order_by(ServiceRecord.service_date.desc()))
            ],
            "faults": [
                {"id": str(x.id), "severity": x.severity, "description": x.description, "reported_at": x.reported_at, "resolved_at": x.resolved_at}
                for x in db.scalars(select(MechanicalFault).where(MechanicalFault.vehicle_id == vehicle_id).order_by(MechanicalFault.reported_at.desc()))
            ],
            "inspections": [
                {"id": str(x.id), "date": x.inspection_date, "status": x.status, "inspector": x.inspector, "next_date": x.next_inspection_date}
                for x in db.scalars(select(Inspection).where(Inspection.vehicle_id == vehicle_id).order_by(Inspection.inspection_date.desc()))
            ],
            "fuel": [
                {"id": str(x.id), "recorded_at": x.recorded_at, "mileage": x.mileage, "litres": str(x.litres), "cost": str(x.cost) if x.cost is not None else None}
                for x in db.scalars(select(FuelRecord).where(FuelRecord.vehicle_id == vehicle_id).order_by(FuelRecord.recorded_at.desc()))
            ],
            "accidents": [
                {"id": str(x.id), "occurred_at": x.occurred_at, "location": x.location, "description": x.description, "reference_number": x.reference_number}
                for x in db.scalars(select(AccidentRecord).where(AccidentRecord.vehicle_id == vehicle_id).order_by(AccidentRecord.occurred_at.desc()))
            ],
            "assignments": [
                {"id": str(x.id), "driver_id": str(x.driver_id), "purpose": x.purpose, "start_at": x.start_at, "end_at": x.end_at, "status": x.status}
                for x in db.scalars(select(Assignment).where(Assignment.vehicle_id == vehicle_id).order_by(Assignment.start_at.desc()))
            ],
            "trips": [
                {"id": str(x.id), "driver_id": str(x.driver_id), "destination": x.destination, "start_at": x.start_at, "expected_return_at": x.expected_return_at, "actual_return_at": x.actual_return_at, "status": x.status}
                for x in db.scalars(select(Trip).where(Trip.vehicle_id == vehicle_id).order_by(Trip.start_at.desc()))
            ],
        }
        return {"vehicle": _serialize_vehicle(vehicle), "decision": evaluate_vehicle(db, vehicle), "history": history}


@router.get("/vehicles/{vehicle_id}/decision")
def vehicle_decision(vehicle_id: uuid.UUID, branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id)
        return evaluate_vehicle(db, _vehicle(db, branch_id, vehicle_id))


_ALLOWED_UPLOAD_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}


@router.post("/files", status_code=201)
async def upload_file(
    branch_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
    claims: dict = Depends(current_claims),
) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id, write=True)

    if file.content_type not in _ALLOWED_UPLOAD_TYPES:
        raise HTTPException(status_code=415, detail="only PDF and standard image files are accepted")
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="file exceeds the configured upload limit")

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".bin"
    filename = f"{uuid.uuid4().hex}{suffix}"
    directory = Path(settings.upload_dir) / str(branch_id)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_bytes(content)
    return {"file_url": f"/api/fleet/files/{branch_id}/{filename}"}


@router.get("/files/{branch_id}/{filename}", response_class=FileResponse)
def read_file(branch_id: uuid.UUID, filename: str, claims: dict = Depends(current_claims)):
    if Path(filename).name != filename:
        raise HTTPException(status_code=400, detail="invalid filename")
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id)
    path = Path(settings.upload_dir) / str(branch_id) / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(path)


@router.post("/documents", status_code=201)
def add_document(payload: VehicleDocumentCreate, claims: dict = Depends(current_claims)) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, payload.branch_id, write=True)
        _vehicle(db, payload.branch_id, payload.vehicle_id)
        row = VehicleDocument(**payload.model_dump())
        db.add(row)
        db.commit()
        return {"id": str(row.id)}


@router.post("/services", status_code=201)
def add_service(payload: ServiceRecordCreate, claims: dict = Depends(current_claims)) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, payload.branch_id, write=True)
        vehicle = _vehicle(db, payload.branch_id, payload.vehicle_id)
        row = ServiceRecord(**payload.model_dump())
        db.add(row)
        if payload.mileage > vehicle.current_mileage:
            vehicle.current_mileage = payload.mileage
        db.commit()
        return {"id": str(row.id)}


@router.post("/faults", status_code=201)
def add_fault(payload: MechanicalFaultCreate, claims: dict = Depends(current_claims)) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, payload.branch_id, write=True)
        vehicle = _vehicle(db, payload.branch_id, payload.vehicle_id)
        row = MechanicalFault(**payload.model_dump())
        db.add(row)
        vehicle.mechanical_condition = "out_of_service" if payload.severity == "critical" else "attention"
        db.commit()
        return {"id": str(row.id)}


@router.post("/faults/{fault_id}/resolve")
def resolve_fault(fault_id: uuid.UUID, claims: dict = Depends(current_claims)) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        fault = db.get(MechanicalFault, fault_id)
        if fault is None:
            raise HTTPException(status_code=404, detail="fault not found")
        _require_branch(db, profile, fault.branch_id, write=True)
        fault.resolved_at = _utcnow()
        remaining = db.scalar(
            select(func.count()).select_from(MechanicalFault).where(
                MechanicalFault.vehicle_id == fault.vehicle_id,
                MechanicalFault.resolved_at.is_(None),
                MechanicalFault.id != fault.id,
            )
        )
        if not remaining:
            vehicle = db.get(Vehicle, fault.vehicle_id)
            if vehicle:
                vehicle.mechanical_condition = "operational"
        db.commit()
        return {"status": "resolved"}


@router.post("/inspections", status_code=201)
def add_inspection(payload: InspectionCreate, claims: dict = Depends(current_claims)) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, payload.branch_id, write=True)
        _vehicle(db, payload.branch_id, payload.vehicle_id)
        row = Inspection(**payload.model_dump())
        db.add(row)
        db.commit()
        return {"id": str(row.id)}


@router.get("/drivers")
def list_drivers(branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id)
        rows = db.scalars(select(Driver).where(Driver.branch_id == branch_id).order_by(Driver.full_name))
        return [
            {"id": str(x.id), "full_name": x.full_name, "employee_number": x.employee_number, "license_number": x.license_number, "license_category": x.license_category, "license_expiry": x.license_expiry, "is_active": x.is_active}
            for x in rows
        ]


@router.post("/drivers", status_code=201)
def add_driver(payload: DriverCreate, claims: dict = Depends(current_claims)) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, payload.branch_id, write=True)
        row = Driver(**payload.model_dump())
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="driver licence already exists in branch") from None
        return {"id": str(row.id)}


@router.post("/maintenance", status_code=201)
def add_maintenance(payload: MaintenanceWorkOrderCreate, claims: dict = Depends(current_claims)) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, payload.branch_id, write=True)
        _vehicle(db, payload.branch_id, payload.vehicle_id)
        row = MaintenanceWorkOrder(**payload.model_dump())
        db.add(row)
        db.commit()
        return {"id": str(row.id)}


@router.post("/maintenance/{work_order_id}/close")
def close_maintenance(work_order_id: uuid.UUID, claims: dict = Depends(current_claims)) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        row = db.get(MaintenanceWorkOrder, work_order_id)
        if row is None:
            raise HTTPException(status_code=404, detail="maintenance work order not found")
        _require_branch(db, profile, row.branch_id, write=True)
        row.status = "closed"
        row.closed_at = _utcnow()
        db.commit()
        return {"status": "closed"}


@router.post("/assignments", status_code=201)
def add_assignment(payload: AssignmentCreate, claims: dict = Depends(current_claims)) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, payload.branch_id, write=True)
        _vehicle(db, payload.branch_id, payload.vehicle_id)
        _driver(db, payload.branch_id, payload.driver_id)
        row = Assignment(**payload.model_dump())
        db.add(row)
        db.commit()
        return {"id": str(row.id)}


@router.post("/assignments/{assignment_id}/complete")
def complete_assignment(assignment_id: uuid.UUID, claims: dict = Depends(current_claims)) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        row = db.get(Assignment, assignment_id)
        if row is None:
            raise HTTPException(status_code=404, detail="assignment not found")
        _require_branch(db, profile, row.branch_id, write=True)
        row.status = "completed"
        row.end_at = row.end_at or _utcnow()
        db.commit()
        return {"status": "completed"}


@router.post("/trips", status_code=201)
def add_trip(payload: TripCreate, claims: dict = Depends(current_claims)) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, payload.branch_id, write=True)
        _vehicle(db, payload.branch_id, payload.vehicle_id)
        _driver(db, payload.branch_id, payload.driver_id)
        row = Trip(**payload.model_dump())
        db.add(row)
        db.commit()
        return {"id": str(row.id)}


@router.post("/trips/{trip_id}/return")
def return_trip(trip_id: uuid.UUID, claims: dict = Depends(current_claims)) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        row = db.get(Trip, trip_id)
        if row is None:
            raise HTTPException(status_code=404, detail="trip not found")
        _require_branch(db, profile, row.branch_id, write=True)
        row.status = "completed"
        row.actual_return_at = _utcnow()
        db.commit()
        return {"status": "completed"}


@router.post("/reservations", status_code=201)
def add_reservation(payload: ReservationCreate, claims: dict = Depends(current_claims)) -> dict[str, str]:
    if payload.end_at <= payload.start_at:
        raise HTTPException(status_code=422, detail="reservation end must be after start")
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, payload.branch_id, write=True)
        _vehicle(db, payload.branch_id, payload.vehicle_id)
        if payload.driver_id:
            _driver(db, payload.branch_id, payload.driver_id)
        row = Reservation(**payload.model_dump())
        db.add(row)
        db.commit()
        return {"id": str(row.id)}


@router.post("/reservations/{reservation_id}/cancel")
def cancel_reservation(reservation_id: uuid.UUID, claims: dict = Depends(current_claims)) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        row = db.get(Reservation, reservation_id)
        if row is None:
            raise HTTPException(status_code=404, detail="reservation not found")
        _require_branch(db, profile, row.branch_id, write=True)
        row.status = "cancelled"
        db.commit()
        return {"status": "cancelled"}


@router.post("/fuel", status_code=201)
def add_fuel(payload: FuelRecordCreate, claims: dict = Depends(current_claims)) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, payload.branch_id, write=True)
        vehicle = _vehicle(db, payload.branch_id, payload.vehicle_id)
        values = payload.model_dump()
        if values["recorded_at"] is None:
            values["recorded_at"] = _utcnow()
        row = FuelRecord(**values)
        db.add(row)
        if payload.mileage > vehicle.current_mileage:
            vehicle.current_mileage = payload.mileage
        db.commit()
        return {"id": str(row.id)}


@router.post("/accidents", status_code=201)
def add_accident(payload: AccidentRecordCreate, claims: dict = Depends(current_claims)) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, payload.branch_id, write=True)
        _vehicle(db, payload.branch_id, payload.vehicle_id)
        if payload.driver_id:
            _driver(db, payload.branch_id, payload.driver_id)
        row = AccidentRecord(**payload.model_dump())
        db.add(row)
        db.commit()
        return {"id": str(row.id)}


@router.post("/match")
def match(payload: VehicleMatchRequest, claims: dict = Depends(current_claims)) -> dict[str, Any]:
    if payload.end_at <= payload.start_at:
        raise HTTPException(status_code=422, detail="request end must be after start")
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, payload.branch_id)
        if payload.driver_id:
            _driver(db, payload.branch_id, payload.driver_id)
        return match_vehicles(
            db,
            branch_id=payload.branch_id,
            vehicle_type=payload.vehicle_type,
            start_at=payload.start_at,
            end_at=payload.end_at,
            driver_id=payload.driver_id,
        )


@router.get("/dashboard")
def dashboard(branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        branch = _require_branch(db, profile, branch_id)
        vehicles = list(db.scalars(select(Vehicle).where(Vehicle.branch_id == branch_id, Vehicle.is_active.is_(True))))
        snapshots = [evaluate_vehicle(db, vehicle) for vehicle in vehicles]
        alerts: list[dict[str, Any]] = []
        for snapshot in snapshots:
            for alert in snapshot["alerts"]:
                alerts.append(
                    {
                        "vehicle_id": snapshot["vehicle"]["id"],
                        "registration_plate": snapshot["vehicle"]["registration_plate"],
                        **alert,
                    }
                )
        return {
            "branch": {"id": str(branch.id), "code": branch.code, "name": branch.name},
            "totals": {
                "vehicles": len(vehicles),
                "available_now": sum(1 for x in snapshots if x["availability"]["label"] == "AVAILABLE NOW"),
                "documents_attention": sum(1 for x in snapshots if x["documents"]["overall"]["level"] != "green"),
                "service_attention": sum(1 for x in snapshots if x["service"]["level"] != "green"),
                "mechanical_attention": sum(1 for x in snapshots if x["mechanical"]["level"] != "green"),
                "out_of_service": sum(1 for x in snapshots if x["mechanical"]["level"] == "red"),
            },
            "readiness": {
                "green": sum(1 for x in snapshots if x["readiness"] == "green"),
                "orange": sum(1 for x in snapshots if x["readiness"] == "orange"),
                "red": sum(1 for x in snapshots if x["readiness"] == "red"),
            },
            "alerts": alerts[:100],
            "vehicles": snapshots,
        }
