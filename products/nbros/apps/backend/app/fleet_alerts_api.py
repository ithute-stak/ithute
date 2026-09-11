from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from redis import Redis
from sqlalchemy import func, select

from .auth import current_claims
from .config import settings
from .db import SessionLocal
from .fleet import _profile, _require_branch
from .fleet_alerts import FleetAlert
from .models import Vehicle

router = APIRouter(prefix="/api/v1/fleet", tags=["fleet-alerts"])


def _serialize(row: FleetAlert, registration_plate: str | None) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "branch_id": str(row.branch_id),
        "vehicle_id": str(row.vehicle_id),
        "registration_plate": registration_plate,
        "severity": row.severity,
        "label": row.label,
        "detail": row.detail,
        "source_type": row.source_type,
        "source_id": row.source_id,
        "first_seen_at": row.first_seen_at,
        "last_seen_at": row.last_seen_at,
        "resolved_at": row.resolved_at,
        "last_notified_at": row.last_notified_at,
        "notification_attempts": row.notification_attempts,
        "last_notification_error": row.last_notification_error,
    }


@router.get("/alerts")
def list_alerts(
    branch_id: uuid.UUID = Query(...),
    active_only: bool = Query(True),
    claims: dict = Depends(current_claims),
) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id)
        stmt = (
            select(FleetAlert, Vehicle.registration_plate)
            .join(Vehicle, Vehicle.id == FleetAlert.vehicle_id)
            .where(FleetAlert.branch_id == branch_id)
        )
        if active_only:
            stmt = stmt.where(FleetAlert.resolved_at.is_(None))
        rows = db.execute(stmt.order_by(FleetAlert.last_seen_at.desc())).all()
        return [_serialize(alert, plate) for alert, plate in rows]


@router.get("/monitor/status")
def monitor_status(
    branch_id: uuid.UUID = Query(...),
    claims: dict = Depends(current_claims),
) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id)
        active = db.scalar(
            select(func.count(FleetAlert.id)).where(
                FleetAlert.branch_id == branch_id,
                FleetAlert.resolved_at.is_(None),
            )
        ) or 0
        failed_notifications = db.scalar(
            select(func.count(FleetAlert.id)).where(
                FleetAlert.branch_id == branch_id,
                FleetAlert.resolved_at.is_(None),
                FleetAlert.last_notification_error.is_not(None),
            )
        ) or 0
        latest = db.scalar(
            select(func.max(FleetAlert.last_seen_at)).where(FleetAlert.branch_id == branch_id)
        )

    monitor = None
    try:
        client = Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1)
        raw = client.get("nbros:fleet-monitor:last-run")
        client.close()
        if raw:
            monitor = json.loads(raw)
    except Exception:
        monitor = None

    return {
        "active_alerts": int(active),
        "notification_failures": int(failed_notifications),
        "latest_alert_evaluation": latest,
        "worker": monitor,
    }
