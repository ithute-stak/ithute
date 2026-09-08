from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.procurement import allow_self_approval, assignment_authorised, commit, ensure_document, issue_reference, row_dict, utcnow
from app.db.session import get_db
from app.models import (
    ApprovalAction, ApprovalRequest, ApprovalStep, ApprovalWorkflow, CompanySetting, Employee, FleetAsset,
    NumberSequence, Permission, ProgrammeActivity, ProgrammeBaseline, Project, ProjectAssetAllocation,
    ResourceAuditEvent, ResourcePlan, ResourcePlanItem, ResourceRequest, Role, RolePermission, StockItem,
)
from app.security.access import Principal, current_principal


router = APIRouter(prefix="/resources", tags=["Phase 20 - Resource Planning & Capacity Control"])

PERMISSIONS = {
    "resources.view": ("resources", "view", "View resource plans, capacity, requests and exceptions"),
    "resources.manage": ("resources", "manage", "Prepare resource plans, forecast lines and resource requests"),
    "resources.approve": ("resources", "approve", "Independently approve resource plans and requests"),
    "resources.fulfill": ("resources", "fulfill", "Record supplied resource fulfilment evidence after approval"),
    "resources.export": ("resources", "export", "Export controlled resource planning registers"),
}

POLICY_DEFAULT = {"require_plan_evidence": True, "require_request_evidence": True, "require_fulfilment_evidence": True, "capacity_limit_pct": 100}


def anywhere(principal: Principal, permission: str) -> None:
    if not principal.has_permission_anywhere(permission):
        raise HTTPException(status_code=403, detail=f"Permission required: {permission}")


def scope(principal: Principal, permission: str, branch_id: int, site_id: int | None = None) -> None:
    if not principal.can(permission, branch_id=branch_id, site_id=site_id):
        raise HTTPException(status_code=403, detail=f"Permission required in this branch/site: {permission}")


def policy(db: Session, company_id: int) -> dict[str, Any]:
    row = db.scalar(select(CompanySetting).where(CompanySetting.company_id == company_id, CompanySetting.key == "resource_policy"))
    return {**POLICY_DEFAULT, **(row.value if row and isinstance(row.value, dict) else {})}


def audit(db: Session, principal: Principal, action: str, entity: Any, *, branch_id: int | None, site_id: int | None, project_id: int | None, detail: dict[str, Any] | None = None) -> None:
    db.add(ResourceAuditEvent(company_id=principal.user.company_id, branch_id=branch_id, site_id=site_id, project_id=project_id, actor=principal.user.full_name, action=action, entity_type=entity.__tablename__, entity_id=str(entity.id), detail=detail or {}))


