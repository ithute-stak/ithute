from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Employee, FleetAsset, Permission, Role, RolePermission
from app.security.access import Principal, build_principal, current_principal


ROLE_PERMISSION_REQUIREMENTS: dict[str, set[str]] = {
    "SYSTEM_ADMIN": {"fleet.view", "fleet.manage", "fleet.assign", "fleet.inspect", "fleet.inspect.approve", "fleet.fuel", "fleet.maintenance", "fleet.approve", "fleet.costs", "fleet.export"},
    "HQ_EXECUTIVE": {"fleet.view", "fleet.inspect.approve", "fleet.approve", "fleet.costs", "fleet.export"},
    "BRANCH_MANAGER": {"fleet.view", "fleet.assign", "fleet.inspect", "fleet.inspect.approve", "fleet.fuel", "fleet.maintenance", "fleet.costs"},
    "SITE_MANAGER": {"fleet.view", "fleet.assign", "fleet.inspect", "fleet.fuel", "fleet.maintenance"},
    "APPROVER": {"fleet.inspect.approve", "fleet.approve"},
    "AUDITOR": {"fleet.view", "fleet.costs", "fleet.export"},
    "FLEET_MANAGER": {"fleet.view", "fleet.manage", "fleet.assign", "fleet.inspect", "fleet.inspect.approve", "fleet.fuel", "fleet.maintenance", "fleet.approve", "fleet.costs", "fleet.export"},
    "FLEET_OFFICER": {"fleet.view", "fleet.manage", "fleet.assign", "fleet.inspect", "fleet.fuel", "fleet.maintenance", "fleet.costs", "fleet.export"},
    "FLEET_INSPECTOR": {"fleet.view", "fleet.inspect"},
}


def _asset_id_from_path(path: str) -> int | None:
    if "/fleet/assets/" not in path:
        return None
    try:
        return int(path.split("/fleet/assets/", 1)[1].split("/", 1)[0])
    except (ValueError, IndexError):
        return None


def _validate_employee_scope(db: Session, company_id: int, employee_id: int | None, branch_id: int, site_id: int | None, *, label: str) -> None:
    if employee_id is None:
        return
    employee = db.get(Employee, int(employee_id))
    if not employee or employee.company_id != company_id or employee.employment_status not in {"active", "on_leave"}:
        raise HTTPException(status_code=422, detail=f"{label} is not an active employee of this company")
    if employee.branch_id != int(branch_id):
        raise HTTPException(status_code=422, detail=f"{label} must belong to the asset/assignment branch")
    if site_id is not None and employee.site_id is not None and employee.site_id != int(site_id):
        raise HTTPException(status_code=422, detail=f"{label} is assigned to a different site")


async def reconcile_fleet_access(request: Request, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> Principal:
    """Keep Phase 4 system-role permissions and cross-module scope boundaries consistent."""
    if not db.scalar(select(Permission.id).where(Permission.code == "fleet.manage")):
        return principal

    company_id = principal.user.company_id
    permissions = {row.code: row for row in db.scalars(select(Permission)).all()}
    roles = {row.code: row for row in db.scalars(select(Role).where(Role.company_id == company_id)).all()}
    changed = False
    for role_code, required_codes in ROLE_PERMISSION_REQUIREMENTS.items():
        role = roles.get(role_code)
        if not role:
            continue
        existing = set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id == role.id)).all())
        for code in required_codes:
            permission = permissions.get(code)
            if permission and permission.id not in existing:
                db.add(RolePermission(role_id=role.id, permission_id=permission.id))
                existing.add(permission.id)
                changed = True

    method = request.method.upper()
    path = request.url.path
    payload: dict = {}
    if method in {"POST", "PUT", "PATCH"}:
        try:
            parsed = await request.json()
            payload = parsed if isinstance(parsed, dict) else {}
        except Exception:
            payload = {}

    asset_id = _asset_id_from_path(path)
    asset = db.get(FleetAsset, asset_id) if asset_id else None
    if asset is not None and asset.company_id != company_id:
        asset = None

    if method == "POST" and path.endswith("/assignments") and asset is not None:
        branch_id = int(payload.get("branch_id") or asset.branch_id)
        site_id = int(payload["site_id"]) if payload.get("site_id") is not None else None
        _validate_employee_scope(db, company_id, payload.get("employee_id"), branch_id, site_id, label="Operator/driver")

    if method == "POST" and path.endswith("/fuel") and asset is not None:
        _validate_employee_scope(db, company_id, payload.get("employee_id"), asset.branch_id, asset.site_id, label="Fuel operator/driver")

    if method == "POST" and path.endswith("/inspections") and asset is not None:
        _validate_employee_scope(db, company_id, payload.get("inspector_employee_id"), asset.branch_id, asset.site_id, label="Inspector")

    if method == "POST" and path.endswith("/status") and asset is not None:
        requested_status = payload.get("status")
        requested_serviceability = payload.get("serviceability", asset.serviceability)
        if requested_status == "active" and requested_serviceability == "unserviceable":
            raise HTTPException(status_code=422, detail="An unserviceable asset cannot be placed into active service")
        if requested_status in {"out_of_service", "disposed"} and requested_serviceability == "serviceable":
            raise HTTPException(status_code=422, detail="Out-of-service or disposed assets cannot be marked serviceable")

    if changed:
        db.commit()
    refreshed = build_principal(db, principal.user, principal.session)
    request.state.principal = refreshed
    return refreshed
