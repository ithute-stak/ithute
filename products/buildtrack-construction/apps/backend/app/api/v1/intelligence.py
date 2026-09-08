from __future__ import annotations

import csv
import io
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.procurement import commit, money, row_dict
from app.api.v1.commercial import cost_actual_total, current_contract_sum, latest_budget, procurement_commitment, subcontract_commitment
from app.db.session import get_db
from app.models import (
    Branch, ClientInvoice, ClientContract, CompanySetting, FleetAsset, FleetFuelTransaction,
    FleetMaintenanceJob, Permission, Project, ProjectRisk, Role, RolePermission, StockBalance,
    StockItem, StoreLocation, Tender, TenderOutcome, TimesheetEntry,
)
from app.security.access import Principal, current_principal

router = APIRouter(prefix="/intelligence", tags=["Phase 12 - Management Intelligence"])

PERMISSIONS = {
    "intelligence.view": ("intelligence", "view", "View management intelligence and operational exceptions"),
    "intelligence.export": ("intelligence", "export", "Export management intelligence reports"),
}


def require_anywhere(principal: Principal, permission: str) -> None:
    if not principal.has_permission_anywhere(permission):
        raise HTTPException(status_code=403, detail=f"Permission required: {permission}")


def allowed_projects(db: Session, principal: Principal) -> list[Project]:
    return [row for row in db.scalars(select(Project).where(Project.company_id == principal.user.company_id)).all() if principal.can("intelligence.view", branch_id=row.branch_id, site_id=row.primary_site_id)]


def bootstrap_permissions(db: Session, company_id: int) -> None:
    permissions: dict[str, Permission] = {}
    for code, (module, action, description) in PERMISSIONS.items():
        row = db.scalar(select(Permission).where(Permission.code == code))
        if not row:
            row = Permission(code=code, module=module, action=action, description=description); db.add(row); db.flush()
        permissions[code] = row
    roles = {row.code: row for row in db.scalars(select(Role).where(Role.company_id == company_id)).all()}
    if "DIRECTOR" not in roles:
        row = Role(company_id=company_id, code="DIRECTOR", name="Director", scope_level="company", description="Phase 12 company and branch intelligence", is_system=True, is_active=True); db.add(row); db.flush(); roles["DIRECTOR"] = row
    grants = {"SYSTEM_ADMIN": set(PERMISSIONS), "HQ_EXECUTIVE": set(PERMISSIONS), "DIRECTOR": set(PERMISSIONS), "BRANCH_MANAGER": {"intelligence.view"}, "PROJECT_MANAGER": {"intelligence.view"}, "AUDITOR": set(PERMISSIONS)}
    for role_code, codes in grants.items():
        role = roles.get(role_code)
        if not role: continue
        existing = set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id == role.id)).all())
        for code in codes:
            if permissions[code].id not in existing: db.add(RolePermission(role_id=role.id, permission_id=permissions[code].id)); existing.add(permissions[code].id)
    if not db.scalar(select(CompanySetting).where(CompanySetting.company_id == company_id, CompanySetting.key == "intelligence_policy")):
        db.add(CompanySetting(company_id=company_id, key="intelligence_policy", value={"project_health_margin_warning": 0, "stock_coverage_warning_days": 14}, description="Phase 12 management-intelligence thresholds"))


def project_health(db: Session, project: Project) -> dict[str, Any]:
    contract = db.scalar(select(ClientContract).where(ClientContract.project_id == project.id))
    budget = latest_budget(db, project); actual = cost_actual_total(db, project.id); po = procurement_commitment(db, project.id); subcontract = subcontract_commitment(db, project.id); exposure = money(actual + po + subcontract); revenue = current_contract_sum(db, contract) if contract else money(project.contract_amount)
    critical_risks = db.scalar(select(func.count()).select_from(ProjectRisk).where(ProjectRisk.project_id == project.id, ProjectRisk.status.in_(("open", "mitigating")), ProjectRisk.rating >= 16)) or 0
    days_remaining = (project.contract_completion_date - date.today()).days
    status = "healthy"
    if critical_risks or (budget > 0 and exposure > budget) or days_remaining < 0: status = "critical"
    elif (budget > 0 and exposure > budget * Decimal("0.9")) or days_remaining <= 30: status = "watch"
    return {"project_id": project.id, "project_number": project.project_number, "name": project.name, "branch_id": project.branch_id, "site_id": project.primary_site_id, "status": status, "budget": str(budget), "actual_cost": str(actual), "commitments": str(money(po + subcontract)), "exposure": str(exposure), "revenue": str(revenue), "forecast_margin": str(money(revenue - exposure)), "critical_risks": critical_risks, "completion_date": project.contract_completion_date.isoformat(), "days_remaining": days_remaining}


