from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_tenant_permission
from app.db.session import get_db
from app.models import EdgeApplication, EdgeInspection, EdgeOrigin, EdgeRouteDeployment, User
from app.services.caddy_routes import CaddyRouteError, activate_route, deactivate_route, propagation_state
from app.services.edge_inspection import EdgeInspectionError, inspect_public_origin
from app.services.hosting_edge_handoff import HostingOriginError, inspect_trusted_origin

router = APIRouter(prefix="/tenants/{tenant_id}/edge", tags=["edge-routes"])


def _app(db: Session, tenant_id: UUID, app_id: UUID) -> EdgeApplication:
    row = db.scalar(select(EdgeApplication).where(EdgeApplication.id == app_id, EdgeApplication.tenant_id == tenant_id))
    if row is None:
        raise HTTPException(404, "Edge application not found")
    return row


def _deployment(db: Session, app_id: UUID) -> EdgeRouteDeployment:
    row = db.scalar(select(EdgeRouteDeployment).where(EdgeRouteDeployment.application_id == app_id))
    if row is None:
        row = EdgeRouteDeployment(application_id=app_id)
        db.add(row)
        db.flush()
    return row


def _out(row: EdgeRouteDeployment, app: EdgeApplication) -> dict:
    return {
        "id": str(row.id),
        "application_id": str(app.id),
        "hostname": app.hostname,
        "status": row.status,
        "expected_ips": json.loads(row.expected_ips_json or "[]"),
        "observed_ips": json.loads(row.observed_ips_json or "[]"),
        "caddy_revision": row.caddy_revision,
        "last_checked_at": row.last_checked_at.isoformat() if row.last_checked_at else None,
        "activated_at": row.activated_at.isoformat() if row.activated_at else None,
        "error": row.error,
    }


@router.get("/applications/{app_id}/route")
def route_status(
    tenant_id: UUID,
    app_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "dns.read", db, current)
    app = _app(db, tenant_id, app_id)
    row = _deployment(db, app.id)
    db.commit(); db.refresh(row)
    return _out(row, app)


@router.post("/applications/{app_id}/route/reconcile")
def reconcile_route(
    tenant_id: UUID,
    app_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    app = _app(db, tenant_id, app_id)
    row = _deployment(db, app.id)
    now = datetime.now(timezone.utc)
    row.last_checked_at = now
    row.error = None

    if not app.enabled:
        row.status = "disabled"
        try:
            deactivate_route(str(app.id))
        except CaddyRouteError as exc:
            row.status = "error"; row.error = str(exc)
        db.commit(); db.refresh(row)
        return _out(row, app)

    if app.mode != "protected":
        row.status = "pending_mode"
        row.error = "Set edge mode to protected before activating Caddy routing."
        db.commit(); db.refresh(row)
        return _out(row, app)

    try:
        propagation = propagation_state(app.hostname)
    except CaddyRouteError as exc:
        row.status = "error"; row.error = str(exc)
        db.commit(); db.refresh(row)
        return _out(row, app)

    row.expected_ips_json = json.dumps(propagation["expected_ips"])
    row.observed_ips_json = json.dumps(propagation["observed_ips"])
    if not propagation["propagated"]:
        row.status = "pending_dns"
        row.error = "DNS has not propagated to an Ithute edge IP yet."
        db.commit(); db.refresh(row)
        return _out(row, app)

    origin = db.scalar(
        select(EdgeOrigin)
        .where(EdgeOrigin.application_id == app.id, EdgeOrigin.enabled.is_(True))
        .order_by(EdgeOrigin.failover_priority, EdgeOrigin.name)
        .limit(1)
    )
    if origin is None:
        row.status = "pending_origin"; row.error = "Add an enabled origin before activating the route."
        db.commit(); db.refresh(row)
        return _out(row, app)

    try:
        if origin.name == "ithute-hosting":
            inspection = inspect_trusted_origin(origin.url, origin.health_path, origin.expected_status, origin.timeout_seconds)
            inspection = {
                **inspection,
                "resolved_ip": origin.url.split("//", 1)[-1].split(":", 1)[0],
                "tls_version": None,
                "cipher": None,
                "certificate_issuer": None,
                "certificate_not_after": None,
                "certificate_days_remaining": None,
            }
        else:
            inspection = inspect_public_origin(origin.url, origin.health_path, origin.expected_status, origin.timeout_seconds)
    except (EdgeInspectionError, HostingOriginError) as exc:
        row.status = "pending_origin"; row.error = str(exc)
        db.commit(); db.refresh(row)
        return _out(row, app)

    db.add(EdgeInspection(
        application_id=app.id,
        origin_id=origin.id,
        healthy=inspection["healthy"],
        resolved_ip=inspection["resolved_ip"],
        status_code=inspection["status_code"],
        latency_ms=inspection["latency_ms"],
        tls_version=inspection["tls_version"],
        cipher=inspection["cipher"],
        certificate_issuer=inspection["certificate_issuer"],
        certificate_not_after=inspection["certificate_not_after"],
        certificate_days_remaining=inspection["certificate_days_remaining"],
        error=inspection["error"],
    ))
    if not inspection["healthy"]:
        row.status = "pending_origin"
        row.error = inspection["error"] or f"Origin returned HTTP {inspection['status_code']} instead of {origin.expected_status}."
        db.commit(); db.refresh(row)
        return _out(row, app)

    try:
        activate_route(str(app.id), app.hostname, origin.url)
    except CaddyRouteError as exc:
        row.status = "error"; row.error = str(exc)
        db.commit(); db.refresh(row)
        return _out(row, app)

    row.status = "active"
    row.caddy_revision += 1
    row.activated_at = now
    row.error = None
    db.commit(); db.refresh(row)
    return _out(row, app)


@router.delete("/applications/{app_id}/route")
def remove_route(
    tenant_id: UUID,
    app_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    app = _app(db, tenant_id, app_id)
    row = _deployment(db, app.id)
    try:
        deactivate_route(str(app.id))
    except CaddyRouteError as exc:
        row.status = "error"; row.error = str(exc)
        db.commit(); db.refresh(row)
        raise HTTPException(502, str(exc)) from exc
    row.status = "disabled"; row.error = None
    db.commit(); db.refresh(row)
    return _out(row, app)
