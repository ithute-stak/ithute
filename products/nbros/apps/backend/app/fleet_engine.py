from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from .models import (
    Assignment,
    DocumentRequirement,
    Driver,
    FleetSetting,
    Inspection,
    MaintenanceWorkOrder,
    MechanicalFault,
    Reservation,
    ServiceKitRule,
    ServiceRecord,
    Trip,
    Vehicle,
    VehicleDocument,
    VehicleTypeLicenseRule,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _status(level: str, label: str, detail: str, *, source_type: str | None = None, source_id: Any = None) -> dict[str, Any]:
    result: dict[str, Any] = {"level": level, "label": label, "detail": detail}
    if source_type:
        result["source_type"] = source_type
    if source_id is not None:
        result["source_id"] = str(source_id)
    return result


def document_status(document: VehicleDocument, today: date, warning_days: int, critical_days: int) -> dict[str, Any]:
    if document.expiry_date is None:
        return _status("green", "VALID", "No expiry date applies.", source_type="vehicle_document", source_id=document.id)
    days = (document.expiry_date - today).days
    if days < 0:
        return _status("red", "EXPIRED", f"Expired {-days} day(s) ago.", source_type="vehicle_document", source_id=document.id)
    if days <= critical_days:
        return _status("red", "CRITICAL", f"Expires in {days} day(s).", source_type="vehicle_document", source_id=document.id)
    if days <= warning_days:
        return _status("orange", "EXPIRES SOON", f"Expires in {days} day(s).", source_type="vehicle_document", source_id=document.id)
    return _status("green", "VALID", f"Valid for {days} more day(s).", source_type="vehicle_document", source_id=document.id)


def _fleet_setting(db: Session, branch_id) -> FleetSetting:
    row = db.get(FleetSetting, branch_id)
    if row is None:
        return FleetSetting(
            branch_id=branch_id,
            document_warning_days=30,
            document_critical_days=7,
            service_warning_days=30,
            service_mileage_warning=1000,
        )
    return row


def evaluate_vehicle(db: Session, vehicle: Vehicle, *, at: datetime | None = None) -> dict[str, Any]:
    at = at or _now()
    today = at.date()
    setting = _fleet_setting(db, vehicle.branch_id)

    documents = list(
        db.scalars(
            select(VehicleDocument)
            .where(VehicleDocument.vehicle_id == vehicle.id)
            .order_by(VehicleDocument.created_at.desc())
        )
    )
    requirements = list(
        db.scalars(
            select(DocumentRequirement).where(
                DocumentRequirement.branch_id == vehicle.branch_id,
                DocumentRequirement.is_required.is_(True),
                or_(DocumentRequirement.vehicle_type.is_(None), DocumentRequirement.vehicle_type == vehicle.vehicle_type),
            )
        )
    )

    document_items: list[dict[str, Any]] = []
    required_types = {r.document_type.strip().lower(): r for r in requirements}
    docs_by_type: dict[str, list[VehicleDocument]] = {}
    for doc in documents:
        docs_by_type.setdefault(doc.document_type.strip().lower(), []).append(doc)

    for key, requirement in required_types.items():
        candidates = docs_by_type.get(key, [])
        if not candidates:
            document_items.append(
                _status("red", "MISSING", f"Required document missing: {requirement.document_type}.", source_type="document_requirement", source_id=requirement.id)
            )
            document_items[-1]["document_type"] = requirement.document_type
            continue
        doc = candidates[0]
        result = document_status(
            doc,
            today,
            requirement.warning_days or setting.document_warning_days,
            requirement.critical_days or setting.document_critical_days,
        )
        result["document_type"] = doc.document_type
        result["document_number"] = doc.document_number
        result["expiry_date"] = doc.expiry_date.isoformat() if doc.expiry_date else None
        result["file_url"] = doc.file_url
        document_items.append(result)

    for key, candidates in docs_by_type.items():
        if key in required_types:
            continue
        doc = candidates[0]
        result = document_status(doc, today, setting.document_warning_days, setting.document_critical_days)
        result["document_type"] = doc.document_type
        result["document_number"] = doc.document_number
        result["expiry_date"] = doc.expiry_date.isoformat() if doc.expiry_date else None
        result["file_url"] = doc.file_url
        document_items.append(result)

    if any(item["label"] == "EXPIRED" for item in document_items):
        documents_overall = _status("red", "DOCUMENTS EXPIRED", "One or more required documents have expired.")
    elif any(item["label"] == "MISSING" for item in document_items):
        documents_overall = _status("red", "DOCUMENTS INCOMPLETE", "One or more required documents are missing.")
    elif any(item["level"] in {"orange", "red"} for item in document_items):
        documents_overall = _status("orange", "DOCUMENTS EXPIRING SOON", "One or more documents require renewal attention.")
    else:
        documents_overall = _status("green", "DOCUMENTS VALID", "All recorded required documents are valid.")

    latest_service = db.scalar(
        select(ServiceRecord)
        .where(ServiceRecord.vehicle_id == vehicle.id)
        .order_by(ServiceRecord.service_date.desc(), ServiceRecord.created_at.desc())
        .limit(1)
    )
    service_kit = None
    if latest_service is None:
        service = _status("orange", "SERVICE HISTORY MISSING", "No service record exists for this vehicle.")
    else:
        overdue_date = latest_service.next_service_date is not None and latest_service.next_service_date < today
        overdue_mileage = latest_service.next_service_mileage is not None and vehicle.current_mileage >= latest_service.next_service_mileage
        due_soon_date = (
            latest_service.next_service_date is not None
            and 0 <= (latest_service.next_service_date - today).days <= setting.service_warning_days
        )
        due_soon_mileage = (
            latest_service.next_service_mileage is not None
            and 0 <= latest_service.next_service_mileage - vehicle.current_mileage <= setting.service_mileage_warning
        )
        if overdue_date or overdue_mileage:
            service = _status("red", "SERVICE OVERDUE", "Service date or mileage threshold has been exceeded.", source_type="service_record", source_id=latest_service.id)
        elif due_soon_date or due_soon_mileage:
            service = _status("orange", "SERVICE DUE SOON", "Prepare the next service and required kit.", source_type="service_record", source_id=latest_service.id)
        else:
            service = _status("green", "SERVICE UP TO DATE", "No service threshold is currently due.", source_type="service_record", source_id=latest_service.id)

        kit_rule = db.scalar(
            select(ServiceKitRule).where(
                ServiceKitRule.branch_id == vehicle.branch_id,
                ServiceKitRule.make.ilike(vehicle.make),
                ServiceKitRule.model.ilike(vehicle.model),
                ServiceKitRule.service_type.ilike(latest_service.service_type),
            )
        )
        service_kit = kit_rule.kit_name if kit_rule else latest_service.service_kit

    unresolved_faults = list(
        db.scalars(
            select(MechanicalFault).where(
                MechanicalFault.vehicle_id == vehicle.id,
                MechanicalFault.resolved_at.is_(None),
            )
        )
    )
    critical_fault = next((fault for fault in unresolved_faults if fault.severity == "critical"), None)
    if critical_fault or vehicle.mechanical_condition == "out_of_service":
        fault = critical_fault
        mechanical = _status(
            "red",
            "OUT OF SERVICE",
            fault.description if fault else "Vehicle is marked out of service.",
            source_type="mechanical_fault" if fault else "vehicle",
            source_id=fault.id if fault else vehicle.id,
        )
    elif unresolved_faults or vehicle.mechanical_condition == "attention":
        fault = unresolved_faults[0] if unresolved_faults else None
        mechanical = _status(
            "orange",
            "REQUIRES ATTENTION",
            fault.description if fault else "Vehicle requires mechanical attention.",
            source_type="mechanical_fault" if fault else "vehicle",
            source_id=fault.id if fault else vehicle.id,
        )
    else:
        mechanical = _status("green", "OPERATIONAL", "No unresolved mechanical fault blocks operation.", source_type="vehicle", source_id=vehicle.id)

    latest_inspection = db.scalar(
        select(Inspection)
        .where(Inspection.vehicle_id == vehicle.id)
        .order_by(Inspection.inspection_date.desc(), Inspection.created_at.desc())
        .limit(1)
    )
    if latest_inspection is None:
        inspection = _status("orange", "INSPECTION UNKNOWN", "No inspection record exists.")
    elif latest_inspection.status == "failed" or (
        latest_inspection.next_inspection_date is not None and latest_inspection.next_inspection_date < today
    ):
        inspection = _status("red", "INSPECTION FAILED/OVERDUE", "Inspection blocks vehicle readiness.", source_type="inspection", source_id=latest_inspection.id)
    elif latest_inspection.status == "attention":
        inspection = _status("orange", "INSPECTION ATTENTION", "Inspection requires follow-up.", source_type="inspection", source_id=latest_inspection.id)
    else:
        inspection = _status("green", "INSPECTION CURRENT", "Latest inspection passed.", source_type="inspection", source_id=latest_inspection.id)

    maintenance = db.scalar(
        select(MaintenanceWorkOrder).where(
            MaintenanceWorkOrder.vehicle_id == vehicle.id,
            MaintenanceWorkOrder.status.in_(["open", "in_progress"]),
        ).order_by(MaintenanceWorkOrder.opened_at.desc())
    )
    assignment = db.scalar(
        select(Assignment).where(
            Assignment.vehicle_id == vehicle.id,
            Assignment.status == "active",
            Assignment.start_at <= at,
            or_(Assignment.end_at.is_(None), Assignment.end_at >= at),
        ).order_by(Assignment.start_at.desc())
    )
    trip = db.scalar(
        select(Trip).where(
            Trip.vehicle_id == vehicle.id,
            Trip.status == "active",
            Trip.start_at <= at,
            Trip.actual_return_at.is_(None),
        ).order_by(Trip.start_at.desc())
    )
    reservation = db.scalar(
        select(Reservation).where(
            Reservation.vehicle_id == vehicle.id,
            Reservation.status == "active",
            Reservation.start_at <= at,
            Reservation.end_at >= at,
        ).order_by(Reservation.start_at.desc())
    )

    blockers: list[dict[str, Any]] = []
    if documents_overall["level"] == "red":
        blockers.append(documents_overall)
    if mechanical["level"] == "red":
        blockers.append(mechanical)
    if service["level"] == "red":
        blockers.append(service)
    if inspection["level"] == "red":
        blockers.append(inspection)
    if maintenance:
        blockers.append(_status("red", "UNDER MAINTENANCE", maintenance.description, source_type="maintenance_work_order", source_id=maintenance.id))
    if trip:
        blockers.append(_status("red", "ON ACTIVE TRIP", f"Trip to {trip.destination}.", source_type="trip", source_id=trip.id))
    if assignment:
        blockers.append(_status("red", "ASSIGNED", assignment.purpose or "Vehicle has an active assignment.", source_type="assignment", source_id=assignment.id))
    if reservation:
        blockers.append(_status("red", "RESERVED", reservation.purpose or "Vehicle is reserved.", source_type="reservation", source_id=reservation.id))

    release_candidates: list[datetime] = []
    if maintenance and maintenance.expected_release_at:
        release_candidates.append(maintenance.expected_release_at)
    if trip and trip.expected_return_at:
        release_candidates.append(trip.expected_return_at)
    if assignment and assignment.end_at:
        release_candidates.append(assignment.end_at)
    if reservation:
        release_candidates.append(reservation.end_at)

    if not blockers:
        availability = _status("green", "AVAILABLE NOW", "All availability checks passed.")
        expected_available_at = at
    elif release_candidates:
        expected_available_at = max(release_candidates)
        availability = _status("orange", "EXPECTED LATER", f"Expected operational release: {expected_available_at.isoformat()}.")
    else:
        expected_available_at = None
        availability = _status("red", "AVAILABILITY UNKNOWN", "Unavailable and no reliable release date is recorded.")

    component_levels = [documents_overall["level"], service["level"], mechanical["level"], inspection["level"], availability["level"]]
    readiness_level = "red" if "red" in component_levels else "orange" if "orange" in component_levels else "green"

    alerts = [
        item
        for item in [documents_overall, service, mechanical, inspection, availability]
        if item["level"] != "green"
    ]

    return {
        "vehicle": {
            "id": str(vehicle.id),
            "branch_id": str(vehicle.branch_id),
            "registration_plate": vehicle.registration_plate,
            "make": vehicle.make,
            "model": vehicle.model,
            "vehicle_type": vehicle.vehicle_type,
            "current_mileage": vehicle.current_mileage,
        },
        "readiness": readiness_level,
        "documents": {"overall": documents_overall, "items": document_items},
        "service": {**service, "service_kit": service_kit},
        "mechanical": mechanical,
        "inspection": inspection,
        "availability": {
            **availability,
            "expected_available_at": expected_available_at.isoformat() if expected_available_at else None,
            "blockers": blockers,
        },
        "alerts": alerts,
    }


def vehicle_matches_period(
    db: Session,
    vehicle: Vehicle,
    start_at: datetime,
    end_at: datetime,
) -> tuple[bool, list[str], datetime | None]:
    reasons: list[str] = []
    expected_release: list[datetime] = []
    snapshot = evaluate_vehicle(db, vehicle, at=start_at)
    for blocker in snapshot["availability"]["blockers"]:
        if blocker["label"] not in {"ASSIGNED", "ON ACTIVE TRIP", "RESERVED"}:
            reasons.append(blocker["label"])
    expected_from_snapshot = snapshot["availability"].get("expected_available_at")
    if expected_from_snapshot:
        try:
            expected_release.append(datetime.fromisoformat(expected_from_snapshot))
        except ValueError:
            pass

    assignment = db.scalar(
        select(Assignment).where(
            Assignment.vehicle_id == vehicle.id,
            Assignment.status == "active",
            Assignment.start_at < end_at,
            or_(Assignment.end_at.is_(None), Assignment.end_at > start_at),
        ).order_by(Assignment.start_at.desc()).limit(1)
    )
    trip = db.scalar(
        select(Trip).where(
            Trip.vehicle_id == vehicle.id,
            Trip.status == "active",
            Trip.start_at < end_at,
            or_(Trip.expected_return_at.is_(None), Trip.expected_return_at > start_at),
        ).order_by(Trip.start_at.desc()).limit(1)
    )
    reservation = db.scalar(
        select(Reservation).where(
            Reservation.vehicle_id == vehicle.id,
            Reservation.status == "active",
            Reservation.start_at < end_at,
            Reservation.end_at > start_at,
        ).order_by(Reservation.start_at.desc()).limit(1)
    )
    if assignment:
        reasons.append("ASSIGNED FOR REQUESTED PERIOD")
        if assignment.end_at:
            expected_release.append(assignment.end_at)
    if trip:
        reasons.append("ACTIVE TRIP CONFLICT")
        if trip.expected_return_at:
            expected_release.append(trip.expected_return_at)
    if reservation:
        reasons.append("RESERVATION CONFLICT")
        expected_release.append(reservation.end_at)
    expected = max(expected_release) if expected_release else None
    return not reasons, list(dict.fromkeys(reasons)), expected

def match_vehicles(
    db: Session,
    *,
    branch_id,
    vehicle_type: str,
    start_at: datetime,
    end_at: datetime,
    driver_id=None,
) -> dict[str, Any]:
    driver = db.get(Driver, driver_id) if driver_id else None
    if driver is not None:
        if not driver.is_active:
            return {"recommended": None, "available": [], "excluded": [], "driver_error": "Driver is inactive.", "next_expected_availability": None}
        if driver.license_expiry < start_at.date():
            return {"recommended": None, "available": [], "excluded": [], "driver_error": "Driver licence is expired.", "next_expected_availability": None}
        driver_assignment = db.scalar(
            select(Assignment.id).where(
                Assignment.driver_id == driver.id,
                Assignment.status == "active",
                Assignment.start_at < end_at,
                or_(Assignment.end_at.is_(None), Assignment.end_at > start_at),
            ).limit(1)
        )
        driver_trip = db.scalar(
            select(Trip.id).where(
                Trip.driver_id == driver.id,
                Trip.status == "active",
                Trip.start_at < end_at,
                or_(Trip.expected_return_at.is_(None), Trip.expected_return_at > start_at),
            ).limit(1)
        )
        if driver_assignment or driver_trip:
            return {"recommended": None, "available": [], "excluded": [], "driver_error": "Driver is already committed during the requested period.", "next_expected_availability": None}
        allowed_rules = list(
            db.scalars(
                select(VehicleTypeLicenseRule).where(
                    VehicleTypeLicenseRule.branch_id == branch_id,
                    VehicleTypeLicenseRule.vehicle_type.ilike(vehicle_type),
                )
            )
        )
        if allowed_rules and driver.license_category not in {rule.license_category for rule in allowed_rules}:
            return {"recommended": None, "available": [], "excluded": [], "driver_error": "Driver licence category is not suitable.", "next_expected_availability": None}

    vehicles = list(
        db.scalars(
            select(Vehicle).where(
                Vehicle.branch_id == branch_id,
                Vehicle.is_active.is_(True),
                Vehicle.vehicle_type.ilike(vehicle_type),
            )
        )
    )
    available: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    release_dates: list[datetime] = []
    for vehicle in vehicles:
        ok, reasons, expected_release = vehicle_matches_period(db, vehicle, start_at, end_at)
        if ok:
            snapshot = evaluate_vehicle(db, vehicle, at=start_at)
            score = {"green": 3, "orange": 2, "red": 1}[snapshot["readiness"]]
            available.append({"vehicle": snapshot["vehicle"], "readiness": snapshot["readiness"], "score": score})
        else:
            if expected_release:
                release_dates.append(expected_release)
            excluded.append(
                {
                    "vehicle_id": str(vehicle.id),
                    "registration_plate": vehicle.registration_plate,
                    "reasons": reasons,
                    "expected_available_at": expected_release.isoformat() if expected_release else None,
                }
            )
    available.sort(key=lambda item: (-item["score"], item["vehicle"]["current_mileage"]))
    recommended = available[0] if available else None
    next_expected = min(release_dates) if release_dates and not available else None
    return {
        "recommended": recommended,
        "available": available,
        "excluded": excluded,
        "driver_error": None,
        "next_expected_availability": next_expected.isoformat() if next_expected else None,
    }
