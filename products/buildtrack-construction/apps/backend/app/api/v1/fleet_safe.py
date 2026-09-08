from __future__ import annotations

import csv
import io
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Branch, CostCentre, Employee, FleetAsset, FleetCompliance, FleetFuelTransaction, FleetMaintenanceJob, Site
from app.security.access import Principal, current_principal

router = APIRouter(prefix="/fleet", tags=["Phase 4 - Fleet & Plant"])
MONEY = Decimal("0.01")


def money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def row_dict(row: Any) -> dict[str, Any]:
    result = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        result[column.name] = value.isoformat() if hasattr(value, "isoformat") else (str(value) if isinstance(value, Decimal) else value)
    return result


@router.get("/catalog")
def scoped_catalog(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if not principal.has_permission_anywhere("fleet.view") and not principal.has_permission_anywhere("fleet.manage"):
        raise HTTPException(status_code=403, detail="fleet.view is required")
    company_id = principal.user.company_id
    branches = []
    for branch in db.scalars(select(Branch).where(Branch.company_id == company_id, Branch.is_active.is_(True)).order_by(Branch.name)).all():
        if principal.can("fleet.view", branch_id=branch.id) or principal.can("fleet.manage", branch_id=branch.id):
            branches.append(row_dict(branch))
    visible_branch_ids = {int(row["id"]) for row in branches}
    sites = []
    for site in db.scalars(select(Site).where(Site.company_id == company_id, Site.is_active.is_(True)).order_by(Site.name)).all():
        if site.branch_id in visible_branch_ids and (principal.can("fleet.view", branch_id=site.branch_id, site_id=site.id) or principal.can("fleet.manage", branch_id=site.branch_id, site_id=site.id)):
            sites.append(row_dict(site))
    employees = []
    for employee in db.scalars(select(Employee).where(Employee.company_id == company_id, Employee.employment_status.in_(["active", "on_leave"])).order_by(Employee.first_name, Employee.last_name)).all():
        if principal.can("fleet.view", branch_id=employee.branch_id, site_id=employee.site_id) or principal.can("fleet.assign", branch_id=employee.branch_id, site_id=employee.site_id):
            employees.append({"id": employee.id, "employee_number": employee.employee_number, "full_name": " ".join(filter(None, [employee.first_name, employee.middle_names, employee.last_name])), "branch_id": employee.branch_id, "site_id": employee.site_id, "job_title": employee.job_title})
    cost_centres = []
    for centre in db.scalars(select(CostCentre).where(CostCentre.company_id == company_id, CostCentre.is_active.is_(True)).order_by(CostCentre.code)).all():
        if centre.branch_id is None or centre.branch_id in visible_branch_ids:
            cost_centres.append(row_dict(centre))
    permissions = sorted(code for code in principal.permission_codes if code.startswith("fleet."))
    return {"branches": branches, "sites": sites, "cost_centres": cost_centres, "employees": employees, "permissions": permissions, "asset_types": ["vehicle", "truck", "bus", "light_plant", "heavy_plant", "generator", "trailer", "equipment", "other"]}


def scoped_cost_rows(db: Session, principal: Principal) -> list[dict[str, Any]]:
    if not principal.has_permission_anywhere("fleet.costs"):
        raise HTTPException(status_code=403, detail="fleet.costs is required")
    result = []
    for asset in db.scalars(select(FleetAsset).where(FleetAsset.company_id == principal.user.company_id).order_by(FleetAsset.asset_number)).all():
        if not principal.can("fleet.costs", branch_id=asset.branch_id, site_id=asset.site_id):
            continue
        fuel = db.scalar(select(func.coalesce(func.sum(FleetFuelTransaction.total_cost), 0)).where(FleetFuelTransaction.asset_id == asset.id)) or 0
        maintenance = db.scalar(select(func.coalesce(func.sum(FleetMaintenanceJob.total_cost), 0)).where(FleetMaintenanceJob.asset_id == asset.id, FleetMaintenanceJob.status == "completed")) or 0
        compliance = db.scalar(select(func.coalesce(func.sum(FleetCompliance.cost), 0)).where(FleetCompliance.asset_id == asset.id)) or 0
        total = Decimal(fuel) + Decimal(maintenance) + Decimal(compliance)
        result.append({"asset_id": asset.id, "asset_number": asset.asset_number, "registration_number": asset.registration_number, "branch_id": asset.branch_id, "fuel_cost": str(money(fuel)), "maintenance_cost": str(money(maintenance)), "compliance_cost": str(money(compliance)), "total_cost": str(money(total))})
    return result


@router.get("/costs")
def scoped_costs(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    return scoped_cost_rows(db, principal)


@router.get("/export.csv")
def scoped_export(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> StreamingResponse:
    if not principal.has_permission_anywhere("fleet.export"):
        raise HTTPException(status_code=403, detail="fleet.export is required")
    cost_map = {row["asset_id"]: row for row in scoped_cost_rows(db, principal)} if principal.has_permission_anywhere("fleet.costs") else {}
    output = io.StringIO(); writer = csv.writer(output)
    writer.writerow(["Asset Number", "Type", "Registration", "Make", "Model", "Branch ID", "Site ID", "Status", "Serviceability", "Odometer km", "Engine hours", "Fuel cost", "Maintenance cost", "Compliance cost", "Total cost"])
    for asset in db.scalars(select(FleetAsset).where(FleetAsset.company_id == principal.user.company_id).order_by(FleetAsset.asset_number)).all():
        if not principal.can("fleet.export", branch_id=asset.branch_id, site_id=asset.site_id):
            continue
        c = cost_map.get(asset.id, {})
        writer.writerow([asset.asset_number, asset.asset_type, asset.registration_number or "", asset.make, asset.model, asset.branch_id, asset.site_id or "", asset.status, asset.serviceability, asset.current_odometer_km, asset.current_engine_hours, c.get("fuel_cost", ""), c.get("maintenance_cost", ""), c.get("compliance_cost", ""), c.get("total_cost", "")])
    return StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=buildtrack-fleet-register.csv"})