@router.post("/bootstrap")
def bootstrap(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if not principal.has_company_permission("company.manage") and not principal.has_company_permission("intelligence.view"):
        raise HTTPException(status_code=403, detail="Company-level administration is required to initialise Management Intelligence")
    bootstrap_permissions(db, principal.user.company_id); commit(db)
    return {"phase": 12, "status": "ready", "message": "Director, branch and project intelligence controls are ready."}


@router.get("/director-dashboard")
def director_dashboard(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_anywhere(principal, "intelligence.view")
    projects = allowed_projects(db, principal); health = [project_health(db, row) for row in projects]
    invoices = [row for row in db.scalars(select(ClientInvoice).where(ClientInvoice.company_id == principal.user.company_id)).all() if (contract := db.get(ClientContract, row.contract_id)) and principal.can("intelligence.view", branch_id=contract.branch_id, site_id=contract.site_id)]
    return {"currency": "LSL", "projects": len(projects), "project_health": {"healthy": sum(row["status"] == "healthy" for row in health), "watch": sum(row["status"] == "watch" for row in health), "critical": sum(row["status"] == "critical" for row in health)}, "portfolio_revenue": str(money(sum((Decimal(row["revenue"]) for row in health), Decimal("0")))), "portfolio_exposure": str(money(sum((Decimal(row["exposure"]) for row in health), Decimal("0")))), "portfolio_forecast_margin": str(money(sum((Decimal(row["forecast_margin"]) for row in health), Decimal("0")))), "client_receivable": str(money(sum((Decimal(row.net_amount) - Decimal(row.paid_amount) for row in invoices if row.status in {"issued", "part_paid"}), Decimal("0")))), "tender_pipeline": tender_pipeline(db, principal), "fleet": fleet_performance(db, principal), "materials": materials(db, principal)}


@router.get("/branches")
def branches(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    require_anywhere(principal, "intelligence.view")
    result: list[dict[str, Any]] = []
    for branch in db.scalars(select(Branch).where(Branch.company_id == principal.user.company_id, Branch.is_active.is_(True)).order_by(Branch.name)).all():
        rows = [row for row in allowed_projects(db, principal) if row.branch_id == branch.id]
        if not rows: continue
        health = [project_health(db, row) for row in rows]
        result.append({"branch_id": branch.id, "code": branch.code, "name": branch.name, "projects": len(rows), "revenue": str(money(sum((Decimal(row["revenue"]) for row in health), Decimal("0")))), "exposure": str(money(sum((Decimal(row["exposure"]) for row in health), Decimal("0")))), "forecast_margin": str(money(sum((Decimal(row["forecast_margin"]) for row in health), Decimal("0")))), "critical_projects": sum(row["status"] == "critical" for row in health)})
    return result


@router.get("/projects/health")
def projects_health(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    require_anywhere(principal, "intelligence.view")
    return sorted((project_health(db, row) for row in allowed_projects(db, principal)), key=lambda row: (row["status"] != "critical", row["days_remaining"]))


def tender_pipeline(db: Session, principal: Principal) -> dict[str, Any]:
    rows = [row for row in db.scalars(select(Tender).where(Tender.company_id == principal.user.company_id)).all() if principal.can("intelligence.view", branch_id=row.branch_id, site_id=row.site_id)]
    outcomes = {row.tender_id: row for row in db.scalars(select(TenderOutcome).where(TenderOutcome.company_id == principal.user.company_id)).all()}
    return {"open": sum(row.status not in {"lost", "withdrawn", "awarded"} for row in rows), "awarded": sum(row.status == "awarded" for row in rows), "won_value": str(money(sum((Decimal(row.estimated_contract_value or 0) for row in rows if row.status == "awarded"), Decimal("0")))), "lost": sum((outcomes.get(row.id).outcome == "lost") for row in rows if outcomes.get(row.id)), "closing_next_30_days": sum(0 <= (row.submission_deadline.date() - date.today()).days <= 30 for row in rows)}


@router.get("/tender-pipeline")
def tender_pipeline_endpoint(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_anywhere(principal, "intelligence.view"); return tender_pipeline(db, principal)


def fleet_performance(db: Session, principal: Principal) -> dict[str, Any]:
    assets = [row for row in db.scalars(select(FleetAsset).where(FleetAsset.company_id == principal.user.company_id)).all() if principal.can("intelligence.view", branch_id=row.branch_id, site_id=row.site_id)]
    asset_ids = {row.id for row in assets}; fuel = [row for row in db.scalars(select(FleetFuelTransaction).where(FleetFuelTransaction.company_id == principal.user.company_id)).all() if row.asset_id in asset_ids]; jobs = [row for row in db.scalars(select(FleetMaintenanceJob).where(FleetMaintenanceJob.company_id == principal.user.company_id)).all() if row.asset_id in asset_ids]
    return {"assets": len(assets), "serviceable": sum(row.serviceability == "serviceable" for row in assets), "unserviceable": sum(row.serviceability != "serviceable" for row in assets), "fuel_cost": str(money(sum((Decimal(row.total_cost) for row in fuel), Decimal("0")))), "fuel_litres": str(sum((Decimal(row.litres) for row in fuel), Decimal("0"))), "maintenance_cost": str(money(sum((Decimal(row.total_cost) for row in jobs if row.status == "completed"), Decimal("0")))), "open_maintenance": sum(row.status not in {"completed", "cancelled"} for row in jobs)}


@router.get("/fleet-performance")
def fleet_performance_endpoint(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_anywhere(principal, "intelligence.view"); return fleet_performance(db, principal)


def materials(db: Session, principal: Principal) -> dict[str, Any]:
    balances = db.scalars(select(StockBalance).where(StockBalance.company_id == principal.user.company_id)).all(); low: list[dict[str, Any]] = []; value = Decimal("0")
    for balance in balances:
        location, item = db.get(StoreLocation, balance.location_id), db.get(StockItem, balance.stock_item_id)
        if not location or not item or not principal.can("intelligence.view", branch_id=location.branch_id, site_id=location.site_id): continue
        quantity = Decimal(balance.quantity_on_hand) - Decimal(balance.quantity_reserved); value += Decimal(balance.quantity_on_hand) * Decimal(balance.average_unit_cost)
        if item.stock_controlled and quantity <= Decimal(item.reorder_level): low.append({"stock_item_id": item.id, "sku": item.sku, "description": item.description, "location": location.name, "available": str(quantity), "reorder_level": str(item.reorder_level)})
    return {"stock_value": str(money(value)), "low_stock_count": len(low), "low_stock": low}


@router.get("/materials")
def materials_endpoint(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_anywhere(principal, "intelligence.view"); return materials(db, principal)


@router.get("/exceptions")
def exceptions(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    require_anywhere(principal, "intelligence.view"); result: list[dict[str, Any]] = []
    for row in projects_health(db, principal):
        if row["status"] != "healthy": result.append({"category": "project_health", "severity": row["status"], "reference": row["project_number"], "message": f"Exposure {row['exposure']} against budget {row['budget']}; {row['critical_risks']} critical risks"})
    for row in materials(db, principal)["low_stock"]: result.append({"category": "materials", "severity": "warning", "reference": row["sku"], "message": f"{row['description']} available {row['available']} at {row['location']}"})
    fleet = fleet_performance(db, principal)
    if fleet["unserviceable"]: result.append({"category": "fleet", "severity": "critical", "reference": "fleet", "message": f"{fleet['unserviceable']} assets are not serviceable"})
    return result


@router.get("/exports/portfolio.csv")
def export_portfolio(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> StreamingResponse:
    require_anywhere(principal, "intelligence.export"); output = io.StringIO(); writer = csv.writer(output); writer.writerow(["Project", "Status", "Budget", "Actual", "Commitments", "Exposure", "Revenue", "Forecast Margin", "Critical Risks", "Completion"])
    for row in projects_health(db, principal): writer.writerow([row["project_number"], row["status"], row["budget"], row["actual_cost"], row["commitments"], row["exposure"], row["revenue"], row["forecast_margin"], row["critical_risks"], row["completion_date"]])
    return StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=buildtrack-portfolio-intelligence.csv"})