def project_or_404(db: Session, principal: Principal, project_id: int, permission: str = "resources.view") -> Project:
    row = db.get(Project, project_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Project not found")
    scope(principal, permission, row.branch_id, row.primary_site_id)
    return row


def plan_or_404(db: Session, principal: Principal, plan_id: int, permission: str = "resources.view") -> ResourcePlan:
    row = db.get(ResourcePlan, plan_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Resource plan not found")
    scope(principal, permission, row.branch_id, row.site_id)
    return row


def item_or_404(db: Session, principal: Principal, item_id: int, permission: str = "resources.view") -> ResourcePlanItem:
    row = db.get(ResourcePlanItem, item_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Resource plan item not found")
    scope(principal, permission, row.branch_id, row.site_id)
    return row


def request_or_404(db: Session, principal: Principal, request_id: int, permission: str = "resources.view") -> ResourceRequest:
    row = db.get(ResourceRequest, request_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Resource request not found")
    scope(principal, permission, row.branch_id, row.site_id)
    return row


def ensure_plan_editable(row: ResourcePlan) -> None:
    if row.status not in {"draft", "rejected"}:
        raise HTTPException(status_code=409, detail="Resource plan is frozen while approval is active or after approval")


def date_overlap(left_start: date, left_finish: date, right_start: date, right_finish: date | None) -> bool:
    return left_start <= (right_finish or date.max) and right_start <= left_finish


def plan_conflicts(db: Session, plan: ResourcePlan) -> list[dict[str, Any]]:
    config = policy(db, plan.company_id)
    cap = Decimal(str(config["capacity_limit_pct"]))
    items = db.scalars(select(ResourcePlanItem).where(ResourcePlanItem.plan_id == plan.id)).all()
    all_items = db.scalars(select(ResourcePlanItem).where(ResourcePlanItem.company_id == plan.company_id)).all()
    statuses = {row.id: row.status for row in db.scalars(select(ResourcePlan).where(ResourcePlan.company_id == plan.company_id)).all()}
    result: list[dict[str, Any]] = []
    for item in items:
        resource_key = ("employee", item.employee_id) if item.employee_id else (("asset", item.asset_id) if item.asset_id else None)
        if not resource_key:
            continue
        overlapping = [other for other in all_items if other.id != item.id and ((other.employee_id and resource_key == ("employee", other.employee_id)) or (other.asset_id and resource_key == ("asset", other.asset_id))) and (other.plan_id == plan.id or statuses.get(other.plan_id) in {"submitted", "approved"}) and date_overlap(item.planned_from, item.planned_to, other.planned_from, other.planned_to)]
        total = Decimal(item.allocation_pct) + sum((Decimal(other.allocation_pct) for other in overlapping), Decimal("0"))
        if total > cap:
            result.append({"kind": f"{resource_key[0]}_capacity", "resource_id": resource_key[1], "item_id": item.id, "allocation_pct": str(total), "limit_pct": str(cap), "message": f"{resource_key[0].title()} allocation exceeds {cap}% across overlapping resource plans"})
        if item.asset_id:
            allocations = db.scalars(select(ProjectAssetAllocation).where(ProjectAssetAllocation.asset_id == item.asset_id, ProjectAssetAllocation.status.in_(("planned", "confirmed")), ProjectAssetAllocation.project_id != plan.project_id)).all()
            for allocation in allocations:
                if date_overlap(item.planned_from, item.planned_to, allocation.planned_from, allocation.planned_to):
                    result.append({"kind": "asset_project_allocation", "resource_id": item.asset_id, "item_id": item.id, "allocation_id": allocation.id, "message": "Asset has an overlapping Phase 6 project allocation"})
    return result


def plan_payload(db: Session, row: ResourcePlan, include_items: bool = False) -> dict[str, Any]:
    payload = row_dict(row)
    project = db.get(Project, row.project_id)
    items = db.scalars(select(ResourcePlanItem).where(ResourcePlanItem.plan_id == row.id).order_by(ResourcePlanItem.line_number)).all()
    payload.update({"project_number": project.project_number if project else "", "project_name": project.name if project else "", "item_count": len(items), "employee_count": sum(item.employee_id is not None for item in items), "asset_count": sum(item.asset_id is not None for item in items), "material_count": sum(item.stock_item_id is not None for item in items), "conflict_count": len(plan_conflicts(db, row))})
    if include_items:
        records: list[dict[str, Any]] = []
        for item in items:
            record = row_dict(item)
            employee = db.get(Employee, item.employee_id) if item.employee_id else None
            asset = db.get(FleetAsset, item.asset_id) if item.asset_id else None
            stock = db.get(StockItem, item.stock_item_id) if item.stock_item_id else None
            activity = db.get(ProgrammeActivity, item.activity_id) if item.activity_id else None
            record.update({"employee_name": f"{employee.first_name} {employee.last_name}" if employee else "", "asset_number": asset.asset_number if asset else "", "stock_sku": stock.sku if stock else "", "stock_description": stock.description if stock else "", "activity_name": activity.name if activity else ""})
            records.append(record)
        payload["items"] = records
        payload["conflicts"] = plan_conflicts(db, row)
    return payload


def workflow(db: Session, company_id: int, code: str) -> ApprovalWorkflow:
    row = db.scalar(select(ApprovalWorkflow).where(ApprovalWorkflow.company_id == company_id, ApprovalWorkflow.code == code, ApprovalWorkflow.is_active.is_(True)))
    if not row or not db.scalar(select(func.count()).select_from(ApprovalStep).where(ApprovalStep.workflow_id == row.id)):
        raise HTTPException(status_code=409, detail=f"Resource approval workflow {code} is not configured")
    return row


def approval_request(db: Session, principal: Principal, *, code: str, entity_type: str, entity_id: int, title: str, branch_id: int, site_id: int | None) -> ApprovalRequest:
    selected = workflow(db, principal.user.company_id, code)
    row = ApprovalRequest(company_id=principal.user.company_id, workflow_id=selected.id, branch_id=branch_id, site_id=site_id, entity_type=entity_type, entity_id=str(entity_id), reference=issue_reference(db, principal.user.company_id, "RESOURCE_APPROVAL", "RAP"), title=title, amount=Decimal("0"), status="pending", current_step_order=1, requested_by=principal.user.full_name)
    db.add(row)
    db.flush()
    return row


def bootstrap_data(db: Session, company_id: int) -> None:
    permissions: dict[str, Permission] = {}
    for code, (module, action, description) in PERMISSIONS.items():
        row = db.scalar(select(Permission).where(Permission.code == code))
        if not row:
            row = Permission(code=code, module=module, action=action, description=description)
            db.add(row)
            db.flush()
        permissions[code] = row
    roles = {row.code: row for row in db.scalars(select(Role).where(Role.company_id == company_id)).all()}
    for code, name, scope_level in (("RESOURCE_MANAGER", "Resource Manager", "company"), ("RESOURCE_PLANNER", "Resource Planner", "branch"), ("RESOURCE_REVIEWER", "Resource Reviewer", "company")):
        if code not in roles:
            row = Role(company_id=company_id, code=code, name=name, scope_level=scope_level, description=f"Phase 20 {name.lower()} role", is_system=True, is_active=True)
            db.add(row)
            db.flush()
            roles[code] = row
    grants = {
        "SYSTEM_ADMIN": set(PERMISSIONS), "HQ_EXECUTIVE": set(PERMISSIONS),
        "BRANCH_MANAGER": {"resources.view", "resources.manage", "resources.approve", "resources.export"},
        "PROJECT_MANAGER": {"resources.view", "resources.manage", "resources.export"}, "SITE_MANAGER": {"resources.view", "resources.manage"},
        "APPROVER": {"resources.approve"}, "AUDITOR": {"resources.view", "resources.export"},
        "RESOURCE_MANAGER": set(PERMISSIONS), "RESOURCE_PLANNER": {"resources.view", "resources.manage", "resources.export"},
        "RESOURCE_REVIEWER": {"resources.view", "resources.approve", "resources.fulfill", "resources.export"},
    }
    for role_code, codes in grants.items():
        role = roles.get(role_code)
        if not role:
            continue
        existing = set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id == role.id)).all())
        for code in codes:
            if permissions[code].id not in existing:
                db.add(RolePermission(role_id=role.id, permission_id=permissions[code].id))
                existing.add(permissions[code].id)
    for code, name, prefix in (("RESOURCE_PLAN", "Resource Plan", "RPL"), ("RESOURCE_REQUEST", "Resource Request", "RQR"), ("RESOURCE_APPROVAL", "Resource Approval", "RAP")):
        if not db.scalar(select(NumberSequence).where(NumberSequence.company_id == company_id, NumberSequence.code == code)):
            db.add(NumberSequence(company_id=company_id, code=code, name=name, prefix=prefix, next_number=1, padding=5, reset_period="yearly"))
    branch, hq = roles.get("BRANCH_MANAGER"), roles.get("HQ_EXECUTIVE")
    if not branch or not hq:
        raise HTTPException(status_code=409, detail="Branch Manager and HQ Executive roles are required for Phase 20")
    for code, name in (("RESOURCE_PLAN", "Resource Plan Approval"), ("RESOURCE_REQUEST", "Resource Request Approval")):
        row = db.scalar(select(ApprovalWorkflow).where(ApprovalWorkflow.company_id == company_id, ApprovalWorkflow.code == code))
        if not row:
            row = ApprovalWorkflow(company_id=company_id, code=code, name=name, module="resources", description=f"Controlled {name.lower()}", min_amount=Decimal("0"), is_active=True)
            db.add(row)
            db.flush()
        if not db.scalar(select(func.count()).select_from(ApprovalStep).where(ApprovalStep.workflow_id == row.id)):
            db.add_all([ApprovalStep(workflow_id=row.id, step_order=1, name="Branch Resource Review", role_id=branch.id, required_approvals=1, escalation_hours=24), ApprovalStep(workflow_id=row.id, step_order=2, name="Head Office Resource Approval", role_id=hq.id, required_approvals=1, escalation_hours=48)])
    if not db.scalar(select(CompanySetting).where(CompanySetting.company_id == company_id, CompanySetting.key == "resource_policy")):
        db.add(CompanySetting(company_id=company_id, key="resource_policy", value=dict(POLICY_DEFAULT), description="Phase 20 resource capacity governance"))


class PlanInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: int
    programme_baseline_id: int | None = None
    name: str = Field(min_length=2, max_length=240)
    horizon_start: date
    horizon_finish: date
    revision_reason: str | None = Field(default=None, max_length=4000)
    supporting_document_id: int | None = None


class PlanItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    activity_id: int | None = None
    employee_id: int | None = None
    asset_id: int | None = None
    stock_item_id: int | None = None
    resource_type: Literal["employee", "asset", "material", "subcontract", "other"]
    description: str = Field(min_length=2, max_length=300)
    quantity: Decimal = Field(gt=0)
    unit: str = Field(min_length=1, max_length=40)
    allocation_pct: Decimal = Field(default=Decimal("100"), gt=0, le=100)
    planned_from: date
    planned_to: date
    is_critical: bool = False
    supporting_document_id: int | None = None
    notes: str | None = Field(default=None, max_length=4000)


class RequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_type: Literal["hire", "rent", "procure", "reassign", "other"]
    needed_by: date
    quantity: Decimal = Field(gt=0)
    justification: str | None = Field(default=None, max_length=4000)
    supporting_document_id: int | None = None


class FulfilmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fulfilment_document_id: int | None = None


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]
    comment: str | None = Field(default=None, max_length=2000)


