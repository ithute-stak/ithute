from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import CompanySetting, FleetAsset, FleetAssignment, FleetCompliance, FleetInspection, FleetMaintenancePlan
from app.security.access import Principal, current_principal

router = APIRouter(prefix="/fleet", tags=["Phase 4 - Fleet Control"])


def row_dict(row: Any) -> dict[str, Any]:
    result = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        result[column.name] = value.isoformat() if hasattr(value, "isoformat") else str(value) if isinstance(value, Decimal) else value
    return result


@router.get("/inspections")
def inspection_queue(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    rows = db.scalars(select(FleetInspection).where(FleetInspection.company_id == principal.user.company_id).order_by(FleetInspection.created_at.desc()).limit(500)).all()
    return [row_dict(row) for row in rows if principal.can("fleet.view", branch_id=row.branch_id, site_id=row.site_id) or principal.can("fleet.inspect.approve", branch_id=row.branch_id, site_id=row.site_id)]


@router.get("/assignments")
def assignment_queue(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    rows = db.scalars(select(FleetAssignment).where(FleetAssignment.company_id == principal.user.company_id).order_by(FleetAssignment.assigned_from.desc()).limit(500)).all()
    return [row_dict(row) for row in rows if principal.can("fleet.view", branch_id=row.branch_id, site_id=row.site_id) or principal.can("fleet.assign", branch_id=row.branch_id, site_id=row.site_id)]


@router.get("/compliance")
def compliance_register(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    rows = db.scalars(select(FleetCompliance).where(FleetCompliance.company_id == principal.user.company_id).order_by(FleetCompliance.expiry_date)).all()
    result = []
    for row in rows:
        asset = db.get(FleetAsset, row.asset_id)
        if asset and principal.can("fleet.view", branch_id=asset.branch_id, site_id=asset.site_id):
            item = row_dict(row); item["asset_number"] = asset.asset_number; result.append(item)
    return result


@router.get("/maintenance-plans")
def maintenance_plans(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    rows = db.scalars(select(FleetMaintenancePlan).where(FleetMaintenancePlan.company_id == principal.user.company_id).order_by(FleetMaintenancePlan.id.desc())).all()
    result = []
    for row in rows:
        asset = db.get(FleetAsset, row.asset_id)
        if asset and principal.can("fleet.view", branch_id=asset.branch_id, site_id=asset.site_id):
            item = row_dict(row); item["asset_number"] = asset.asset_number; result.append(item)
    return result


class FleetPolicyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    maintenance_due_warning_days: int = Field(default=14, ge=0, le=365)


def _policy_value(row: CompanySetting | None, *, can_edit: bool) -> dict[str, Any]:
    source = row.value if row and isinstance(row.value, dict) else {}
    return {
        "maintenance_due_warning_days": int(source.get("maintenance_due_warning_days", 14)),
        # Compliance reminders are stored per compliance record.
        # These are governance invariants, not user-disableable preferences.
        "require_maintenance_approval": True,
        "critical_defect_blocks_operation": True,
        "can_edit": can_edit,
    }


@router.get("/policy")
def get_policy(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if not principal.has_permission_anywhere("fleet.view") and not principal.has_permission_anywhere("fleet.manage"):
        raise HTTPException(status_code=403, detail="fleet.view is required")
    row = db.scalar(select(CompanySetting).where(CompanySetting.company_id == principal.user.company_id, CompanySetting.key == "fleet_policy"))
    return _policy_value(row, can_edit=principal.has_company_permission("fleet.manage"))


@router.put("/policy")
def set_policy(payload: FleetPolicyInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if not principal.has_company_permission("fleet.manage"):
        raise HTTPException(status_code=403, detail="Company-level fleet.manage is required")
    row = db.scalar(select(CompanySetting).where(CompanySetting.company_id == principal.user.company_id, CompanySetting.key == "fleet_policy"))
    existing = row.value if row and isinstance(row.value, dict) else {}
    value = {
        **existing,
        **payload.model_dump(),
        "require_maintenance_approval": True,
        "critical_defect_blocks_operation": True,
    }
    if row:
        row.value = value
    else:
        row = CompanySetting(company_id=principal.user.company_id, key="fleet_policy", value=value); db.add(row)
    db.commit()
    return {**_policy_value(row, can_edit=True)}
