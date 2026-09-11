from __future__ import annotations

import csv
import io
import threading
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy import func, select

from .auth import current_claims
from .db import SessionLocal
from .enterprise_models import AuditEvent, PurchaseOrder, WorkshopJobCard
from .enterprise_ops import _tco_rows
from .fleet import _profile, _require_branch
from .fleet_alerts import FleetAlert
from .fleet_engine import evaluate_vehicle
from .models import Vehicle

router = APIRouter(tags=["production-hardening"])

_started_at = time.monotonic()
_lock = threading.Lock()
_requests_total = 0
_status_counts: Counter[int] = Counter()


def _csv_response(filename: str, headers: list[str], rows: list[list[Any]]) -> StreamingResponse:
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(headers)
    writer.writerows(rows)
    payload = stream.getvalue().encode("utf-8-sig")
    return StreamingResponse(
        iter([payload]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def install_hardening(app) -> None:
    @app.middleware("http")
    async def security_and_observability(request: Request, call_next):
        global _requests_total
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            with _lock:
                _requests_total += 1
                _status_counts[500] += 1
            raise
        elapsed_ms = (time.perf_counter() - started) * 1000
        with _lock:
            _requests_total += 1
            _status_counts[response.status_code] += 1
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Server-Timing"] = f'app;dur={elapsed_ms:.2f}'
        return response


@router.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
def metrics() -> str:
    with _lock:
        total = _requests_total
        counts = dict(_status_counts)
    uptime = max(time.monotonic() - _started_at, 0)
    lines = [
        "# HELP nbros_uptime_seconds NBros API process uptime.",
        "# TYPE nbros_uptime_seconds gauge",
        f"nbros_uptime_seconds {uptime:.3f}",
        "# HELP nbros_http_requests_total HTTP requests served by this process.",
        "# TYPE nbros_http_requests_total counter",
        f"nbros_http_requests_total {total}",
    ]
    for code in sorted(counts):
        lines.append(f'nbros_http_responses_total{{status="{code}"}} {counts[code]}')
    return "\n".join(lines) + "\n"


@router.get("/api/v1/operations/observability")
def observability(branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id)
        active_alerts = db.scalar(select(func.count(FleetAlert.id)).where(FleetAlert.branch_id == branch_id, FleetAlert.resolved_at.is_(None))) or 0
        failed_notifications = db.scalar(select(func.count(FleetAlert.id)).where(FleetAlert.branch_id == branch_id, FleetAlert.resolved_at.is_(None), FleetAlert.last_notification_error.is_not(None))) or 0
        open_workshop = db.scalar(select(func.count(WorkshopJobCard.id)).where(WorkshopJobCard.branch_id == branch_id, WorkshopJobCard.status.notin_(["completed", "cancelled"]))) or 0
        open_orders = db.scalar(select(func.count(PurchaseOrder.id)).where(PurchaseOrder.branch_id == branch_id, PurchaseOrder.status.in_(["issued", "part_received"]))) or 0
        return {
            "generated_at": datetime.now(timezone.utc),
            "active_fleet_alerts": int(active_alerts),
            "alerts_with_notification_error": int(failed_notifications),
            "open_workshop_jobs": int(open_workshop),
            "open_purchase_orders": int(open_orders),
        }


@router.get("/api/v1/operations/exports/fleet.csv")
def export_fleet(branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)):
    with SessionLocal() as db:
        profile = _profile(db, claims)
        branch = _require_branch(db, profile, branch_id)
        vehicles = list(db.scalars(select(Vehicle).where(Vehicle.branch_id == branch_id).order_by(Vehicle.registration_plate)))
        rows: list[list[Any]] = []
        for vehicle in vehicles:
            snapshot = evaluate_vehicle(db, vehicle)
            rows.append([
                vehicle.registration_plate,
                vehicle.make,
                vehicle.model,
                vehicle.vehicle_type,
                vehicle.current_mileage,
                snapshot["readiness"],
                snapshot["documents"]["overall"]["label"],
                snapshot["service"]["label"],
                snapshot["mechanical"]["label"],
                snapshot["inspection"]["label"],
                snapshot["availability"]["label"],
                snapshot["availability"].get("expected_available_at") or "",
            ])
        return _csv_response(
            f"nbros-{branch.code.lower()}-fleet.csv",
            ["Registration", "Make", "Model", "Vehicle Type", "Mileage", "Readiness", "Documents", "Service", "Mechanical", "Inspection", "Availability", "Expected Available"],
            rows,
        )


@router.get("/api/v1/operations/exports/tco.csv")
def export_tco(branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)):
    with SessionLocal() as db:
        profile = _profile(db, claims)
        branch = _require_branch(db, profile, branch_id)
        data = _tco_rows(db, branch_id)
        rows = [
            [
                row["registration_plate"], row["current_mileage"], row["known_cost"], row["cost_per_recorded_km"] or "",
                row["fuel"], row["service"], row["workshop_labour"], row["external_repairs"], row["tyres"], row["insurance_excess"],
            ]
            for row in data
        ]
        return _csv_response(
            f"nbros-{branch.code.lower()}-tco.csv",
            ["Registration", "Mileage", "Known Cost", "Cost per Recorded KM", "Fuel", "Service", "Workshop Labour", "External Repairs", "Tyres", "Insurance Excess"],
            rows,
        )


@router.get("/api/v1/operations/exports/audit.csv")
def export_audit(branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)):
    with SessionLocal() as db:
        profile = _profile(db, claims)
        branch = _require_branch(db, profile, branch_id)
        events = list(db.scalars(select(AuditEvent).where(AuditEvent.branch_id == branch_id).order_by(AuditEvent.created_at.desc()).limit(5000)))
        rows = [[event.created_at.isoformat(), str(event.actor_profile_id or ""), event.action, event.entity_type, event.entity_id or "", event.detail_json or ""] for event in events]
        return _csv_response(
            f"nbros-{branch.code.lower()}-audit.csv",
            ["Timestamp", "Actor Profile", "Action", "Entity Type", "Entity ID", "Detail JSON"],
            rows,
        )