@router.post("/bootstrap")
def bootstrap(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if not principal.has_company_permission("company.manage") and not principal.has_company_permission("resources.manage"):
        raise HTTPException(status_code=403, detail="Company administration is required to initialise Phase 20")
    bootstrap_data(db, principal.user.company_id)
    commit(db)
    return {"phase": 20, "status": "ready"}


@router.get("/catalog")
def catalog(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    anywhere(principal, "resources.view")
    projects = [row_dict(row) for row in db.scalars(select(Project).where(Project.company_id == principal.user.company_id, Project.status.in_(("mobilising", "ready", "active"))).order_by(Project.name)).all() if principal.can("resources.view", branch_id=row.branch_id, site_id=row.primary_site_id)]
    baselines = [row_dict(row) for row in db.scalars(select(ProgrammeBaseline).where(ProgrammeBaseline.company_id == principal.user.company_id, ProgrammeBaseline.status == "approved").order_by(ProgrammeBaseline.approved_at.desc())).all() if principal.can("resources.view", branch_id=row.branch_id, site_id=row.site_id)]
    employees = [row_dict(row) for row in db.scalars(select(Employee).where(Employee.company_id == principal.user.company_id, Employee.employment_status == "active").order_by(Employee.first_name, Employee.last_name)).all()]
    assets = [row_dict(row) for row in db.scalars(select(FleetAsset).where(FleetAsset.company_id == principal.user.company_id, FleetAsset.status == "active", FleetAsset.serviceability == "serviceable").order_by(FleetAsset.asset_number)).all() if principal.can("resources.view", branch_id=row.branch_id, site_id=row.site_id)]
    stocks = [row_dict(row) for row in db.scalars(select(StockItem).where(StockItem.company_id == principal.user.company_id, StockItem.is_active.is_(True)).order_by(StockItem.sku)).all()]
    return {"projects": projects, "baselines": baselines, "employees": employees, "assets": assets, "stock_items": stocks, "policy": policy(db, principal.user.company_id), "permissions": [code for code in PERMISSIONS if principal.has_permission_anywhere(code)]}


@router.get("/plans")
def plans(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    anywhere(principal, "resources.view")
    rows = db.scalars(select(ResourcePlan).where(ResourcePlan.company_id == principal.user.company_id).order_by(ResourcePlan.created_at.desc())).all()
    return [plan_payload(db, row) for row in rows if principal.can("resources.view", branch_id=row.branch_id, site_id=row.site_id)]


@router.post("/plans", status_code=201)
def create_plan(payload: PlanInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    project = project_or_404(db, principal, payload.project_id, "resources.manage")
    if payload.horizon_finish < payload.horizon_start:
        raise HTTPException(status_code=422, detail="Resource planning horizon finish cannot precede its start")
    if payload.programme_baseline_id:
        baseline = db.get(ProgrammeBaseline, payload.programme_baseline_id)
        if not baseline or baseline.company_id != project.company_id or baseline.project_id != project.id or baseline.status != "approved":
            raise HTTPException(status_code=422, detail="Resource plan baseline must be an approved programme baseline for the project")
    ensure_document(db, project.company_id, payload.supporting_document_id)
    latest = db.scalar(select(func.max(ResourcePlan.version)).where(ResourcePlan.project_id == project.id)) or 0
    if latest and not payload.revision_reason:
        raise HTTPException(status_code=422, detail="A resource plan revision reason is required after the first plan")
    row = ResourcePlan(company_id=project.company_id, branch_id=project.branch_id, site_id=project.primary_site_id, project_id=project.id, programme_baseline_id=payload.programme_baseline_id, version=int(latest) + 1, plan_number=issue_reference(db, project.company_id, "RESOURCE_PLAN", "RPL"), name=payload.name.strip(), horizon_start=payload.horizon_start, horizon_finish=payload.horizon_finish, status="draft", revision_reason=payload.revision_reason, supporting_document_id=payload.supporting_document_id, prepared_by=principal.user.full_name)
    db.add(row)
    db.flush()
    audit(db, principal, "resources.plan.created", row, branch_id=row.branch_id, site_id=row.site_id, project_id=row.project_id, detail={"version": row.version})
    commit(db)
    return plan_payload(db, row)


@router.get("/plans/{plan_id:int}")
def plan_detail(plan_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    return plan_payload(db, plan_or_404(db, principal, plan_id), include_items=True)


@router.post("/plans/{plan_id:int}/items", status_code=201)
def add_plan_item(plan_id: int, payload: PlanItemInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    plan = plan_or_404(db, principal, plan_id, "resources.manage")
    ensure_plan_editable(plan)
    if payload.planned_to < payload.planned_from or payload.planned_from < plan.horizon_start or payload.planned_to > plan.horizon_finish:
        raise HTTPException(status_code=422, detail="Resource item dates must remain inside the plan horizon")
    ids = [payload.employee_id is not None, payload.asset_id is not None, payload.stock_item_id is not None]
    if sum(ids) > 1:
        raise HTTPException(status_code=422, detail="A resource plan item can identify only one specific employee, asset or material")
    if payload.resource_type == "employee":
        employee = db.get(Employee, payload.employee_id) if payload.employee_id else None
        if not employee or employee.company_id != plan.company_id or employee.employment_status != "active" or employee.branch_id != plan.branch_id:
            raise HTTPException(status_code=422, detail="Employee resources require an active employee in the project branch")
    elif payload.resource_type == "asset":
        asset = db.get(FleetAsset, payload.asset_id) if payload.asset_id else None
        if not asset or asset.company_id != plan.company_id or asset.branch_id != plan.branch_id or asset.status != "active" or asset.serviceability != "serviceable":
            raise HTTPException(status_code=422, detail="Asset resources require an active, serviceable asset in the project branch")
    elif payload.resource_type == "material":
        stock = db.get(StockItem, payload.stock_item_id) if payload.stock_item_id else None
        if not stock or stock.company_id != plan.company_id or not stock.is_active:
            raise HTTPException(status_code=422, detail="Material resources require an active company stock item")
    elif any(ids):
        raise HTTPException(status_code=422, detail="Only employee, asset and material resource types may link a specific master record")
    if payload.activity_id:
        activity = db.get(ProgrammeActivity, payload.activity_id)
        if not activity or activity.company_id != plan.company_id or activity.project_id != plan.project_id or (plan.programme_baseline_id and activity.baseline_id != plan.programme_baseline_id):
            raise HTTPException(status_code=422, detail="Resource activity must belong to the project programme baseline")
    ensure_document(db, plan.company_id, payload.supporting_document_id)
    next_line = (db.scalar(select(func.max(ResourcePlanItem.line_number)).where(ResourcePlanItem.plan_id == plan.id)) or 0) + 1
    row = ResourcePlanItem(company_id=plan.company_id, branch_id=plan.branch_id, site_id=plan.site_id, project_id=plan.project_id, plan_id=plan.id, activity_id=payload.activity_id, employee_id=payload.employee_id, asset_id=payload.asset_id, stock_item_id=payload.stock_item_id, line_number=next_line, resource_type=payload.resource_type, description=payload.description.strip(), quantity=payload.quantity, unit=payload.unit.strip(), allocation_pct=payload.allocation_pct, planned_from=payload.planned_from, planned_to=payload.planned_to, is_critical=payload.is_critical, supporting_document_id=payload.supporting_document_id, notes=payload.notes, created_by=principal.user.full_name)
    db.add(row)
    db.flush()
    audit(db, principal, "resources.plan.item.created", row, branch_id=plan.branch_id, site_id=plan.site_id, project_id=plan.project_id, detail={"plan_id": plan.id})
    commit(db)
    return row_dict(row)


@router.delete("/items/{item_id:int}")
def delete_plan_item(item_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, int]:
    item = item_or_404(db, principal, item_id, "resources.manage")
    plan = plan_or_404(db, principal, item.plan_id, "resources.manage")
    ensure_plan_editable(plan)
    requests = db.scalar(select(func.count()).select_from(ResourceRequest).where(ResourceRequest.plan_item_id == item.id)) or 0
    if requests:
        raise HTTPException(status_code=409, detail="Resource plan item cannot be removed after a resource request exists")
    db.delete(item)
    db.flush()
    audit(db, principal, "resources.plan.item.deleted", plan, branch_id=plan.branch_id, site_id=plan.site_id, project_id=plan.project_id, detail={"item_id": item_id})
    commit(db)
    return {"deleted_item_id": item_id}


@router.get("/plans/{plan_id:int}/conflicts")
def conflicts(plan_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    return plan_conflicts(db, plan_or_404(db, principal, plan_id))


@router.post("/plans/{plan_id:int}/submit")
def submit_plan(plan_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    plan = plan_or_404(db, principal, plan_id, "resources.manage")
    ensure_plan_editable(plan)
    if policy(db, plan.company_id)["require_plan_evidence"] and not plan.supporting_document_id:
        raise HTTPException(status_code=409, detail="Controlled resource-plan evidence is required before approval")
    if not db.scalar(select(func.count()).select_from(ResourcePlanItem).where(ResourcePlanItem.plan_id == plan.id)):
        raise HTTPException(status_code=409, detail="A resource plan requires at least one resource item before approval")
    conflicts_found = plan_conflicts(db, plan)
    if conflicts_found:
        raise HTTPException(status_code=409, detail="Resolve resource capacity conflicts before submitting this plan")
    request = approval_request(db, principal, code="RESOURCE_PLAN", entity_type="resource_plan", entity_id=plan.id, title=f"Resource plan {plan.plan_number}", branch_id=plan.branch_id, site_id=plan.site_id)
    plan.status, plan.approval_request_id, plan.submitted_at = "submitted", request.id, utcnow()
    audit(db, principal, "resources.plan.submitted", plan, branch_id=plan.branch_id, site_id=plan.site_id, project_id=plan.project_id, detail={"approval_reference": request.reference})
    commit(db)
    return row_dict(request)


@router.get("/requests")
def requests(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    anywhere(principal, "resources.view")
    rows = db.scalars(select(ResourceRequest).where(ResourceRequest.company_id == principal.user.company_id).order_by(ResourceRequest.needed_by, ResourceRequest.id.desc())).all()
    result: list[dict[str, Any]] = []
    for row in rows:
        if not principal.can("resources.view", branch_id=row.branch_id, site_id=row.site_id):
            continue
        payload = row_dict(row)
        item = db.get(ResourcePlanItem, row.plan_item_id)
        payload.update({"resource_description": item.description if item else "", "resource_type": item.resource_type if item else "", "plan_number": db.get(ResourcePlan, item.plan_id).plan_number if item and db.get(ResourcePlan, item.plan_id) else ""})
        result.append(payload)
    return result


@router.post("/items/{item_id:int}/requests", status_code=201)
def create_request(item_id: int, payload: RequestInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    item = item_or_404(db, principal, item_id, "resources.manage")
    plan = plan_or_404(db, principal, item.plan_id, "resources.manage")
    if plan.status != "approved":
        raise HTTPException(status_code=409, detail="Resource requests can only be prepared from an independently approved resource plan")
    if payload.needed_by < item.planned_from or payload.needed_by > item.planned_to:
        raise HTTPException(status_code=422, detail="Resource request need date must remain inside the approved planned resource window")
    requested = db.scalar(select(func.coalesce(func.sum(ResourceRequest.quantity), 0)).where(ResourceRequest.plan_item_id == item.id, ResourceRequest.status.in_(("submitted", "approved", "fulfilled")))) or 0
    if Decimal(payload.quantity) + Decimal(requested) > Decimal(item.quantity):
        raise HTTPException(status_code=409, detail="Resource request exceeds the remaining approved planned quantity")
    ensure_document(db, item.company_id, payload.supporting_document_id)
    row = ResourceRequest(company_id=item.company_id, branch_id=item.branch_id, site_id=item.site_id, project_id=item.project_id, plan_item_id=item.id, request_number=issue_reference(db, item.company_id, "RESOURCE_REQUEST", "RQR"), request_type=payload.request_type, needed_by=payload.needed_by, quantity=payload.quantity, status="draft", justification=payload.justification, supporting_document_id=payload.supporting_document_id, requested_by=principal.user.full_name)
    db.add(row)
    db.flush()
    audit(db, principal, "resources.request.created", row, branch_id=row.branch_id, site_id=row.site_id, project_id=row.project_id, detail={"plan_item_id": item.id})
    commit(db)
    return row_dict(row)


@router.post("/requests/{request_id:int}/submit")
def submit_request(request_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = request_or_404(db, principal, request_id, "resources.manage")
    if row.status not in {"draft", "rejected"}:
        raise HTTPException(status_code=409, detail="Only draft or rejected resource requests can be submitted")
    if policy(db, row.company_id)["require_request_evidence"] and not row.supporting_document_id:
        raise HTTPException(status_code=409, detail="Controlled resource request evidence is required before approval")
    request = approval_request(db, principal, code="RESOURCE_REQUEST", entity_type="resource_request", entity_id=row.id, title=f"Resource request {row.request_number}", branch_id=row.branch_id, site_id=row.site_id)
    row.status, row.approval_request_id, row.submitted_at = "submitted", request.id, utcnow()
    audit(db, principal, "resources.request.submitted", row, branch_id=row.branch_id, site_id=row.site_id, project_id=row.project_id, detail={"approval_reference": request.reference})
    commit(db)
    return row_dict(request)


@router.post("/requests/{request_id:int}/fulfil")
def fulfil_request(request_id: int, payload: FulfilmentInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = request_or_404(db, principal, request_id, "resources.fulfill")
    if row.status != "approved":
        raise HTTPException(status_code=409, detail="Only independently approved resource requests can be recorded as fulfilled")
    if policy(db, row.company_id)["require_fulfilment_evidence"] and not (payload.fulfilment_document_id or row.fulfilment_document_id):
        raise HTTPException(status_code=409, detail="Controlled fulfilment evidence is required before recording a resource request")
    ensure_document(db, row.company_id, payload.fulfilment_document_id)
    row.fulfilment_document_id = payload.fulfilment_document_id or row.fulfilment_document_id
    row.status, row.fulfilled_by, row.fulfilled_at = "fulfilled", principal.user.full_name, utcnow()
    audit(db, principal, "resources.request.fulfilled", row, branch_id=row.branch_id, site_id=row.site_id, project_id=row.project_id)
    commit(db)
    return row_dict(row)


@router.get("/approvals")
def approvals(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    anywhere(principal, "resources.view")
    rows = db.scalars(select(ApprovalRequest).where(ApprovalRequest.company_id == principal.user.company_id, ApprovalRequest.entity_type.in_(("resource_plan", "resource_request")), ApprovalRequest.status == "pending").order_by(ApprovalRequest.requested_at)).all()
    result: list[dict[str, Any]] = []
    for row in rows:
        if not principal.can("resources.view", branch_id=row.branch_id, site_id=row.site_id):
            continue
        payload = row_dict(row)
        entity = db.get(ResourcePlan, int(row.entity_id)) if row.entity_type == "resource_plan" else db.get(ResourceRequest, int(row.entity_id))
        payload["resource_reference"] = getattr(entity, "plan_number", None) or getattr(entity, "request_number", "")
        result.append(payload)
    return result


@router.post("/approvals/{approval_id:int}/decision")
def decide_approval(approval_id: int, payload: ApprovalDecision, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    approval = db.get(ApprovalRequest, approval_id)
    if not approval or approval.company_id != principal.user.company_id or approval.entity_type not in {"resource_plan", "resource_request"}:
        raise HTTPException(status_code=404, detail="Resource approval request not found")
    entity = db.get(ResourcePlan, int(approval.entity_id)) if approval.entity_type == "resource_plan" else db.get(ResourceRequest, int(approval.entity_id))
    if not entity:
        raise HTTPException(status_code=404, detail="Resource approval entity is unavailable")
    scope(principal, "resources.approve", entity.branch_id, entity.site_id)
    if approval.status != "pending" or entity.status != "submitted":
        raise HTTPException(status_code=409, detail="Resource approval request is not pending")
    step = db.scalar(select(ApprovalStep).where(ApprovalStep.workflow_id == approval.workflow_id, ApprovalStep.step_order == approval.current_step_order))
    if not step or not assignment_authorised(db, principal, step.role_id, entity.branch_id, entity.site_id):
        raise HTTPException(status_code=403, detail="Your active role assignment is not authorised for this resource approval step")
    if approval.requested_by == principal.user.full_name and not allow_self_approval(db, approval.company_id):
        raise HTTPException(status_code=422, detail="Self-approval is disabled by company policy")
    db.add(ApprovalAction(request_id=approval.id, step_order=step.step_order, role_id=step.role_id, actor_name=principal.user.full_name, action=payload.decision, comment=payload.comment))
    if payload.decision == "reject":
        approval.status, approval.completed_at, entity.status = "rejected", utcnow(), "rejected"
    else:
        completed = (db.scalar(select(func.count()).select_from(ApprovalAction).where(ApprovalAction.request_id == approval.id, ApprovalAction.step_order == step.step_order, ApprovalAction.action == "approve")) or 0) + 1
        if completed >= step.required_approvals:
            next_step = db.scalar(select(ApprovalStep).where(ApprovalStep.workflow_id == approval.workflow_id, ApprovalStep.step_order > step.step_order).order_by(ApprovalStep.step_order).limit(1))
            if next_step:
                approval.current_step_order = next_step.step_order
            else:
                approval.status, approval.completed_at, entity.status = "approved", utcnow(), "approved"
                entity.approved_at = utcnow()
                if approval.entity_type == "resource_plan":
                    prior = db.scalars(select(ResourcePlan).where(ResourcePlan.project_id == entity.project_id, ResourcePlan.status == "approved", ResourcePlan.id != entity.id)).all()
                    for old in prior:
                        old.status, old.superseded_at = "superseded", utcnow()
    audit(db, principal, f"resources.approval.{payload.decision}", approval, branch_id=entity.branch_id, site_id=entity.site_id, project_id=entity.project_id, detail={"entity_type": approval.entity_type, "approval_status": approval.status, "step": step.step_order})
    commit(db)
    return row_dict(approval)


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    anywhere(principal, "resources.view")
    plans = [row for row in db.scalars(select(ResourcePlan).where(ResourcePlan.company_id == principal.user.company_id)).all() if principal.can("resources.view", branch_id=row.branch_id, site_id=row.site_id)]
    requests = [row for row in db.scalars(select(ResourceRequest).where(ResourceRequest.company_id == principal.user.company_id)).all() if principal.can("resources.view", branch_id=row.branch_id, site_id=row.site_id)]
    conflicts_found = sum((len(plan_conflicts(db, row)) for row in plans if row.status in {"draft", "submitted", "approved"}), 0)
    today = date.today()
    return {"approved_plans": sum(row.status == "approved" for row in plans), "draft_plans": sum(row.status in {"draft", "rejected"} for row in plans), "pending_plans": sum(row.status == "submitted" for row in plans), "capacity_conflicts": conflicts_found, "requests_pending": sum(row.status in {"draft", "submitted", "approved"} for row in requests), "requests_due": sum(row.status in {"draft", "submitted", "approved"} and row.needed_by <= today for row in requests), "requests_fulfilled": sum(row.status == "fulfilled" for row in requests)}


@router.get("/exports/plan-items.csv")
def export_plan_items(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> StreamingResponse:
    anywhere(principal, "resources.export")
    stream = io.StringIO()
    fields = ["plan_number", "project_number", "line_number", "resource_type", "description", "quantity", "unit", "allocation_pct", "planned_from", "planned_to", "is_critical"]
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    rows = db.scalars(select(ResourcePlan).where(ResourcePlan.company_id == principal.user.company_id, ResourcePlan.status == "approved")).all()
    for plan in rows:
        if not principal.can("resources.export", branch_id=plan.branch_id, site_id=plan.site_id):
            continue
        payload = plan_payload(db, plan, include_items=True)
        for item in payload["items"]:
            writer.writerow({"plan_number": plan.plan_number, "project_number": payload["project_number"], **{key: item.get(key, "") for key in fields if key not in {"plan_number", "project_number"}}})
    return StreamingResponse(iter([stream.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=resource-plan-items.csv"})


@router.get("/audit")
def audit_events(limit: int = Query(default=250, ge=1, le=1000), db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    anywhere(principal, "resources.view")
    rows = db.scalars(select(ResourceAuditEvent).where(ResourceAuditEvent.company_id == principal.user.company_id).order_by(ResourceAuditEvent.occurred_at.desc()).limit(limit)).all()
    return [row_dict(row) for row in rows if row.branch_id is None or principal.can("resources.view", branch_id=row.branch_id, site_id=row.site_id)]
