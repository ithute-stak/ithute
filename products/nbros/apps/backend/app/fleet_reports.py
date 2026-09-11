from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from .auth import current_claims
from .db import SessionLocal
from .fleet import _profile, _require_branch, _vehicle
from .fleet_alerts import FleetAlert
from .fleet_engine import evaluate_vehicle
from .fleet_inventory import vehicle_service_kit_stock
from .models import AccidentRecord, Assignment, Driver, FuelRecord, Inspection, MaintenanceWorkOrder, MechanicalFault, Reservation, ServiceRecord, Trip, Vehicle, VehicleDocument

router = APIRouter(prefix="/api/v1/fleet", tags=["fleet-reports"])


def _as_float(value: Decimal | int | float | None) -> float:
    return float(value or 0)


def _window(from_date: date | None, to_date: date | None) -> tuple[date, date, datetime, datetime]:
    end = to_date or date.today()
    start = from_date or (end - timedelta(days=29))
    if start > end:
        raise HTTPException(status_code=422, detail="from_date must be on or before to_date")
    return start, end, datetime.combine(start, time.min, tzinfo=timezone.utc), datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc)


def build_branch_summary(db, branch_id: uuid.UUID, *, from_date: date | None = None, to_date: date | None = None) -> dict[str, Any]:
    start, end, start_at, end_at = _window(from_date, to_date)
    vehicles = list(db.scalars(select(Vehicle).where(Vehicle.branch_id == branch_id, Vehicle.is_active.is_(True)).order_by(Vehicle.registration_plate)))
    drivers = list(db.scalars(select(Driver).where(Driver.branch_id == branch_id, Driver.is_active.is_(True))))
    service_rows = list(db.scalars(select(ServiceRecord).where(ServiceRecord.branch_id == branch_id, ServiceRecord.service_date >= start, ServiceRecord.service_date <= end)))
    fuel_rows = list(db.scalars(select(FuelRecord).where(FuelRecord.branch_id == branch_id, FuelRecord.recorded_at >= start_at, FuelRecord.recorded_at < end_at)))
    accident_rows = list(db.scalars(select(AccidentRecord).where(AccidentRecord.branch_id == branch_id, AccidentRecord.occurred_at >= start_at, AccidentRecord.occurred_at < end_at)))
    trip_rows = list(db.scalars(select(Trip).where(Trip.branch_id == branch_id, Trip.start_at >= start_at, Trip.start_at < end_at)))
    maintenance_rows = list(db.scalars(select(MaintenanceWorkOrder).where(MaintenanceWorkOrder.branch_id == branch_id, MaintenanceWorkOrder.opened_at >= start_at, MaintenanceWorkOrder.opened_at < end_at)))
    alerts = list(db.scalars(select(FleetAlert).where(FleetAlert.branch_id == branch_id, FleetAlert.resolved_at.is_(None))))

    readiness = {"green": 0, "orange": 0, "red": 0}
    inventory = {"available": 0, "reorder": 0, "stock_required": 0, "unknown": 0}
    available_now = 0
    vehicle_costs = {vehicle.id: {"vehicle_id": str(vehicle.id), "registration_plate": vehicle.registration_plate, "service_cost": 0.0, "fuel_cost": 0.0, "total_cost": 0.0} for vehicle in vehicles}

    for vehicle in vehicles:
        snapshot = evaluate_vehicle(db, vehicle)
        readiness[snapshot["readiness"]] += 1
        if snapshot["availability"]["label"] == "AVAILABLE NOW":
            available_now += 1
        stock = vehicle_service_kit_stock(db, vehicle, service_snapshot=snapshot.get("service"))
        label = str(stock.get("label") or "")
        if label == "AVAILABLE": inventory["available"] += 1
        elif "REORDER" in label: inventory["reorder"] += 1
        elif "STOCK REQUIRED" in label: inventory["stock_required"] += 1
        else: inventory["unknown"] += 1

    for row in service_rows:
        if row.vehicle_id in vehicle_costs: vehicle_costs[row.vehicle_id]["service_cost"] += _as_float(row.cost)
    for row in fuel_rows:
        if row.vehicle_id in vehicle_costs: vehicle_costs[row.vehicle_id]["fuel_cost"] += _as_float(row.cost)
    for row in vehicle_costs.values(): row["total_cost"] = row["service_cost"] + row["fuel_cost"]

    active_assignments = db.scalar(select(func.count(Assignment.id)).where(Assignment.branch_id == branch_id, Assignment.status == "active")) or 0
    active_trips = db.scalar(select(func.count(Trip.id)).where(Trip.branch_id == branch_id, Trip.status == "active")) or 0
    active_reservations = db.scalar(select(func.count(Reservation.id)).where(Reservation.branch_id == branch_id, Reservation.status == "active")) or 0
    open_maintenance = db.scalar(select(func.count(MaintenanceWorkOrder.id)).where(MaintenanceWorkOrder.branch_id == branch_id, MaintenanceWorkOrder.status.in_(["open", "in_progress"]))) or 0
    alert_counts = {"red": 0, "orange": 0}
    for alert in alerts:
        if alert.severity in alert_counts: alert_counts[alert.severity] += 1

    return {
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "fleet": {"vehicles": len(vehicles), "drivers": len(drivers), "available_now": available_now, "readiness": readiness},
        "operations": {"active_assignments": int(active_assignments), "active_trips": int(active_trips), "active_reservations": int(active_reservations), "open_maintenance": int(open_maintenance), "trips_in_window": len(trip_rows), "accidents_in_window": len(accident_rows)},
        "costs": {"service_total": sum(_as_float(row.cost) for row in service_rows), "fuel_total": sum(_as_float(row.cost) for row in fuel_rows), "fuel_litres": sum(_as_float(row.litres) for row in fuel_rows), "maintenance_jobs_in_window": len(maintenance_rows)},
        "alerts": {"active": len(alerts), **alert_counts},
        "service_kit_stock": inventory,
        "vehicle_costs": sorted(vehicle_costs.values(), key=lambda item: (-item["total_cost"], item["registration_plate"])),
    }


