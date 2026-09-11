from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from .auth import current_claims
from .db import SessionLocal
from .fleet import _profile, _require_branch
from .models import (
    Assignment,
    DocumentRequirement,
    Driver,
    FleetSetting,
    MaintenanceWorkOrder,
    Reservation,
    ServiceKitRule,
    Trip,
    Vehicle,
    VehicleTypeLicenseRule,
)

router = APIRouter(prefix="/api/v1/fleet", tags=["fleet"])


def _vehicle_map(db, branch_id: uuid.UUID) -> dict[uuid.UUID, Vehicle]:
    rows = db.scalars(select(Vehicle).where(Vehicle.branch_id == branch_id))
    return {row.id: row for row in rows}


def _driver_map(db, branch_id: uuid.UUID) -> dict[uuid.UUID, Driver]:
    rows = db.scalars(select(Driver).where(Driver.branch_id == branch_id))
    return {row.id: row for row in rows}


@router.get("/operations")
def active_operations(
    branch_id: uuid.UUID = Query(...),
    claims: dict = Depends(current_claims),
) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id)
        vehicles = _vehicle_map(db, branch_id)
        drivers = _driver_map(db, branch_id)

        maintenance = list(
            db.scalars(
                select(MaintenanceWorkOrder)
                .where(
                    MaintenanceWorkOrder.branch_id == branch_id,
                    MaintenanceWorkOrder.status.in_(["open", "in_progress"]),
                )
                .order_by(MaintenanceWorkOrder.opened_at.desc())
            )
        )
        assignments = list(
            db.scalars(
                select(Assignment)
                .where(Assignment.branch_id == branch_id, Assignment.status == "active")
                .order_by(Assignment.start_at.desc())
            )
        )
        trips = list(
            db.scalars(
                select(Trip)
                .where(Trip.branch_id == branch_id, Trip.status == "active")
                .order_by(Trip.start_at.desc())
            )
        )
        reservations = list(
            db.scalars(
                select(Reservation)
                .where(Reservation.branch_id == branch_id, Reservation.status == "active")
                .order_by(Reservation.start_at.asc())
            )
        )

        def vehicle_name(vehicle_id: uuid.UUID) -> str:
            row = vehicles.get(vehicle_id)
            return row.registration_plate if row else str(vehicle_id)

        def driver_name(driver_id: uuid.UUID | None) -> str | None:
            if driver_id is None:
                return None
            row = drivers.get(driver_id)
            return row.full_name if row else str(driver_id)

        return {
            "maintenance": [
                {
                    "id": str(row.id),
                    "vehicle_id": str(row.vehicle_id),
                    "vehicle": vehicle_name(row.vehicle_id),
                    "status": row.status,
                    "description": row.description,
                    "opened_at": row.opened_at,
                    "expected_release_at": row.expected_release_at,
                }
                for row in maintenance
            ],
            "assignments": [
                {
                    "id": str(row.id),
                    "vehicle_id": str(row.vehicle_id),
                    "vehicle": vehicle_name(row.vehicle_id),
                    "driver_id": str(row.driver_id),
                    "driver": driver_name(row.driver_id),
                    "purpose": row.purpose,
                    "start_at": row.start_at,
                    "end_at": row.end_at,
                }
                for row in assignments
            ],
            "trips": [
                {
                    "id": str(row.id),
                    "vehicle_id": str(row.vehicle_id),
                    "vehicle": vehicle_name(row.vehicle_id),
                    "driver_id": str(row.driver_id),
                    "driver": driver_name(row.driver_id),
                    "destination": row.destination,
                    "purpose": row.purpose,
                    "start_at": row.start_at,
                    "expected_return_at": row.expected_return_at,
                }
                for row in trips
            ],
            "reservations": [
                {
                    "id": str(row.id),
                    "vehicle_id": str(row.vehicle_id),
                    "vehicle": vehicle_name(row.vehicle_id),
                    "driver_id": str(row.driver_id) if row.driver_id else None,
                    "driver": driver_name(row.driver_id),
                    "purpose": row.purpose,
                    "start_at": row.start_at,
                    "end_at": row.end_at,
                }
                for row in reservations
            ],
        }


@router.get("/settings")
def settings_view(
    branch_id: uuid.UUID = Query(...),
    claims: dict = Depends(current_claims),
) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id)
        setting = db.get(FleetSetting, branch_id)
        requirements = list(
            db.scalars(
                select(DocumentRequirement)
                .where(DocumentRequirement.branch_id == branch_id)
                .order_by(DocumentRequirement.document_type)
            )
        )
        licence_rules = list(
            db.scalars(
                select(VehicleTypeLicenseRule)
                .where(VehicleTypeLicenseRule.branch_id == branch_id)
                .order_by(VehicleTypeLicenseRule.vehicle_type, VehicleTypeLicenseRule.license_category)
            )
        )
        kit_rules = list(
            db.scalars(
                select(ServiceKitRule)
                .where(ServiceKitRule.branch_id == branch_id)
                .order_by(ServiceKitRule.make, ServiceKitRule.model, ServiceKitRule.service_type)
            )
        )
        return {
            "settings": {
                "document_warning_days": setting.document_warning_days if setting else 30,
                "document_critical_days": setting.document_critical_days if setting else 7,
                "service_warning_days": setting.service_warning_days if setting else 30,
                "service_mileage_warning": setting.service_mileage_warning if setting else 1000,
            },
            "document_requirements": [
                {
                    "id": str(row.id),
                    "document_type": row.document_type,
                    "vehicle_type": row.vehicle_type,
                    "is_required": row.is_required,
                    "warning_days": row.warning_days,
                    "critical_days": row.critical_days,
                }
                for row in requirements
            ],
            "licence_rules": [
                {
                    "id": str(row.id),
                    "vehicle_type": row.vehicle_type,
                    "license_category": row.license_category,
                }
                for row in licence_rules
            ],
            "service_kit_rules": [
                {
                    "id": str(row.id),
                    "make": row.make,
                    "model": row.model,
                    "service_type": row.service_type,
                    "kit_name": row.kit_name,
                }
                for row in kit_rules
            ],
        }
