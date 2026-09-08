from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date, timedelta
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
    ApprovalAction, ApprovalRequest, ApprovalStep, ApprovalWorkflow, Branch, CompanySetting, Employee,
    NumberSequence, Permission, PlanningAuditEvent, ProgrammeActivity, ProgrammeActivityUpdate,
    ProgrammeBaseline, ProgrammeDelayEvent, ProgrammeLookaheadItem, Project, ProjectMilestone, Role,
    RolePermission, Site,
)
from app.security.access import Principal, current_principal


router = APIRouter(prefix="/planning", tags=["Phase 19 - Programme & Project Controls"])

PERMISSIONS = {
    "planning.view": ("planning", "view", "View project programmes, progress, lookaheads and delay evidence"),
    "planning.manage": ("planning", "manage", "Prepare programme baselines, updates, lookaheads and delay records"),
    "planning.approve": ("planning", "approve", "Independently approve programme baselines"),
    "planning.export": ("planning", "export", "Export controlled programme registers"),
}

POLICY_DEFAULT = {
    "require_baseline_evidence": True,
    "programme_weight_pct": 100,
    "lookahead_window_days": 42,
    "delay_notice_warning_days": 3,
}


def anywhere(principal: Principal, permission: str) -> None:
    if not principal.has_permission_anywhere(permission):
        raise HTTPException(status_code=403, detail=f"Permission required: {permission}")


def scope(principal: Principal, permission: str, branch_id: int, site_id: int | None = None) -> None:
    if not principal.can(permission, branch_id=branch_id, site_id=site_id):
        raise HTTPException(status_code=403, detail=f"Permission required in this branch/site: {permission}")


def policy(db: Session, company_id: int) -> dict[str, Any]:
    row = db.scalar(select(CompanySetting).where(CompanySetting.company_id == company_id, CompanySetting.key == "planning_policy"))
    return {**POLICY_DEFAULT, **(row.value if row and isinstance(row.value, dict) else {})}


def audit(db: Session, principal: Principal, action: str, entity: Any, *, branch_id: int | None, site_id: int | None, project_id: int | None, detail: dict[str, Any] | None = None) -> None:
    db.add(PlanningAuditEvent(company_id=principal.user.company_id, branch_id=branch_id, site_id=site_id, project_id=project_id, actor=principal.user.full_name, action=action, entity_type=entity.__tablename__, entity_id=str(entity.id), detail=detail or {}))