def vehicle_history_rows(db, branch_id: uuid.UUID, vehicle_id: uuid.UUID) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    def add(kind: str, at: datetime | date, title: str, detail: str, **extra: Any) -> None:
        instant = datetime.combine(at, time.min, tzinfo=timezone.utc) if isinstance(at, date) and not isinstance(at, datetime) else at
        if instant.tzinfo is None: instant = instant.replace(tzinfo=timezone.utc)
        events.append({"kind": kind, "at": instant.isoformat(), "title": title, "detail": detail, **extra})

    for row in db.scalars(select(VehicleDocument).where(VehicleDocument.branch_id == branch_id, VehicleDocument.vehicle_id == vehicle_id).order_by(VehicleDocument.created_at.desc())):
        expiry = f" · expires {row.expiry_date.isoformat()}" if row.expiry_date else ""
        add("document", row.created_at, row.document_type, f"{row.document_number or 'No document number'}{expiry}", source_id=str(row.id))
    for row in db.scalars(select(ServiceRecord).where(ServiceRecord.branch_id == branch_id, ServiceRecord.vehicle_id == vehicle_id).order_by(ServiceRecord.service_date.desc())):
        add("service", row.service_date, row.service_type, f"{row.mileage:,} km · cost {_as_float(row.cost):.2f}", source_id=str(row.id))
    for row in db.scalars(select(MechanicalFault).where(MechanicalFault.branch_id == branch_id, MechanicalFault.vehicle_id == vehicle_id).order_by(MechanicalFault.reported_at.desc())):
        add("fault", row.reported_at, f"{row.severity.upper()} mechanical fault", row.description, source_id=str(row.id), resolved_at=row.resolved_at.isoformat() if row.resolved_at else None)
    for row in db.scalars(select(Inspection).where(Inspection.branch_id == branch_id, Inspection.vehicle_id == vehicle_id).order_by(Inspection.inspection_date.desc())):
        add("inspection", row.inspection_date, f"Inspection · {row.status}", row.notes or row.inspector or "Inspection recorded.", source_id=str(row.id))
    for row in db.scalars(select(MaintenanceWorkOrder).where(MaintenanceWorkOrder.branch_id == branch_id, MaintenanceWorkOrder.vehicle_id == vehicle_id).order_by(MaintenanceWorkOrder.opened_at.desc())):
        add("maintenance", row.opened_at, f"Maintenance · {row.status}", row.description, source_id=str(row.id), closed_at=row.closed_at.isoformat() if row.closed_at else None)
    for row in db.scalars(select(Assignment).where(Assignment.branch_id == branch_id, Assignment.vehicle_id == vehicle_id).order_by(Assignment.start_at.desc())):
        add("assignment", row.start_at, f"Assignment · {row.status}", row.purpose or "Vehicle assignment", source_id=str(row.id), driver_id=str(row.driver_id), end_at=row.end_at.isoformat() if row.end_at else None)
    for row in db.scalars(select(Trip).where(Trip.branch_id == branch_id, Trip.vehicle_id == vehicle_id).order_by(Trip.start_at.desc())):
        add("trip", row.start_at, f"Trip to {row.destination}", row.purpose or row.status, source_id=str(row.id), driver_id=str(row.driver_id), return_at=(row.actual_return_at or row.expected_return_at).isoformat() if (row.actual_return_at or row.expected_return_at) else None)
    for row in db.scalars(select(Reservation).where(Reservation.branch_id == branch_id, Reservation.vehicle_id == vehicle_id).order_by(Reservation.start_at.desc())):
        add("reservation", row.start_at, f"Reservation · {row.status}", row.purpose or "Vehicle reservation", source_id=str(row.id), end_at=row.end_at.isoformat())
    for row in db.scalars(select(FuelRecord).where(FuelRecord.branch_id == branch_id, FuelRecord.vehicle_id == vehicle_id).order_by(FuelRecord.recorded_at.desc())):
        add("fuel", row.recorded_at, "Fuel record", f"{_as_float(row.litres):.2f} L · cost {_as_float(row.cost):.2f} · {row.mileage:,} km", source_id=str(row.id))
    for row in db.scalars(select(AccidentRecord).where(AccidentRecord.branch_id == branch_id, AccidentRecord.vehicle_id == vehicle_id).order_by(AccidentRecord.occurred_at.desc())):
        add("accident", row.occurred_at, "Accident / incident", row.description, source_id=str(row.id), reference_number=row.reference_number)
    for row in db.scalars(select(FleetAlert).where(FleetAlert.branch_id == branch_id, FleetAlert.vehicle_id == vehicle_id).order_by(FleetAlert.first_seen_at.desc())):
        add("alert", row.first_seen_at, row.label, row.detail, source_id=str(row.id), severity=row.severity, resolved_at=row.resolved_at.isoformat() if row.resolved_at else None)
    events.sort(key=lambda item: item["at"], reverse=True)
    return events[:500]


@router.get("/reports/summary")
def report_summary(branch_id: uuid.UUID = Query(...), from_date: date | None = Query(default=None), to_date: date | None = Query(default=None), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id)
        return build_branch_summary(db, branch_id, from_date=from_date, to_date=to_date)


@router.get("/reports/vehicle-history")
def vehicle_history(branch_id: uuid.UUID = Query(...), vehicle_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, branch_id)
        vehicle = _vehicle(db, branch_id, vehicle_id)
        return {"vehicle": {"id": str(vehicle.id), "registration_plate": vehicle.registration_plate, "make": vehicle.make, "model": vehicle.model, "vehicle_type": vehicle.vehicle_type}, "events": vehicle_history_rows(db, branch_id, vehicle.id)}