def project_or_404(db: Session, principal: Principal, project_id: int, permission: str = "planning.view") -> Project:
    row = db.get(Project, project_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Project not found")
    scope(principal, permission, row.branch_id, row.primary_site_id)
    return row


def baseline_or_404(db: Session, principal: Principal, baseline_id: int, permission: str = "planning.view") -> ProgrammeBaseline:
    row = db.get(ProgrammeBaseline, baseline_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Programme baseline not found")
    scope(principal, permission, row.branch_id, row.site_id)
    return row


def activity_or_404(db: Session, principal: Principal, activity_id: int, permission: str = "planning.view") -> ProgrammeActivity:
    row = db.get(ProgrammeActivity, activity_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Programme activity not found")
    baseline = baseline_or_404(db, principal, row.baseline_id, permission)
    return row


def ensure_baseline_editable(row: ProgrammeBaseline) -> None:
    if row.status not in {"draft", "rejected"}:
        raise HTTPException(status_code=409, detail="Programme baseline is frozen while approval is active or after approval")


def latest_updates(db: Session, activity_ids: list[int]) -> dict[int, ProgrammeActivityUpdate]:
    result: dict[int, ProgrammeActivityUpdate] = {}
    if not activity_ids:
        return result
    rows = db.scalars(select(ProgrammeActivityUpdate).where(ProgrammeActivityUpdate.activity_id.in_(activity_ids)).order_by(ProgrammeActivityUpdate.activity_id, ProgrammeActivityUpdate.reporting_date.desc(), ProgrammeActivityUpdate.id.desc())).all()
    for row in rows:
        result.setdefault(row.activity_id, row)
    return result


def dependency_order(activities: list[ProgrammeActivity]) -> list[int]:
    ids = {row.id for row in activities}
    predecessor = {row.id: row.predecessor_activity_id for row in activities if row.predecessor_activity_id in ids}
    visiting: set[int] = set()
    visited: set[int] = set()
    order: list[int] = []

    def visit(item_id: int) -> None:
        if item_id in visited:
            return
        if item_id in visiting:
            raise HTTPException(status_code=409, detail="Programme activity dependencies contain a cycle")
        visiting.add(item_id)
        if predecessor.get(item_id):
            visit(int(predecessor[item_id]))
        visiting.remove(item_id)
        visited.add(item_id)
        order.append(item_id)

    for item_id in ids:
        visit(item_id)
    return order


def programme_metrics(db: Session, baseline: ProgrammeBaseline, as_of: date | None = None) -> dict[str, Any]:
    as_of = as_of or date.today()
    activities = db.scalars(select(ProgrammeActivity).where(ProgrammeActivity.baseline_id == baseline.id).order_by(ProgrammeActivity.planned_start, ProgrammeActivity.id)).all()
    order = dependency_order(activities)
    by_id = {row.id: row for row in activities}
    successors: dict[int, list[int]] = defaultdict(list)
    for row in activities:
        if row.predecessor_activity_id in by_id:
            successors[int(row.predecessor_activity_id)].append(row.id)
    critical: set[int] = {row.id for row in activities if row.planned_finish == baseline.baseline_finish}
    queue = list(critical)
    while queue:
        current = queue.pop()
        predecessor = by_id[current].predecessor_activity_id
        if predecessor in by_id and predecessor not in critical:
            critical.add(int(predecessor))
            queue.append(int(predecessor))
    updates = latest_updates(db, list(by_id))
    total_weight = sum((Decimal(row.weight_pct) for row in activities), Decimal("0"))
    planned, actual = Decimal("0"), Decimal("0")
    delayed, complete = 0, 0
    forecast_finish = baseline.baseline_finish
    payloads: list[dict[str, Any]] = []
    for item_id in order:
        row = by_id[item_id]
        duration = max((row.planned_finish - row.planned_start).days, 0)
        if as_of < row.planned_start:
            planned_pct = Decimal("0")
        elif as_of >= row.planned_finish:
            planned_pct = Decimal("100")
        else:
            planned_pct = Decimal((as_of - row.planned_start).days * 100) / Decimal(max(duration, 1))
        update = updates.get(row.id)
        actual_pct = Decimal(update.progress_pct) if update else Decimal("0")
        planned += Decimal(row.weight_pct) * planned_pct / Decimal("100")
        actual += Decimal(row.weight_pct) * actual_pct / Decimal("100")
        late = bool(update and update.forecast_finish and update.forecast_finish > row.planned_finish) or (actual_pct < Decimal("100") and as_of > row.planned_finish)
        if late:
            delayed += 1
        if actual_pct >= Decimal("100"):
            complete += 1
        if update and update.forecast_finish and update.forecast_finish > forecast_finish:
            forecast_finish = update.forecast_finish
        item = row_dict(row)
        item.update({"critical": row.id in critical, "planned_progress_pct": str(planned_pct.quantize(Decimal("0.001"))), "actual_progress_pct": str(actual_pct), "variance_pct": str((actual_pct - planned_pct).quantize(Decimal("0.001"))), "late": late, "latest_update": row_dict(update) if update else None, "successor_count": len(successors.get(row.id, []))})
        payloads.append(item)
    return {"activities": payloads, "activity_count": len(activities), "critical_count": len(critical), "delayed_count": delayed, "complete_count": complete, "total_weight_pct": str(total_weight), "planned_progress_pct": str(planned.quantize(Decimal("0.001"))), "actual_progress_pct": str(actual.quantize(Decimal("0.001"))), "variance_pct": str((actual - planned).quantize(Decimal("0.001"))), "forecast_finish": forecast_finish.isoformat()}


def baseline_payload(db: Session, row: ProgrammeBaseline, include_activities: bool = False) -> dict[str, Any]:
    payload = row_dict(row)
    project = db.get(Project, row.project_id)
    payload.update({"project_number": project.project_number if project else "", "project_name": project.name if project else ""})
    metrics = programme_metrics(db, row)
    payload.update({key: value for key, value in metrics.items() if key != "activities"})
    if include_activities:
        payload["activities"] = metrics["activities"]
    return payload


def approval_workflow(db: Session, company_id: int) -> ApprovalWorkflow:
    row = db.scalar(select(ApprovalWorkflow).where(ApprovalWorkflow.company_id == company_id, ApprovalWorkflow.code == "PROGRAMME_BASELINE", ApprovalWorkflow.is_active.is_(True)))
    if not row or not db.scalar(select(func.count()).select_from(ApprovalStep).where(ApprovalStep.workflow_id == row.id)):
        raise HTTPException(status_code=409, detail="Programme baseline approval workflow is not configured")
    return row


def create_approval(db: Session, principal: Principal, baseline: ProgrammeBaseline) -> ApprovalRequest:
    workflow = approval_workflow(db, baseline.company_id)
    row = ApprovalRequest(company_id=baseline.company_id, workflow_id=workflow.id, branch_id=baseline.branch_id, site_id=baseline.site_id, entity_type="programme_baseline", entity_id=str(baseline.id), reference=issue_reference(db, baseline.company_id, "PROGRAMME_APPROVAL", "PAP"), title=f"Programme baseline {baseline.baseline_number}", amount=Decimal("0"), status="pending", current_step_order=1, requested_by=principal.user.full_name)
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
    for code, name, scope_level in (("PROGRAMME_MANAGER", "Programme Manager", "company"), ("PLANNER", "Planner", "branch"), ("PROGRAMME_REVIEWER", "Programme Reviewer", "company")):
        if code not in roles:
            row = Role(company_id=company_id, code=code, name=name, scope_level=scope_level, description=f"Phase 19 {name.lower()} role", is_system=True, is_active=True)
            db.add(row)
            db.flush()
            roles[code] = row
    grants = {
        "SYSTEM_ADMIN": set(PERMISSIONS), "HQ_EXECUTIVE": set(PERMISSIONS),
        "BRANCH_MANAGER": {"planning.view", "planning.manage", "planning.approve", "planning.export"},
        "PROJECT_MANAGER": {"planning.view", "planning.manage", "planning.export"}, "SITE_MANAGER": {"planning.view", "planning.manage"},
        "APPROVER": {"planning.approve"}, "AUDITOR": {"planning.view", "planning.export"},
        "PROGRAMME_MANAGER": set(PERMISSIONS), "PLANNER": {"planning.view", "planning.manage", "planning.export"},
        "PROGRAMME_REVIEWER": {"planning.view", "planning.approve", "planning.export"},
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
    for code, name, prefix in (("PROGRAMME_BASELINE", "Programme Baseline", "PBL"), ("PROGRAMME_DELAY", "Programme Delay", "PDL"), ("PROGRAMME_APPROVAL", "Programme Approval", "PAP")):
        if not db.scalar(select(NumberSequence).where(NumberSequence.company_id == company_id, NumberSequence.code == code)):
            db.add(NumberSequence(company_id=company_id, code=code, name=name, prefix=prefix, next_number=1, padding=5, reset_period="yearly"))
    branch, hq = roles.get("BRANCH_MANAGER"), roles.get("HQ_EXECUTIVE")
    if not branch or not hq:
        raise HTTPException(status_code=409, detail="Branch Manager and HQ Executive roles are required for Phase 19")
    flow = db.scalar(select(ApprovalWorkflow).where(ApprovalWorkflow.company_id == company_id, ApprovalWorkflow.code == "PROGRAMME_BASELINE"))
    if not flow:
        flow = ApprovalWorkflow(company_id=company_id, code="PROGRAMME_BASELINE", name="Programme Baseline Approval", module="planning", description="Controlled programme baseline approval", min_amount=Decimal("0"), is_active=True)
        db.add(flow)
        db.flush()
    if not db.scalar(select(func.count()).select_from(ApprovalStep).where(ApprovalStep.workflow_id == flow.id)):
        db.add_all([ApprovalStep(workflow_id=flow.id, step_order=1, name="Branch Programme Review", role_id=branch.id, required_approvals=1, escalation_hours=24), ApprovalStep(workflow_id=flow.id, step_order=2, name="Head Office Programme Approval", role_id=hq.id, required_approvals=1, escalation_hours=48)])
    if not db.scalar(select(CompanySetting).where(CompanySetting.company_id == company_id, CompanySetting.key == "planning_policy")):
        db.add(CompanySetting(company_id=company_id, key="planning_policy", value=dict(POLICY_DEFAULT), description="Phase 19 programme governance"))


class BaselineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: int
    name: str = Field(min_length=2, max_length=240)
    baseline_start: date
    baseline_finish: date
    revision_reason: str | None = Field(default=None, max_length=4000)
    supporting_document_id: int | None = None


class ActivityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    milestone_id: int | None = None
    predecessor_activity_id: int | None = None
    owner_employee_id: int | None = None
    wbs_code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=2, max_length=300)
    planned_start: date
    planned_finish: date
    weight_pct: Decimal = Field(ge=0, le=100)
    is_milestone: bool = False
    notes: str | None = Field(default=None, max_length=4000)


class ActivityUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reporting_date: date
    progress_pct: Decimal = Field(ge=0, le=100)
    status: Literal["not_started", "in_progress", "complete", "on_hold"]
    actual_start: date | None = None
    actual_finish: date | None = None
    forecast_finish: date | None = None
    delay_reason: str | None = Field(default=None, max_length=4000)
    evidence_document_id: int | None = None
    notes: str | None = Field(default=None, max_length=4000)


class LookaheadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseline_id: int
    activity_id: int | None = None
    owner_employee_id: int | None = None
    title: str = Field(min_length=2, max_length=300)
    planned_start: date
    planned_finish: date
    status: Literal["ready", "blocked", "in_progress", "complete"] = "ready"
    constraint: str | None = Field(default=None, max_length=4000)
    evidence_document_id: int | None = None
    notes: str | None = Field(default=None, max_length=4000)


class LookaheadStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ready", "blocked", "in_progress", "complete"]
    constraint: str | None = Field(default=None, max_length=4000)
    evidence_document_id: int | None = None


class DelayInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: int
    baseline_id: int | None = None
    activity_id: int | None = None
    category: str = Field(min_length=2, max_length=80)
    responsible_party: Literal["client", "contractor", "third_party", "weather", "unconfirmed"] = "unconfirmed"
    title: str = Field(min_length=2, max_length=300)
    event_date: date
    expected_days: int = Field(default=0, ge=0, le=3650)
    notice_due_date: date | None = None
    description: str | None = Field(default=None, max_length=4000)
    evidence_document_id: int | None = None


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]
    comment: str | None = Field(default=None, max_length=2000)


@router.post("/bootstrap")
def bootstrap(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if not principal.has_company_permission("company.manage") and not principal.has_company_permission("planning.manage"):
        raise HTTPException(status_code=403, detail="Company administration is required to initialise Phase 19")
    bootstrap_data(db, principal.user.company_id)
    commit(db)
    return {"phase": 19, "status": "ready"}


@router.get("/catalog")
def catalog(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    anywhere(principal, "planning.view")
    projects = [row_dict(row) for row in db.scalars(select(Project).where(Project.company_id == principal.user.company_id, Project.status.in_(("mobilising", "ready", "active"))).order_by(Project.name)).all() if principal.can("planning.view", branch_id=row.branch_id, site_id=row.primary_site_id)]
    employees = [row_dict(row) for row in db.scalars(select(Employee).where(Employee.company_id == principal.user.company_id, Employee.employment_status == "active").order_by(Employee.first_name, Employee.last_name)).all()]
    return {"projects": projects, "employees": employees, "permissions": [code for code in PERMISSIONS if principal.has_permission_anywhere(code)], "policy": policy(db, principal.user.company_id)}


@router.get("/baselines")
def baselines(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    anywhere(principal, "planning.view")
    rows = db.scalars(select(ProgrammeBaseline).where(ProgrammeBaseline.company_id == principal.user.company_id).order_by(ProgrammeBaseline.created_at.desc())).all()
    return [baseline_payload(db, row) for row in rows if principal.can("planning.view", branch_id=row.branch_id, site_id=row.site_id)]


@router.post("/baselines", status_code=201)
def create_baseline(payload: BaselineInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    project = project_or_404(db, principal, payload.project_id, "planning.manage")
    if payload.baseline_finish < payload.baseline_start:
        raise HTTPException(status_code=422, detail="Programme baseline finish cannot precede its start")
    ensure_document(db, principal.user.company_id, payload.supporting_document_id)
    latest = db.scalar(select(func.max(ProgrammeBaseline.version)).where(ProgrammeBaseline.project_id == project.id)) or 0
    if latest and not payload.revision_reason:
        raise HTTPException(status_code=422, detail="A programme baseline revision reason is required after the first baseline")
    row = ProgrammeBaseline(company_id=project.company_id, branch_id=project.branch_id, site_id=project.primary_site_id, project_id=project.id, version=int(latest) + 1, baseline_number=issue_reference(db, project.company_id, "PROGRAMME_BASELINE", "PBL"), name=payload.name.strip(), baseline_start=payload.baseline_start, baseline_finish=payload.baseline_finish, status="draft", revision_reason=payload.revision_reason, supporting_document_id=payload.supporting_document_id, prepared_by=principal.user.full_name)
    db.add(row)
    db.flush()
    audit(db, principal, "planning.baseline.created", row, branch_id=row.branch_id, site_id=row.site_id, project_id=row.project_id, detail={"version": row.version})
    commit(db)
    return baseline_payload(db, row)


@router.get("/baselines/{baseline_id:int}")
def baseline_detail(baseline_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    return baseline_payload(db, baseline_or_404(db, principal, baseline_id), include_activities=True)


@router.post("/baselines/{baseline_id:int}/activities", status_code=201)
def add_activity(baseline_id: int, payload: ActivityInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    baseline = baseline_or_404(db, principal, baseline_id, "planning.manage")
    ensure_baseline_editable(baseline)
    if payload.planned_finish < payload.planned_start:
        raise HTTPException(status_code=422, detail="Programme activity finish cannot precede its start")
    if payload.planned_start < baseline.baseline_start or payload.planned_finish > baseline.baseline_finish:
        raise HTTPException(status_code=422, detail="Programme activity must remain inside its baseline dates")
    if payload.milestone_id:
        milestone = db.get(ProjectMilestone, payload.milestone_id)
        if not milestone or milestone.company_id != baseline.company_id or milestone.project_id != baseline.project_id:
            raise HTTPException(status_code=422, detail="Milestone must belong to this programme project")
    if payload.owner_employee_id:
        employee = db.get(Employee, payload.owner_employee_id)
        if not employee or employee.company_id != baseline.company_id or employee.employment_status != "active" or employee.branch_id != baseline.branch_id:
            raise HTTPException(status_code=422, detail="Activity owner must be an active employee in the programme branch")
    predecessor = None
    if payload.predecessor_activity_id:
        predecessor = db.get(ProgrammeActivity, payload.predecessor_activity_id)
        if not predecessor or predecessor.baseline_id != baseline.id:
            raise HTTPException(status_code=422, detail="Activity predecessor must belong to this baseline")
        if predecessor.planned_finish > payload.planned_start:
            raise HTTPException(status_code=422, detail="Successor activity cannot start before its predecessor finishes")
    if db.scalar(select(ProgrammeActivity.id).where(ProgrammeActivity.baseline_id == baseline.id, ProgrammeActivity.wbs_code == payload.wbs_code.strip())):
        raise HTTPException(status_code=409, detail="Programme WBS code already exists in this baseline")
    row = ProgrammeActivity(company_id=baseline.company_id, baseline_id=baseline.id, project_id=baseline.project_id, milestone_id=payload.milestone_id, predecessor_activity_id=payload.predecessor_activity_id, owner_employee_id=payload.owner_employee_id, wbs_code=payload.wbs_code.strip(), name=payload.name.strip(), planned_start=payload.planned_start, planned_finish=payload.planned_finish, weight_pct=payload.weight_pct, is_milestone=payload.is_milestone, notes=payload.notes, created_by=principal.user.full_name)
    db.add(row)
    db.flush()
    dependency_order(db.scalars(select(ProgrammeActivity).where(ProgrammeActivity.baseline_id == baseline.id)).all())
    audit(db, principal, "planning.activity.created", row, branch_id=baseline.branch_id, site_id=baseline.site_id, project_id=baseline.project_id, detail={"baseline_id": baseline.id})
    commit(db)
    return row_dict(row)


@router.delete("/activities/{activity_id:int}")
def delete_activity(activity_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, int]:
    row = activity_or_404(db, principal, activity_id, "planning.manage")
    baseline = baseline_or_404(db, principal, row.baseline_id, "planning.manage")
    ensure_baseline_editable(baseline)
    dependents = db.scalar(select(func.count()).select_from(ProgrammeActivity).where(ProgrammeActivity.predecessor_activity_id == row.id)) or 0
    if dependents:
        raise HTTPException(status_code=409, detail="Remove successor dependencies before deleting this activity")
    db.delete(row)
    db.flush()
    audit(db, principal, "planning.activity.deleted", baseline, branch_id=baseline.branch_id, site_id=baseline.site_id, project_id=baseline.project_id, detail={"activity_id": activity_id})
    commit(db)
    return {"deleted_activity_id": activity_id}


@router.post("/baselines/{baseline_id:int}/submit")
def submit_baseline(baseline_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    baseline = baseline_or_404(db, principal, baseline_id, "planning.manage")
    ensure_baseline_editable(baseline)
    config = policy(db, baseline.company_id)
    if config["require_baseline_evidence"] and not baseline.supporting_document_id:
        raise HTTPException(status_code=409, detail="Controlled programme baseline evidence is required before approval")
    metrics = programme_metrics(db, baseline)
    if metrics["activity_count"] < 1:
        raise HTTPException(status_code=409, detail="A programme baseline requires at least one activity before approval")
    if Decimal(metrics["total_weight_pct"]) != Decimal(str(config["programme_weight_pct"])):
        raise HTTPException(status_code=409, detail=f"Programme activity weights must total {config['programme_weight_pct']}% before approval")
    request = create_approval(db, principal, baseline)
    baseline.status, baseline.approval_request_id, baseline.submitted_at = "submitted", request.id, utcnow()
    audit(db, principal, "planning.baseline.submitted", baseline, branch_id=baseline.branch_id, site_id=baseline.site_id, project_id=baseline.project_id, detail={"approval_reference": request.reference})
    commit(db)
    return row_dict(request)


@router.post("/activities/{activity_id:int}/updates", status_code=201)
def record_activity_update(activity_id: int, payload: ActivityUpdateInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    activity = activity_or_404(db, principal, activity_id, "planning.manage")
    baseline = baseline_or_404(db, principal, activity.baseline_id, "planning.manage")
    if baseline.status != "approved":
        raise HTTPException(status_code=409, detail="Activity progress can only be recorded against an independently approved baseline")
    if payload.actual_finish and payload.actual_start and payload.actual_finish < payload.actual_start:
        raise HTTPException(status_code=422, detail="Actual finish cannot precede actual start")
    if payload.forecast_finish and payload.actual_start and payload.forecast_finish < payload.actual_start:
        raise HTTPException(status_code=422, detail="Forecast finish cannot precede actual start")
    if payload.status == "complete" and payload.progress_pct != Decimal("100"):
        raise HTTPException(status_code=422, detail="A complete activity must report 100% progress")
    if payload.progress_pct == Decimal("100") and payload.status != "complete":
        raise HTTPException(status_code=422, detail="100% progress must be marked complete")
    ensure_document(db, principal.user.company_id, payload.evidence_document_id)
    previous = db.scalar(select(ProgrammeActivityUpdate).where(ProgrammeActivityUpdate.activity_id == activity.id).order_by(ProgrammeActivityUpdate.reporting_date.desc(), ProgrammeActivityUpdate.id.desc()).limit(1))
    if previous and payload.reporting_date <= previous.reporting_date:
        raise HTTPException(status_code=409, detail="Activity updates must use a later reporting date than the previous controlled update")
    if previous and payload.progress_pct < Decimal(previous.progress_pct):
        raise HTTPException(status_code=422, detail="Cumulative activity progress cannot move backwards")
    row = ProgrammeActivityUpdate(company_id=activity.company_id, activity_id=activity.id, project_id=activity.project_id, reporting_date=payload.reporting_date, progress_pct=payload.progress_pct, status=payload.status, actual_start=payload.actual_start, actual_finish=payload.actual_finish, forecast_finish=payload.forecast_finish, delay_reason=payload.delay_reason, evidence_document_id=payload.evidence_document_id, notes=payload.notes, reported_by=principal.user.full_name)
    db.add(row)
    db.flush()
    audit(db, principal, "planning.activity.update.recorded", row, branch_id=baseline.branch_id, site_id=baseline.site_id, project_id=activity.project_id, detail={"activity_id": activity.id, "progress_pct": str(row.progress_pct)})
    commit(db)
    return row_dict(row)


@router.get("/lookaheads")
def lookaheads(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    anywhere(principal, "planning.view")
    rows = db.scalars(select(ProgrammeLookaheadItem).where(ProgrammeLookaheadItem.company_id == principal.user.company_id).order_by(ProgrammeLookaheadItem.planned_start, ProgrammeLookaheadItem.id)).all()
    result: list[dict[str, Any]] = []
    for row in rows:
        if not principal.can("planning.view", branch_id=row.branch_id, site_id=row.site_id):
            continue
        payload = row_dict(row)
        project = db.get(Project, row.project_id)
        activity = db.get(ProgrammeActivity, row.activity_id) if row.activity_id else None
        payload.update({"project_name": project.name if project else "", "activity_name": activity.name if activity else ""})
        result.append(payload)
    return result


@router.post("/lookaheads", status_code=201)
def create_lookahead(payload: LookaheadInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    baseline = baseline_or_404(db, principal, payload.baseline_id, "planning.manage")
    if baseline.status != "approved":
        raise HTTPException(status_code=409, detail="Lookahead items require an independently approved programme baseline")
    if payload.planned_finish < payload.planned_start:
        raise HTTPException(status_code=422, detail="Lookahead finish cannot precede its start")
    if payload.planned_start < date.today() - timedelta(days=1) or payload.planned_finish > date.today() + timedelta(days=int(policy(db, baseline.company_id)["lookahead_window_days"])):
        raise HTTPException(status_code=422, detail="Lookahead activities must stay inside the configured rolling planning window")
    if payload.activity_id:
        activity = db.get(ProgrammeActivity, payload.activity_id)
        if not activity or activity.baseline_id != baseline.id:
            raise HTTPException(status_code=422, detail="Lookahead activity must belong to the selected programme baseline")
    if payload.owner_employee_id:
        employee = db.get(Employee, payload.owner_employee_id)
        if not employee or employee.company_id != baseline.company_id or employee.employment_status != "active" or employee.branch_id != baseline.branch_id:
            raise HTTPException(status_code=422, detail="Lookahead owner must be an active employee in the project branch")
    ensure_document(db, baseline.company_id, payload.evidence_document_id)
    row = ProgrammeLookaheadItem(company_id=baseline.company_id, branch_id=baseline.branch_id, site_id=baseline.site_id, project_id=baseline.project_id, baseline_id=baseline.id, activity_id=payload.activity_id, owner_employee_id=payload.owner_employee_id, title=payload.title.strip(), planned_start=payload.planned_start, planned_finish=payload.planned_finish, status=payload.status, constraint=payload.constraint, evidence_document_id=payload.evidence_document_id, notes=payload.notes, created_by=principal.user.full_name)
    db.add(row)
    db.flush()
    audit(db, principal, "planning.lookahead.created", row, branch_id=row.branch_id, site_id=row.site_id, project_id=row.project_id, detail={"baseline_id": baseline.id})
    commit(db)
    return row_dict(row)


@router.patch("/lookaheads/{item_id:int}/status")
def update_lookahead_status(item_id: int, payload: LookaheadStatusInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = db.get(ProgrammeLookaheadItem, item_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Programme lookahead item not found")
    scope(principal, "planning.manage", row.branch_id, row.site_id)
    ensure_document(db, row.company_id, payload.evidence_document_id)
    row.status = payload.status
    row.constraint = payload.constraint or row.constraint
    row.evidence_document_id = payload.evidence_document_id or row.evidence_document_id
    audit(db, principal, "planning.lookahead.status.updated", row, branch_id=row.branch_id, site_id=row.site_id, project_id=row.project_id, detail={"status": row.status})
    commit(db)
    return row_dict(row)


@router.get("/delays")
def delays(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    anywhere(principal, "planning.view")
    rows = db.scalars(select(ProgrammeDelayEvent).where(ProgrammeDelayEvent.company_id == principal.user.company_id).order_by(ProgrammeDelayEvent.event_date.desc(), ProgrammeDelayEvent.id.desc())).all()
    return [row_dict(row) for row in rows if principal.can("planning.view", branch_id=row.branch_id, site_id=row.site_id)]


@router.post("/delays", status_code=201)
def create_delay(payload: DelayInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    project = project_or_404(db, principal, payload.project_id, "planning.manage")
    baseline = None
    if payload.baseline_id:
        baseline = baseline_or_404(db, principal, payload.baseline_id, "planning.manage")
        if baseline.project_id != project.id:
            raise HTTPException(status_code=422, detail="Delay baseline must belong to the selected project")
    if payload.activity_id:
        activity = activity_or_404(db, principal, payload.activity_id, "planning.manage")
        if activity.project_id != project.id or (baseline and activity.baseline_id != baseline.id):
            raise HTTPException(status_code=422, detail="Delay activity must match the selected project programme")
    if payload.notice_due_date and payload.notice_due_date < payload.event_date:
        raise HTTPException(status_code=422, detail="Delay notice due date cannot precede the event date")
    ensure_document(db, project.company_id, payload.evidence_document_id)
    row = ProgrammeDelayEvent(company_id=project.company_id, branch_id=project.branch_id, site_id=project.primary_site_id, project_id=project.id, baseline_id=payload.baseline_id, activity_id=payload.activity_id, delay_number=issue_reference(db, project.company_id, "PROGRAMME_DELAY", "PDL"), category=payload.category.strip(), responsible_party=payload.responsible_party, title=payload.title.strip(), event_date=payload.event_date, expected_days=payload.expected_days, notice_due_date=payload.notice_due_date, status="draft", description=payload.description, evidence_document_id=payload.evidence_document_id, recorded_by=principal.user.full_name)
    db.add(row)
    db.flush()
    audit(db, principal, "planning.delay.created", row, branch_id=row.branch_id, site_id=row.site_id, project_id=row.project_id)
    commit(db)
    return row_dict(row)


@router.post("/delays/{delay_id:int}/raise")
def raise_delay(delay_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = db.get(ProgrammeDelayEvent, delay_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Programme delay event not found")
    scope(principal, "planning.manage", row.branch_id, row.site_id)
    if row.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft delay records can be raised for controlled follow-up")
    if not row.evidence_document_id:
        raise HTTPException(status_code=409, detail="Controlled delay evidence is required before a delay can be raised")
    row.status, row.raised_at = "raised", utcnow()
    audit(db, principal, "planning.delay.raised", row, branch_id=row.branch_id, site_id=row.site_id, project_id=row.project_id)
    commit(db)
    return row_dict(row)


@router.post("/delays/{delay_id:int}/close")
def close_delay(delay_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = db.get(ProgrammeDelayEvent, delay_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Programme delay event not found")
    scope(principal, "planning.manage", row.branch_id, row.site_id)
    if row.status not in {"raised", "acknowledged"}:
        raise HTTPException(status_code=409, detail="Only raised or acknowledged delay records can be closed")
    row.status, row.closed_at = "closed", utcnow()
    audit(db, principal, "planning.delay.closed", row, branch_id=row.branch_id, site_id=row.site_id, project_id=row.project_id)
    commit(db)
    return row_dict(row)


@router.get("/approvals")
def approvals(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    anywhere(principal, "planning.view")
    rows = db.scalars(select(ApprovalRequest).where(ApprovalRequest.company_id == principal.user.company_id, ApprovalRequest.entity_type == "programme_baseline", ApprovalRequest.status == "pending").order_by(ApprovalRequest.requested_at)).all()
    result: list[dict[str, Any]] = []
    for request in rows:
        if not principal.can("planning.view", branch_id=request.branch_id, site_id=request.site_id):
            continue
        payload = row_dict(request)
        baseline = db.get(ProgrammeBaseline, int(request.entity_id))
        payload.update({"baseline_number": baseline.baseline_number if baseline else "", "project_id": baseline.project_id if baseline else None})
        result.append(payload)
    return result


@router.post("/approvals/{request_id:int}/decision")
def decide_approval(request_id: int, payload: ApprovalDecision, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    request = db.get(ApprovalRequest, request_id)
    if not request or request.company_id != principal.user.company_id or request.entity_type != "programme_baseline":
        raise HTTPException(status_code=404, detail="Programme approval request not found")
    baseline = db.get(ProgrammeBaseline, int(request.entity_id))
    if not baseline:
        raise HTTPException(status_code=404, detail="Programme baseline is unavailable")
    scope(principal, "planning.approve", baseline.branch_id, baseline.site_id)
    if request.status != "pending" or baseline.status != "submitted":
        raise HTTPException(status_code=409, detail="Programme approval request is not pending")
    step = db.scalar(select(ApprovalStep).where(ApprovalStep.workflow_id == request.workflow_id, ApprovalStep.step_order == request.current_step_order))
    if not step or not assignment_authorised(db, principal, step.role_id, baseline.branch_id, baseline.site_id):
        raise HTTPException(status_code=403, detail="Your active role assignment is not authorised for this programme approval step")
    if request.requested_by == principal.user.full_name and not allow_self_approval(db, request.company_id):
        raise HTTPException(status_code=422, detail="Self-approval is disabled by company policy")
    db.add(ApprovalAction(request_id=request.id, step_order=step.step_order, role_id=step.role_id, actor_name=principal.user.full_name, action=payload.decision, comment=payload.comment))
    if payload.decision == "reject":
        request.status, request.completed_at, baseline.status = "rejected", utcnow(), "rejected"
    else:
        approved = (db.scalar(select(func.count()).select_from(ApprovalAction).where(ApprovalAction.request_id == request.id, ApprovalAction.step_order == step.step_order, ApprovalAction.action == "approve")) or 0) + 1
        if approved >= step.required_approvals:
            next_step = db.scalar(select(ApprovalStep).where(ApprovalStep.workflow_id == request.workflow_id, ApprovalStep.step_order > step.step_order).order_by(ApprovalStep.step_order).limit(1))
            if next_step:
                request.current_step_order = next_step.step_order
            else:
                request.status, request.completed_at, baseline.status, baseline.approved_at = "approved", utcnow(), "approved", utcnow()
                prior = db.scalars(select(ProgrammeBaseline).where(ProgrammeBaseline.project_id == baseline.project_id, ProgrammeBaseline.status == "approved", ProgrammeBaseline.id != baseline.id)).all()
                for old in prior:
                    old.status, old.superseded_at = "superseded", utcnow()
    audit(db, principal, f"planning.approval.{payload.decision}", request, branch_id=baseline.branch_id, site_id=baseline.site_id, project_id=baseline.project_id, detail={"baseline_id": baseline.id, "approval_status": request.status, "step": step.step_order})
    commit(db)
    return row_dict(request)


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    anywhere(principal, "planning.view")
    baselines = [row for row in db.scalars(select(ProgrammeBaseline).where(ProgrammeBaseline.company_id == principal.user.company_id)).all() if principal.can("planning.view", branch_id=row.branch_id, site_id=row.site_id)]
    approved = [row for row in baselines if row.status == "approved"]
    metrics = [programme_metrics(db, row) for row in approved]
    lookahead_rows = [row for row in db.scalars(select(ProgrammeLookaheadItem).where(ProgrammeLookaheadItem.company_id == principal.user.company_id)).all() if principal.can("planning.view", branch_id=row.branch_id, site_id=row.site_id)]
    delay_rows = [row for row in db.scalars(select(ProgrammeDelayEvent).where(ProgrammeDelayEvent.company_id == principal.user.company_id)).all() if principal.can("planning.view", branch_id=row.branch_id, site_id=row.site_id)]
    today = date.today()
    warning = int(policy(db, principal.user.company_id)["delay_notice_warning_days"])
    return {"approved_baselines": len(approved), "draft_baselines": sum(row.status in {"draft", "rejected"} for row in baselines), "pending_baselines": sum(row.status == "submitted" for row in baselines), "activities_delayed": sum(int(row["delayed_count"]) for row in metrics), "lookahead_blocked": sum(row.status == "blocked" for row in lookahead_rows), "lookahead_due": sum(row.status in {"ready", "in_progress"} and row.planned_start <= today + timedelta(days=7) for row in lookahead_rows), "delays_open": sum(row.status in {"draft", "raised", "acknowledged"} for row in delay_rows), "delay_notices_due": sum(row.status in {"draft", "raised", "acknowledged"} and row.notice_due_date is not None and row.notice_due_date <= today + timedelta(days=warning) for row in delay_rows), "portfolio_planned_progress_pct": str((sum((Decimal(row["planned_progress_pct"]) for row in metrics), Decimal("0")) / Decimal(len(metrics))).quantize(Decimal("0.001")) if metrics else Decimal("0")), "portfolio_actual_progress_pct": str((sum((Decimal(row["actual_progress_pct"]) for row in metrics), Decimal("0")) / Decimal(len(metrics))).quantize(Decimal("0.001")) if metrics else Decimal("0"))}


@router.get("/exports/activities.csv")
def export_activities(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> StreamingResponse:
    anywhere(principal, "planning.export")
    stream = io.StringIO()
    fields = ["baseline_number", "project_number", "wbs_code", "name", "planned_start", "planned_finish", "critical", "planned_progress_pct", "actual_progress_pct", "variance_pct", "late"]
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    rows = db.scalars(select(ProgrammeBaseline).where(ProgrammeBaseline.company_id == principal.user.company_id, ProgrammeBaseline.status == "approved")).all()
    for baseline in rows:
        if not principal.can("planning.export", branch_id=baseline.branch_id, site_id=baseline.site_id):
            continue
        data = baseline_payload(db, baseline, include_activities=True)
        for activity in data["activities"]:
            writer.writerow({"baseline_number": baseline.baseline_number, "project_number": data["project_number"], **{key: activity.get(key, "") for key in fields if key not in {"baseline_number", "project_number"}}})
    return StreamingResponse(iter([stream.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=programme-activities.csv"})


@router.get("/audit")
def audit_events(limit: int = Query(default=250, ge=1, le=1000), db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    anywhere(principal, "planning.view")
    rows = db.scalars(select(PlanningAuditEvent).where(PlanningAuditEvent.company_id == principal.user.company_id).order_by(PlanningAuditEvent.occurred_at.desc()).limit(limit)).all()
    return [row_dict(row) for row in rows if row.branch_id is None or principal.can("planning.view", branch_id=row.branch_id, site_id=row.site_id)]
