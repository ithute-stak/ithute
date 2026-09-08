from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import (
    ApprovalAction,
    ApprovalRequest,
    ApprovalStep,
    ApprovalWorkflow,
    Branch,
    CompanySetting,
    CostCentre,
    Document,
    Employee,
    FleetAsset,
    NumberSequence,
    Permission,
    Project,
    ProjectAssetAllocation,
    ProjectAuditEvent,
    ProjectBudgetBaseline,
    ProjectBudgetLine,
    ProjectHandoverDocument,
    ProjectMilestone,
    ProjectMobilisationItem,
    ProjectReadinessSnapshot,
    ProjectRisk,
    ProjectSiteLink,
    ProjectTeamMember,
    Role,
    RolePermission,
    Site,
    Tender,
    TenderEstimateItem,
    TenderOutcome,
    TenderSubmission,
    TenderTeamMember,
    UserRoleAssignment,
)
from app.security.access import Principal, current_principal

router = APIRouter(prefix="/projects", tags=["Phase 6 - Project Mobilisation"])
MONEY = Decimal("0.01")
PROJECT_PERMISSION_ACTIONS = ("view", "manage", "approve", "mobilise", "budget", "team", "assets", "programme", "export")
PROJECT_POLICY_DEFAULT = {
    "mobilisation_warning_days": 7,
    "critical_risk_threshold": 16,
    "programme_weight_pct": 100,
    "require_budget_approval": True,
    "require_readiness_approval": True,
}
MOBILISATION_CHECKLIST = (
    ("site", "Site possession / access confirmed", True),
    ("client", "Client kick-off and communication protocol confirmed", True),
    ("hse", "Project HSE mobilisation plan approved", True),
    ("commercial", "Required contract securities / insurances transferred to project", True),
    ("regulatory", "Required permits and licences available", True),
    ("procurement", "Initial procurement and subcontract strategy agreed", True),
    ("facilities", "Temporary facilities, utilities and welfare plan", False),
)
HANDOVER_DOCUMENTS = (
    ("award_contract", "Award letter / signed contract", True),
    ("tender_submission", "Controlled tender submission / acknowledgement", True),
    ("priced_boq", "Priced BOQ / commercial submission", True),
    ("drawings_specs", "Issued drawings and specifications", True),
    ("client_hse", "Client HSE / project requirements", True),
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def money(value: Decimal | int | float | str | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def row_dict(row: Any) -> dict[str, Any]:
    return {column.name: json_value(getattr(row, column.name)) for column in row.__table__.columns}


def commit(db: Session, detail: str = "Project mobilisation conflicts with an existing record") -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=detail) from exc


def require_anywhere(principal: Principal, permission: str) -> None:
    if not principal.has_permission_anywhere(permission):
        raise HTTPException(status_code=403, detail=f"Permission required: {permission}")


def require_scope(principal: Principal, permission: str, branch_id: int, site_id: int | None = None) -> None:
    if not principal.can(permission, branch_id=branch_id, site_id=site_id):
        raise HTTPException(status_code=403, detail=f"Permission required in this project scope: {permission}")


def project_policy(db: Session, company_id: int) -> dict[str, Any]:
    row = db.scalar(select(CompanySetting).where(CompanySetting.company_id == company_id, CompanySetting.key == "project_policy"))
    value = dict(PROJECT_POLICY_DEFAULT)
    if row and isinstance(row.value, dict):
        value.update(row.value)
    value["require_budget_approval"] = True
    value["require_readiness_approval"] = True
    return value


def approval_setting(db: Session, company_id: int) -> dict[str, Any]:
    row = db.scalar(select(CompanySetting).where(CompanySetting.company_id == company_id, CompanySetting.key == "approval_control"))
    return row.value if row and isinstance(row.value, dict) else {"allow_self_approval": False}


def audit(db: Session, principal: Principal, action: str, entity_type: str, entity_id: Any | None, *, project: Project | None = None, detail: dict[str, Any] | None = None) -> None:
    db.add(
        ProjectAuditEvent(
            company_id=principal.user.company_id,
            project_id=project.id if project else None,
            branch_id=project.branch_id if project else None,
            site_id=project.primary_site_id if project else None,
            actor_user_id=principal.user.id,
            actor_name=principal.user.full_name,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            detail=detail or {},
        )
    )


def issue_reference(db: Session, company_id: int, sequence_code: str, fallback_prefix: str) -> str:
    sequence = db.scalar(select(NumberSequence).where(NumberSequence.company_id == company_id, NumberSequence.code == sequence_code).with_for_update())
    if not sequence:
        sequence = NumberSequence(company_id=company_id, code=sequence_code, name=sequence_code.replace("_", " ").title(), prefix=fallback_prefix, padding=5, reset_period="yearly")
        db.add(sequence)
        db.flush()
    now = utcnow()
    reset_key = now.strftime("%Y") if sequence.reset_period == "yearly" else now.strftime("%Y%m") if sequence.reset_period == "monthly" else None
    if reset_key and sequence.last_reset_key != reset_key:
        sequence.next_number = 1
        sequence.last_reset_key = reset_key
    current = sequence.next_number
    sequence.next_number += 1
    period = f"-{reset_key}" if reset_key else ""
    return f"{sequence.prefix}{period}-{current:0{sequence.padding}d}"


def project_or_404(db: Session, principal: Principal, project_id: int, permission: str = "projects.view") -> Project:
    project = db.get(Project, project_id)
    if not project or project.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Project not found")
    require_scope(principal, permission, project.branch_id, project.primary_site_id)
    return project


def ensure_project_editable(project: Project) -> None:
    if project.readiness_status in {"pending", "ready"} or project.status == "ready":
        raise HTTPException(status_code=409, detail="Project mobilisation baseline is frozen while readiness approval is pending or after readiness is approved")


def ensure_employee(db: Session, company_id: int, branch_id: int, employee_id: int | None) -> Employee | None:
    if employee_id is None:
        return None
    employee = db.get(Employee, employee_id)
    if not employee or employee.company_id != company_id:
        raise HTTPException(status_code=422, detail="Employee does not belong to this company")
    if employee.branch_id != branch_id:
        raise HTTPException(status_code=422, detail="Project team employee must belong to the project branch")
    if employee.employment_status not in {"active", "probation", "notice"}:
        raise HTTPException(status_code=422, detail="Inactive employee cannot be mobilised to a project")
    return employee


def ensure_document(db: Session, company_id: int, document_id: int | None) -> Document | None:
    if document_id is None:
        return None
    document = db.get(Document, document_id)
    if not document or document.company_id != company_id:
        raise HTTPException(status_code=422, detail="Document does not belong to this company")
    return document


def current_budget(db: Session, project_id: int) -> ProjectBudgetBaseline | None:
    return db.scalar(select(ProjectBudgetBaseline).where(ProjectBudgetBaseline.project_id == project_id).order_by(ProjectBudgetBaseline.version.desc()).limit(1))


def approved_budget(db: Session, project_id: int) -> ProjectBudgetBaseline | None:
    return db.scalar(select(ProjectBudgetBaseline).where(ProjectBudgetBaseline.project_id == project_id, ProjectBudgetBaseline.status == "approved").order_by(ProjectBudgetBaseline.version.desc()).limit(1))


def recalc_budget(db: Session, baseline: ProjectBudgetBaseline) -> None:
    total = db.scalar(select(func.coalesce(func.sum(ProjectBudgetLine.amount), 0)).where(ProjectBudgetLine.baseline_id == baseline.id)) or Decimal("0")
    baseline.total_amount = money(total)


def assignment_authorised(db: Session, principal: Principal, role_id: int, project: Project) -> bool:
    now = utcnow()
    role = db.get(Role, role_id)
    if not role:
        return False
    rows = db.scalars(select(UserRoleAssignment).where(UserRoleAssignment.user_id == principal.user.id, UserRoleAssignment.role_id == role_id)).all()
    for assignment in rows:
        if assignment.valid_from and assignment.valid_from > now:
            continue
        if assignment.valid_until and assignment.valid_until < now:
            continue
        if role.scope_level == "company":
            return True
        if role.scope_level == "branch" and assignment.branch_id == project.branch_id:
            return True
        if role.scope_level == "site" and assignment.site_id == project.primary_site_id:
            return True
    return False


def workflow(db: Session, company_id: int, code: str) -> ApprovalWorkflow:
    row = db.scalar(select(ApprovalWorkflow).where(ApprovalWorkflow.company_id == company_id, ApprovalWorkflow.code == code, ApprovalWorkflow.is_active.is_(True)))
    if not row:
        raise HTTPException(status_code=409, detail=f"Approval workflow {code} is not configured")
    if not db.scalar(select(func.count()).select_from(ApprovalStep).where(ApprovalStep.workflow_id == row.id)):
        raise HTTPException(status_code=409, detail=f"Approval workflow {code} has no steps")
    return row


def create_approval(db: Session, principal: Principal, project: Project, code: str, entity_type: str, entity_id: str, title: str, amount: Decimal | None = None) -> ApprovalRequest:
    selected = workflow(db, project.company_id, code)
    request = ApprovalRequest(
        company_id=project.company_id,
        workflow_id=selected.id,
        branch_id=project.branch_id,
        site_id=project.primary_site_id,
        entity_type=entity_type,
        entity_id=entity_id,
        reference=issue_reference(db, project.company_id, "APPROVAL", "APR"),
        title=title,
        amount=amount,
        status="pending",
        current_step_order=1,
        requested_by=principal.user.full_name,
    )
    db.add(request)
    db.flush()
    return request


def readiness_state(db: Session, project: Project) -> dict[str, Any]:
    policy = project_policy(db, project.company_id)
    blockers: list[str] = []
    baseline = approved_budget(db, project.id)
    if not baseline or baseline.total_amount <= 0:
        blockers.append("Approved project budget baseline is required")
    milestones = db.scalars(select(ProjectMilestone).where(ProjectMilestone.project_id == project.id)).all()
    if not milestones:
        blockers.append("Baseline project programme requires at least one milestone")
    else:
        total_weight = sum((Decimal(item.weight_pct or 0) for item in milestones), Decimal("0"))
        required_weight = Decimal(str(policy.get("programme_weight_pct", 100)))
        if abs(total_weight - required_weight) > Decimal("0.001"):
            blockers.append(f"Programme milestone weights must total {required_weight}% (currently {total_weight}%)")
    missing_mob = db.scalar(select(func.count()).select_from(ProjectMobilisationItem).where(ProjectMobilisationItem.project_id == project.id, ProjectMobilisationItem.required.is_(True), ProjectMobilisationItem.status != "ready")) or 0
    if missing_mob:
        blockers.append(f"{missing_mob} required mobilisation checklist item(s) are not ready")
    missing_docs = db.scalar(select(func.count()).select_from(ProjectHandoverDocument).where(ProjectHandoverDocument.project_id == project.id, ProjectHandoverDocument.required.is_(True), ProjectHandoverDocument.status != "verified")) or 0
    if missing_docs:
        blockers.append(f"{missing_docs} required handover document(s) are not verified")
    if not project.project_manager_employee_id:
        blockers.append("Project manager must be assigned")
    else:
        manager_team = db.scalar(select(ProjectTeamMember).where(ProjectTeamMember.project_id == project.id, ProjectTeamMember.employee_id == project.project_manager_employee_id, ProjectTeamMember.role == "project_manager", ProjectTeamMember.status != "released"))
        if not manager_team:
            blockers.append("Project manager must be present in the active project team")
    threshold = int(policy.get("critical_risk_threshold", 16))
    critical = db.scalar(select(func.count()).select_from(ProjectRisk).where(ProjectRisk.project_id == project.id, ProjectRisk.rating >= threshold, ProjectRisk.status == "open")) or 0
    if critical:
        blockers.append(f"{critical} critical/open mobilisation risk(s) require mitigation")
    planned_assets = db.scalar(select(func.count()).select_from(ProjectAssetAllocation).where(ProjectAssetAllocation.project_id == project.id, ProjectAssetAllocation.status == "planned")) or 0
    if planned_assets:
        blockers.append(f"{planned_assets} planned fleet/plant allocation(s) are not confirmed")
    confirmed_assets = db.scalars(select(ProjectAssetAllocation).where(ProjectAssetAllocation.project_id == project.id, ProjectAssetAllocation.status == "confirmed")).all()
    for allocation in confirmed_assets:
        asset = db.get(FleetAsset, allocation.asset_id)
        if not asset or asset.serviceability == "unserviceable" or asset.status in {"out_of_service", "disposed"}:
            blockers.append(f"Allocated fleet/plant asset {allocation.asset_id} is not serviceable")
    return {
        "ready": not blockers,
        "blockers": blockers,
        "approved_budget_version": baseline.version if baseline else None,
        "approved_budget": str(baseline.total_amount) if baseline else "0.00",
        "milestone_count": len(milestones),
        "required_checklist_missing": int(missing_mob),
        "required_documents_missing": int(missing_docs),
        "critical_open_risks": int(critical),
        "planned_assets_unconfirmed": int(planned_assets),
    }


def snapshot_payload(db: Session, project: Project) -> dict[str, Any]:
    baseline = approved_budget(db, project.id)
    lines = db.scalars(select(ProjectBudgetLine).where(ProjectBudgetLine.baseline_id == baseline.id).order_by(ProjectBudgetLine.id)).all() if baseline else []
    return {
        "snapshot_schema": 1,
        "phase": 6,
        "captured_at": utcnow().isoformat(),
        "project": row_dict(project),
        "sites": [row_dict(row) for row in db.scalars(select(ProjectSiteLink).where(ProjectSiteLink.project_id == project.id).order_by(ProjectSiteLink.is_primary.desc(), ProjectSiteLink.id)).all()],
        "team": [row_dict(row) for row in db.scalars(select(ProjectTeamMember).where(ProjectTeamMember.project_id == project.id, ProjectTeamMember.status != "released").order_by(ProjectTeamMember.role, ProjectTeamMember.id)).all()],
        "budget": {"baseline": row_dict(baseline) if baseline else None, "lines": [row_dict(row) for row in lines]},
        "programme": [row_dict(row) for row in db.scalars(select(ProjectMilestone).where(ProjectMilestone.project_id == project.id).order_by(ProjectMilestone.planned_start, ProjectMilestone.id)).all()],
        "mobilisation": [row_dict(row) for row in db.scalars(select(ProjectMobilisationItem).where(ProjectMobilisationItem.project_id == project.id).order_by(ProjectMobilisationItem.category, ProjectMobilisationItem.id)).all()],
        "assets": [row_dict(row) for row in db.scalars(select(ProjectAssetAllocation).where(ProjectAssetAllocation.project_id == project.id, ProjectAssetAllocation.status != "released").order_by(ProjectAssetAllocation.id)).all()],
        "risks": [row_dict(row) for row in db.scalars(select(ProjectRisk).where(ProjectRisk.project_id == project.id).order_by(ProjectRisk.rating.desc(), ProjectRisk.id)).all()],
        "handover_documents": [row_dict(row) for row in db.scalars(select(ProjectHandoverDocument).where(ProjectHandoverDocument.project_id == project.id).order_by(ProjectHandoverDocument.id)).all()],
        "readiness": readiness_state(db, project),
    }


class ProjectPolicyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mobilisation_warning_days: int = Field(default=7, ge=1, le=90)
    critical_risk_threshold: int = Field(default=16, ge=1, le=25)
    programme_weight_pct: Decimal = Field(default=100, ge=1, le=100)
    require_budget_approval: bool = True
    require_readiness_approval: bool = True


class ProjectFromTenderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    site_code: str | None = Field(default=None, max_length=32)
    site_name: str | None = Field(default=None, max_length=255)
    district: str | None = Field(default=None, max_length=120)
    site_location: str | None = None
    project_manager_employee_id: int | None = None
    contract_start_date: date
    contract_completion_date: date
    mobilisation_date: date
    contract_reference: str | None = Field(default=None, max_length=180)
    project_type: str | None = Field(default=None, max_length=100)
    contingency_budget: Decimal = Field(default=Decimal("0"), ge=0)
    contract_document_id: int | None = None
    notes: str | None = None


class ProjectUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=300)
    project_manager_employee_id: int | None = None
    contract_reference: str | None = Field(default=None, max_length=180)
    project_type: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=300)
    contract_start_date: date
    contract_completion_date: date
    mobilisation_date: date
    contingency_budget: Decimal = Field(default=Decimal("0"), ge=0)
    contract_document_id: int | None = None
    notes: str | None = None


class SiteLinkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    site_id: int
    site_role: str = Field(default="work_site", min_length=2, max_length=40)


class TeamInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employee_id: int
    role: str = Field(min_length=2, max_length=80)
    allocation_pct: int = Field(default=100, ge=1, le=100)
    start_date: date | None = None
    end_date: date | None = None
    status: Literal["planned", "confirmed"] = "planned"
    notes: str | None = None


class TeamStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["planned", "confirmed", "released"]


class BudgetLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cost_code: str | None = Field(default=None, max_length=80)
    cost_type: Literal["material", "labour", "plant", "subcontract", "other", "overhead", "contingency"]
    description: str = Field(min_length=2, max_length=300)
    amount: Decimal = Field(gt=0)
    notes: str | None = None


class MilestoneInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str | None = Field(default=None, max_length=80)
    name: str = Field(min_length=2, max_length=240)
    planned_start: date
    planned_finish: date
    weight_pct: Decimal = Field(ge=0, le=100)
    predecessor_id: int | None = None
    notes: str | None = None


class MobilisationItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["pending", "in_progress", "ready", "not_applicable"]
    owner_employee_id: int | None = None
    due_date: date | None = None
    document_id: int | None = None
    notes: str | None = None


class AssetAllocationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: int
    site_id: int
    planned_from: date
    planned_to: date | None = None
    purpose: str | None = None


class AssetStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["confirmed", "released"]


class RiskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str = Field(min_length=2, max_length=80)
    title: str = Field(min_length=2, max_length=240)
    description: str | None = None
    likelihood: int = Field(ge=1, le=5)
    impact: int = Field(ge=1, le=5)
    owner_employee_id: int | None = None
    mitigation: str | None = None
    status: Literal["open", "mitigated", "closed"] = "open"
    target_date: date | None = None


class HandoverInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: int | None = None
    status: Literal["missing", "received", "verified", "not_applicable"]
    notes: str | None = None


class ApprovalDecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]
    comment: str | None = None


@router.get("/status")
def phase6_status(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_anywhere(principal, "projects.view")
    initialized = db.scalar(select(Permission.id).where(Permission.code == "projects.mobilise")) is not None
    return {"initialized": initialized, "phase": 6, "status": "operational" if initialized else "setup_required"}


@router.post("/bootstrap")
def bootstrap_phase6(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if not principal.has_company_permission("projects.manage") and not principal.has_company_permission("company.manage"):
        raise HTTPException(status_code=403, detail="Company-level project administration is required to initialise Phase 6")
    permissions: dict[str, Permission] = {}
    for action in PROJECT_PERMISSION_ACTIONS:
        code = f"projects.{action}"
        row = db.scalar(select(Permission).where(Permission.code == code))
        if not row:
            row = Permission(code=code, module="projects", action=action, description=f"{action.replace('_', ' ').title()} projects")
            db.add(row)
            db.flush()
        permissions[code] = row

    roles = {row.code: row for row in db.scalars(select(Role).where(Role.company_id == principal.user.company_id)).all()}
    for code, name, scope, description in (
        ("PROJECT_MANAGER", "Project Manager", "branch", "Mobilises and manages projects within an assigned branch"),
        ("PROJECT_CONTROLS", "Project Controls", "company", "Controls project budgets, programmes and mobilisation reporting"),
    ):
        if code not in roles:
            role = Role(company_id=principal.user.company_id, code=code, name=name, scope_level=scope, description=description, is_system=True, is_active=True)
            db.add(role); db.flush(); roles[code] = role

    grants: dict[str, set[str]] = {
        "SYSTEM_ADMIN": {f"projects.{a}" for a in PROJECT_PERMISSION_ACTIONS},
        "HQ_EXECUTIVE": {"projects.view", "projects.approve", "projects.export", "projects.budget", "projects.programme"},
        "BRANCH_MANAGER": {"projects.view", "projects.manage", "projects.mobilise", "projects.budget", "projects.team", "projects.assets", "projects.programme", "projects.export"},
        "SITE_MANAGER": {"projects.view", "projects.team", "projects.assets", "projects.programme"},
        "APPROVER": {"projects.approve"},
        "AUDITOR": {"projects.view", "projects.export"},
        "PROJECT_MANAGER": {"projects.view", "projects.manage", "projects.mobilise", "projects.budget", "projects.team", "projects.assets", "projects.programme", "projects.export"},
        "PROJECT_CONTROLS": {"projects.view", "projects.budget", "projects.programme", "projects.export"},
    }
    for role_code, codes in grants.items():
        role = roles.get(role_code)
        if not role:
            continue
        existing = set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id == role.id)).all())
        for code in codes:
            permission = permissions.get(code)
            if permission and permission.id not in existing:
                db.add(RolePermission(role_id=role.id, permission_id=permission.id))

    for sequence_code, name, prefix in (("PROJECT_RISK", "Project Risk Number", "RSK"),):
        if not db.scalar(select(NumberSequence).where(NumberSequence.company_id == principal.user.company_id, NumberSequence.code == sequence_code)):
            db.add(NumberSequence(company_id=principal.user.company_id, code=sequence_code, name=name, prefix=prefix, padding=5, reset_period="yearly"))

    for code, name in (("PROJECT_BUDGET_BASELINE", "Project Budget Baseline Approval"), ("PROJECT_MOBILISATION", "Project Mobilisation Readiness Approval")):
        wf = db.scalar(select(ApprovalWorkflow).where(ApprovalWorkflow.company_id == principal.user.company_id, ApprovalWorkflow.code == code))
        if not wf:
            wf = ApprovalWorkflow(company_id=principal.user.company_id, code=code, name=name, module="projects", description=f"Controlled {name.lower()} workflow", min_amount=Decimal("0"), is_active=True)
            db.add(wf); db.flush()
        if not db.scalar(select(func.count()).select_from(ApprovalStep).where(ApprovalStep.workflow_id == wf.id)):
            branch_role = roles.get("BRANCH_MANAGER")
            hq_role = roles.get("HQ_EXECUTIVE")
            if not branch_role or not hq_role:
                raise HTTPException(status_code=409, detail="Core Branch Manager and HQ Executive roles are required")
            db.add_all([
                ApprovalStep(workflow_id=wf.id, step_order=1, name="Branch Mobilisation Review", role_id=branch_role.id, required_approvals=1, escalation_hours=24),
                ApprovalStep(workflow_id=wf.id, step_order=2, name="Head Office Approval", role_id=hq_role.id, required_approvals=1, escalation_hours=48),
            ])

    setting = db.scalar(select(CompanySetting).where(CompanySetting.company_id == principal.user.company_id, CompanySetting.key == "project_policy"))
    if not setting:
        db.add(CompanySetting(company_id=principal.user.company_id, key="project_policy", value=dict(PROJECT_POLICY_DEFAULT), description="Phase 6 project mobilisation governance"))
    audit(db, principal, "project.phase6.bootstrap", "company", principal.user.company_id, detail={"permissions": len(PROJECT_PERMISSION_ACTIONS)})
    commit(db)
    return {"initialized": True, "phase": 6, "message": "Project Mobilisation controls initialised"}


@router.get("/catalog")
def project_catalog(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_anywhere(principal, "projects.view")
    company_id = principal.user.company_id
    branches = [row for row in db.scalars(select(Branch).where(Branch.company_id == company_id, Branch.is_active.is_(True)).order_by(Branch.name)).all() if principal.can("projects.view", branch_id=row.id)]
    sites = [row for row in db.scalars(select(Site).where(Site.company_id == company_id, Site.is_active.is_(True)).order_by(Site.name)).all() if principal.can("projects.view", branch_id=row.branch_id, site_id=row.id)]
    employees = [row for row in db.scalars(select(Employee).where(Employee.company_id == company_id, Employee.employment_status.in_(["active", "probation", "notice"])).order_by(Employee.last_name, Employee.first_name)).all() if principal.can("projects.view", branch_id=row.branch_id, site_id=row.site_id)]
    assets = [row for row in db.scalars(select(FleetAsset).where(FleetAsset.company_id == company_id, FleetAsset.status.not_in(["disposed"])).order_by(FleetAsset.asset_number)).all() if principal.has_company_permission("projects.assets") or principal.can("projects.assets", branch_id=row.branch_id, site_id=row.site_id)]
    existing_tender_ids = set(db.scalars(select(Project.tender_id).where(Project.company_id == company_id, Project.tender_id.is_not(None))).all())
    awarded = [row for row in db.scalars(select(Tender).where(Tender.company_id == company_id, Tender.status == "awarded").order_by(Tender.id.desc())).all() if row.id not in existing_tender_ids and principal.can("projects.mobilise", branch_id=row.branch_id, site_id=row.site_id)]
    documents = [row for row in db.scalars(select(Document).where(Document.company_id == company_id, Document.is_active.is_(True)).order_by(Document.id.desc()).limit(500)).all() if row.branch_id is None or principal.can("projects.view", branch_id=row.branch_id, site_id=row.site_id)]
    return {
        "branches": [row_dict(row) for row in branches],
        "sites": [row_dict(row) for row in sites],
        "employees": [{"id": row.id, "employee_number": row.employee_number, "branch_id": row.branch_id, "site_id": row.site_id, "name": f"{row.first_name} {row.last_name}", "job_title": row.job_title} for row in employees],
        "assets": [{"id": row.id, "asset_number": row.asset_number, "branch_id": row.branch_id, "site_id": row.site_id, "name": f"{row.make} {row.model}", "asset_type": row.asset_type, "status": row.status, "serviceability": row.serviceability} for row in assets],
        "awarded_tenders": [{"id": row.id, "tender_number": row.tender_number, "branch_id": row.branch_id, "title": row.title, "client_name": row.client_name, "tender_price": str(row.tender_price)} for row in awarded],
        "documents": [{"id": row.id, "branch_id": row.branch_id, "site_id": row.site_id, "title": row.title, "category": row.category} for row in documents],
        "permissions": sorted(code for code in principal.permission_codes if code.startswith("projects.")),
    }


@router.get("/dashboard/summary")
def project_dashboard(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_anywhere(principal, "projects.view")
    rows = [row for row in db.scalars(select(Project).where(Project.company_id == principal.user.company_id)).all() if principal.can("projects.view", branch_id=row.branch_id, site_id=row.primary_site_id)]
    awarded = db.scalars(select(Tender).where(Tender.company_id == principal.user.company_id, Tender.status == "awarded")).all()
    converted = {row.tender_id for row in rows if row.tender_id is not None}
    backlog = [row for row in awarded if row.id not in converted and principal.can("projects.mobilise", branch_id=row.branch_id, site_id=row.site_id)]
    return {
        "total": len(rows),
        "mobilising": sum(row.status == "mobilising" for row in rows),
        "readiness_pending": sum(row.readiness_status == "pending" for row in rows),
        "ready": sum(row.status == "ready" for row in rows),
        "contract_value": str(money(sum((Decimal(row.contract_amount or 0) for row in rows), Decimal("0")))),
        "approved_baseline_budget": str(money(sum((Decimal(row.baseline_budget or 0) for row in rows), Decimal("0")))),
        "awarded_tenders_waiting": len(backlog),
    }


@router.get("/dashboard/alerts")
def project_alerts(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    require_anywhere(principal, "projects.view")
    policy = project_policy(db, principal.user.company_id)
    warning = date.today() + timedelta(days=int(policy.get("mobilisation_warning_days", 7)))
    threshold = int(policy.get("critical_risk_threshold", 16))
    result: list[dict[str, Any]] = []
    projects = [row for row in db.scalars(select(Project).where(Project.company_id == principal.user.company_id, Project.status != "ready")).all() if principal.can("projects.view", branch_id=row.branch_id, site_id=row.primary_site_id)]
    for project in projects:
        if project.mobilisation_date <= warning:
            result.append({"project_id": project.id, "project_number": project.project_number, "severity": "critical" if project.mobilisation_date < date.today() else "warning", "type": "mobilisation_date", "message": f"Mobilisation date {project.mobilisation_date.isoformat()}"})
        state = readiness_state(db, project)
        if state["required_checklist_missing"]:
            result.append({"project_id": project.id, "project_number": project.project_number, "severity": "warning", "type": "checklist", "message": f"{state['required_checklist_missing']} required mobilisation item(s) incomplete"})
        if state["required_documents_missing"]:
            result.append({"project_id": project.id, "project_number": project.project_number, "severity": "warning", "type": "handover", "message": f"{state['required_documents_missing']} required handover document(s) unverified"})
        if state["critical_open_risks"]:
            result.append({"project_id": project.id, "project_number": project.project_number, "severity": "critical", "type": "risk", "message": f"{state['critical_open_risks']} open risk(s) at or above rating {threshold}"})
    return result


@router.get("/policy/current")
def get_project_policy(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_anywhere(principal, "projects.view")
    value = project_policy(db, principal.user.company_id)
    return {**value, "can_edit": principal.has_company_permission("projects.manage") or principal.has_company_permission("company.manage")}


@router.put("/policy/current")
def set_project_policy(payload: ProjectPolicyInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if not principal.has_company_permission("projects.manage") and not principal.has_company_permission("company.manage"):
        raise HTTPException(status_code=403, detail="Company-level project administration is required")
    value = payload.model_dump(mode="json")
    value["require_budget_approval"] = True
    value["require_readiness_approval"] = True
    row = db.scalar(select(CompanySetting).where(CompanySetting.company_id == principal.user.company_id, CompanySetting.key == "project_policy"))
    if row:
        row.value = value
    else:
        db.add(CompanySetting(company_id=principal.user.company_id, key="project_policy", value=value, description="Phase 6 project mobilisation governance"))
    audit(db, principal, "project.policy.updated", "company_setting", "project_policy", detail=value)
    commit(db)
    return {**value, "can_edit": True}


@router.get("/exports/projects.csv")
def export_projects(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> StreamingResponse:
    require_anywhere(principal, "projects.export")
    output = io.StringIO(); writer = csv.writer(output)
    writer.writerow(["Project Number", "Tender ID", "Project", "Client", "Branch ID", "Site ID", "Contract Start", "Completion", "Status", "Readiness", "Contract Amount", "Approved Baseline Budget"])
    for project in db.scalars(select(Project).where(Project.company_id == principal.user.company_id).order_by(Project.project_number)).all():
        if principal.can("projects.export", branch_id=project.branch_id, site_id=project.primary_site_id):
            writer.writerow([project.project_number, project.tender_id or "", project.name, project.client_name, project.branch_id, project.primary_site_id, project.contract_start_date, project.contract_completion_date, project.status, project.readiness_status, project.contract_amount, project.baseline_budget])
    return StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=buildtrack-project-mobilisation.csv"})


@router.get("/approvals/pending")
def pending_project_approvals(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    require_anywhere(principal, "projects.approve")
    rows = db.scalars(select(ApprovalRequest).where(ApprovalRequest.company_id == principal.user.company_id, ApprovalRequest.entity_type.in_(["project_budget", "project_mobilisation"]), ApprovalRequest.status == "pending").order_by(ApprovalRequest.requested_at)).all()
    result = []
    for request in rows:
        if request.entity_type == "project_budget":
            baseline = db.get(ProjectBudgetBaseline, int(request.entity_id)); project = db.get(Project, baseline.project_id) if baseline else None
        else:
            project = db.get(Project, int(request.entity_id))
        if project and principal.can("projects.approve", branch_id=project.branch_id, site_id=project.primary_site_id):
            result.append({**row_dict(request), "project_id": project.id, "project_number": project.project_number, "project_name": project.name})
    return result


@router.get("/audit/events")
def project_audit_events(db: Session = Depends(get_db), principal: Principal = Depends(current_principal), limit: int = Query(default=200, ge=1, le=1000)) -> list[dict[str, Any]]:
    require_anywhere(principal, "projects.view")
    rows = db.scalars(select(ProjectAuditEvent).where(ProjectAuditEvent.company_id == principal.user.company_id).order_by(ProjectAuditEvent.occurred_at.desc()).limit(limit)).all()
    return [row_dict(row) for row in rows if row.branch_id is None or principal.can("projects.view", branch_id=row.branch_id, site_id=row.site_id)]


@router.post("/approvals/{request_id}/decision")
def decide_project_approval(request_id: int, payload: ApprovalDecisionInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    request = db.get(ApprovalRequest, request_id)
    if not request or request.company_id != principal.user.company_id or request.entity_type not in {"project_budget", "project_mobilisation"}:
        raise HTTPException(status_code=404, detail="Project approval request not found")
    if request.entity_type == "project_budget":
        baseline = db.get(ProjectBudgetBaseline, int(request.entity_id))
        if not baseline:
            raise HTTPException(status_code=404, detail="Project budget baseline not found")
        project = project_or_404(db, principal, baseline.project_id, "projects.approve")
    else:
        baseline = None
        project = project_or_404(db, principal, int(request.entity_id), "projects.approve")
    if request.status != "pending":
        raise HTTPException(status_code=409, detail=f"Approval request is already {request.status}")
    step = db.scalar(select(ApprovalStep).where(ApprovalStep.workflow_id == request.workflow_id, ApprovalStep.step_order == request.current_step_order))
    if not step:
        raise HTTPException(status_code=409, detail="Current approval step is not configured")
    if not assignment_authorised(db, principal, step.role_id, project):
        raise HTTPException(status_code=403, detail="Your active role assignment is not authorised for this approval step")
    if request.requested_by == principal.user.full_name and not bool(approval_setting(db, project.company_id).get("allow_self_approval", False)):
        raise HTTPException(status_code=422, detail="Self-approval is disabled by company approval policy")
    if payload.decision == "approve" and request.entity_type == "project_mobilisation":
        state = readiness_state(db, project)
        if not state["ready"]:
            raise HTTPException(status_code=409, detail={"message": "Project is no longer ready for mobilisation approval", "blockers": state["blockers"]})
    db.add(ApprovalAction(request_id=request.id, step_order=step.step_order, role_id=step.role_id, actor_name=principal.user.full_name, action=payload.decision, comment=payload.comment))
    if payload.decision == "reject":
        request.status = "rejected"; request.completed_at = utcnow()
    else:
        approved_count = (db.scalar(select(func.count()).select_from(ApprovalAction).where(ApprovalAction.request_id == request.id, ApprovalAction.step_order == step.step_order, ApprovalAction.action == "approve")) or 0) + 1
        if approved_count >= step.required_approvals:
            next_step = db.scalar(select(ApprovalStep).where(ApprovalStep.workflow_id == request.workflow_id, ApprovalStep.step_order > step.step_order).order_by(ApprovalStep.step_order).limit(1))
            if next_step:
                request.current_step_order = next_step.step_order
            else:
                request.status = "approved"; request.completed_at = utcnow()
    if baseline:
        if request.status == "rejected":
            baseline.status = "rejected"
        elif request.status == "approved":
            for previous in db.scalars(select(ProjectBudgetBaseline).where(ProjectBudgetBaseline.project_id == project.id, ProjectBudgetBaseline.status == "approved", ProjectBudgetBaseline.id != baseline.id)).all():
                previous.status = "superseded"
            baseline.status = "approved"; baseline.approved_at = utcnow(); project.baseline_budget = baseline.total_amount
    else:
        if request.status == "rejected":
            project.readiness_status = "rejected"
        elif request.status == "approved":
            snapshot = ProjectReadinessSnapshot(
                company_id=project.company_id,
                project_id=project.id,
                version=(db.scalar(select(func.max(ProjectReadinessSnapshot.version)).where(ProjectReadinessSnapshot.project_id == project.id)) or 0) + 1,
                approval_request_id=request.id,
                snapshot=snapshot_payload(db, project),
                created_by=principal.user.full_name,
            )
            db.add(snapshot)
            project.readiness_status = "ready"; project.status = "ready"
    audit(db, principal, f"project.approval.{payload.decision}", "approval_request", request.id, project=project, detail={"entity_type": request.entity_type, "status": request.status, "step": step.step_order})
    commit(db)
    return row_dict(request)


@router.get("")
def list_projects(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    require_anywhere(principal, "projects.view")
    rows = db.scalars(select(Project).where(Project.company_id == principal.user.company_id).order_by(Project.id.desc())).all()
    return [row_dict(row) for row in rows if principal.can("projects.view", branch_id=row.branch_id, site_id=row.primary_site_id)]


@router.post("/from-tender/{tender_id}", status_code=status.HTTP_201_CREATED)
def create_project_from_tender(tender_id: int, payload: ProjectFromTenderInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if db.scalar(select(Permission.id).where(Permission.code == "projects.mobilise")) is None:
        raise HTTPException(status_code=409, detail="Phase 6 must be initialised before mobilising projects")
    tender = db.get(Tender, tender_id)
    if not tender or tender.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Awarded tender not found")
    require_scope(principal, "projects.mobilise", tender.branch_id, tender.site_id)
    if tender.status != "awarded":
        raise HTTPException(status_code=409, detail="Only an awarded tender can be mobilised")
    if db.scalar(select(Project.id).where(Project.tender_id == tender.id)):
        raise HTTPException(status_code=409, detail="This tender has already been converted to a project")
    outcome = db.scalar(select(TenderOutcome).where(TenderOutcome.tender_id == tender.id, TenderOutcome.outcome == "awarded"))
    submission = db.scalar(select(TenderSubmission).where(TenderSubmission.tender_id == tender.id).order_by(TenderSubmission.version.desc()).limit(1))
    if not outcome or not submission:
        raise HTTPException(status_code=409, detail="Awarded tender must have controlled outcome and submission evidence")
    if payload.contract_completion_date <= payload.contract_start_date:
        raise HTTPException(status_code=422, detail="Contract completion date must be after contract start date")
    if payload.mobilisation_date > payload.contract_completion_date:
        raise HTTPException(status_code=422, detail="Mobilisation date cannot be after contract completion")
    manager_id = payload.project_manager_employee_id or tender.lead_employee_id
    manager = ensure_employee(db, tender.company_id, tender.branch_id, manager_id)
    contract_document = ensure_document(db, tender.company_id, payload.contract_document_id)
    project_number = issue_reference(db, tender.company_id, "PROJECT", "PRJ")
    site_code = (payload.site_code or project_number).strip().upper()[:32]
    if db.scalar(select(Site.id).where(Site.branch_id == tender.branch_id, Site.code == site_code)):
        raise HTTPException(status_code=409, detail=f"Site code {site_code} already exists in the project branch")
    site = Site(
        company_id=tender.company_id,
        branch_id=tender.branch_id,
        code=site_code,
        name=(payload.site_name or tender.title)[:255],
        site_type="project_site",
        district=payload.district,
        location=payload.site_location or tender.location,
        responsible_officer=f"{manager.first_name} {manager.last_name}" if manager else None,
        is_active=True,
    )
    db.add(site); db.flush()
    cost_centre = CostCentre(company_id=tender.company_id, branch_id=tender.branch_id, site_id=site.id, code=project_number[:40], name=f"{project_number} - {tender.title}"[:255], cost_centre_type="project", description=f"Project cost centre created from tender {tender.tender_number}", is_active=True)
    db.add(cost_centre); db.flush()
    contract_amount = money(outcome.awarded_amount or tender.tender_price)
    if contract_amount <= 0:
        raise HTTPException(status_code=409, detail="Awarded project must have a positive contract amount")
    project = Project(
        company_id=tender.company_id,
        tender_id=tender.id,
        source_submission_id=submission.id,
        branch_id=tender.branch_id,
        primary_site_id=site.id,
        cost_centre_id=cost_centre.id,
        project_manager_employee_id=manager_id,
        project_number=project_number,
        name=tender.title,
        client_name=tender.client_name,
        contract_reference=payload.contract_reference or tender.external_reference,
        project_type=payload.project_type or tender.category,
        location=payload.site_location or tender.location,
        contract_start_date=payload.contract_start_date,
        contract_completion_date=payload.contract_completion_date,
        mobilisation_date=payload.mobilisation_date,
        currency=tender.currency,
        contract_amount=contract_amount,
        contingency_budget=money(payload.contingency_budget),
        contract_document_id=contract_document.id if contract_document else None,
        status="mobilising",
        readiness_status="draft",
        notes=payload.notes,
        created_by=principal.user.full_name,
    )
    db.add(project); db.flush()
    db.add(ProjectSiteLink(company_id=project.company_id, project_id=project.id, site_id=site.id, site_role="primary_work_site", is_primary=True, linked_by=principal.user.full_name))
    if manager:
        db.add(ProjectTeamMember(company_id=project.company_id, project_id=project.id, employee_id=manager.id, role="project_manager", allocation_pct=100, start_date=payload.mobilisation_date, status="confirmed", added_by=principal.user.full_name))
    for tender_member in db.scalars(select(TenderTeamMember).where(TenderTeamMember.tender_id == tender.id)).all():
        if manager and tender_member.employee_id == manager.id:
            continue
        employee = db.get(Employee, tender_member.employee_id)
        if employee and employee.company_id == project.company_id and employee.branch_id == project.branch_id and employee.employment_status in {"active", "probation", "notice"}:
            db.add(ProjectTeamMember(company_id=project.company_id, project_id=project.id, employee_id=employee.id, role=f"tender_{tender_member.role}"[:80], allocation_pct=100, start_date=payload.mobilisation_date, status="planned", notes="Transferred from Phase 5 tender team", added_by=principal.user.full_name))

    baseline = ProjectBudgetBaseline(company_id=project.company_id, project_id=project.id, version=1, source="tender", status="draft", total_amount=Decimal("0"), created_by=principal.user.full_name, notes=f"Imported from controlled tender {tender.tender_number}")
    db.add(baseline); db.flush()
    imported_total = Decimal("0")
    for item in db.scalars(select(TenderEstimateItem).where(TenderEstimateItem.tender_id == tender.id).order_by(TenderEstimateItem.sort_order, TenderEstimateItem.id)).all():
        quantity = Decimal(item.quantity or 0)
        for cost_type, unit_cost in (("material", item.material_unit_cost), ("labour", item.labour_unit_cost), ("plant", item.plant_unit_cost), ("subcontract", item.subcontract_unit_cost), ("other", item.other_unit_cost)):
            amount = money(quantity * Decimal(unit_cost or 0))
            if amount <= 0:
                continue
            db.add(ProjectBudgetLine(company_id=project.company_id, project_id=project.id, baseline_id=baseline.id, source_tender_estimate_item_id=item.id, cost_code=item.item_code, cost_type=cost_type, description=f"{item.description} - {cost_type}", amount=amount))
            imported_total += amount
    if imported_total <= 0 and Decimal(tender.direct_cost_total or 0) > 0:
        imported_total = money(tender.direct_cost_total)
        db.add(ProjectBudgetLine(company_id=project.company_id, project_id=project.id, baseline_id=baseline.id, cost_type="other", description="Tender direct-cost baseline", amount=imported_total, notes="Detailed cost split was not available in Phase 5 estimate lines"))
    baseline.total_amount = money(imported_total)

    for category, name, required in MOBILISATION_CHECKLIST:
        db.add(ProjectMobilisationItem(company_id=project.company_id, project_id=project.id, category=category, name=name, required=required, status="pending", due_date=payload.mobilisation_date, updated_by=principal.user.full_name))

    source_docs = {
        "award_contract": payload.contract_document_id or outcome.award_document_id,
        "tender_submission": submission.acknowledgement_document_id,
    }
    for doc_type, title, required in HANDOVER_DOCUMENTS:
        document_id = source_docs.get(doc_type)
        if document_id:
            ensure_document(db, project.company_id, document_id)
        db.add(ProjectHandoverDocument(company_id=project.company_id, project_id=project.id, document_type=doc_type, title=title, required=required, document_id=document_id, source_phase=5 if document_id else None, source_reference=tender.tender_number if document_id else None, status="received" if document_id else "missing"))

    audit(db, principal, "project.created_from_tender", "project", project.id, project=project, detail={"project_number": project.project_number, "tender_number": tender.tender_number, "contract_amount": str(project.contract_amount), "site_id": site.id, "cost_centre_id": cost_centre.id})
    commit(db, "Project/site/cost-centre conversion conflicts with existing records")
    db.refresh(project)
    return row_dict(project)


@router.get("/{project_id}")
def project_detail(project_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    project = project_or_404(db, principal, project_id)
    baselines = db.scalars(select(ProjectBudgetBaseline).where(ProjectBudgetBaseline.project_id == project.id).order_by(ProjectBudgetBaseline.version.desc())).all()
    budget = []
    for baseline in baselines:
        budget.append({**row_dict(baseline), "lines": [row_dict(row) for row in db.scalars(select(ProjectBudgetLine).where(ProjectBudgetLine.baseline_id == baseline.id).order_by(ProjectBudgetLine.id)).all()]})
    tender = db.get(Tender, project.tender_id) if project.tender_id else None
    latest_snapshot = db.scalar(select(ProjectReadinessSnapshot).where(ProjectReadinessSnapshot.project_id == project.id).order_by(ProjectReadinessSnapshot.version.desc()).limit(1))
    return {
        **row_dict(project),
        "source_tender": row_dict(tender) if tender else None,
        "sites": [row_dict(row) for row in db.scalars(select(ProjectSiteLink).where(ProjectSiteLink.project_id == project.id).order_by(ProjectSiteLink.is_primary.desc(), ProjectSiteLink.id)).all()],
        "team": [row_dict(row) for row in db.scalars(select(ProjectTeamMember).where(ProjectTeamMember.project_id == project.id).order_by(ProjectTeamMember.status, ProjectTeamMember.role, ProjectTeamMember.id)).all()],
        "budgets": budget,
        "milestones": [row_dict(row) for row in db.scalars(select(ProjectMilestone).where(ProjectMilestone.project_id == project.id).order_by(ProjectMilestone.planned_start, ProjectMilestone.id)).all()],
        "mobilisation_items": [row_dict(row) for row in db.scalars(select(ProjectMobilisationItem).where(ProjectMobilisationItem.project_id == project.id).order_by(ProjectMobilisationItem.category, ProjectMobilisationItem.id)).all()],
        "assets": [row_dict(row) for row in db.scalars(select(ProjectAssetAllocation).where(ProjectAssetAllocation.project_id == project.id).order_by(ProjectAssetAllocation.id)).all()],
        "risks": [row_dict(row) for row in db.scalars(select(ProjectRisk).where(ProjectRisk.project_id == project.id).order_by(ProjectRisk.rating.desc(), ProjectRisk.id)).all()],
        "handover_documents": [row_dict(row) for row in db.scalars(select(ProjectHandoverDocument).where(ProjectHandoverDocument.project_id == project.id).order_by(ProjectHandoverDocument.id)).all()],
        "readiness": readiness_state(db, project),
        "readiness_snapshot": row_dict(latest_snapshot) if latest_snapshot else None,
    }


@router.put("/{project_id}")
def update_project(project_id: int, payload: ProjectUpdateInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    project = project_or_404(db, principal, project_id, "projects.manage"); ensure_project_editable(project)
    if payload.contract_completion_date <= payload.contract_start_date:
        raise HTTPException(status_code=422, detail="Contract completion date must be after contract start date")
    if payload.mobilisation_date > payload.contract_completion_date:
        raise HTTPException(status_code=422, detail="Mobilisation date cannot be after contract completion")
    manager = ensure_employee(db, project.company_id, project.branch_id, payload.project_manager_employee_id)
    document = ensure_document(db, project.company_id, payload.contract_document_id)
    for key, value in payload.model_dump(exclude={"contract_document_id", "project_manager_employee_id"}).items():
        setattr(project, key, value)
    project.project_manager_employee_id = manager.id if manager else None
    project.contract_document_id = document.id if document else None
    audit(db, principal, "project.updated", "project", project.id, project=project, detail={"manager_employee_id": project.project_manager_employee_id})
    commit(db); return row_dict(project)


@router.post("/{project_id}/sites", status_code=201)
def link_project_site(project_id: int, payload: SiteLinkInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    project = project_or_404(db, principal, project_id, "projects.manage"); ensure_project_editable(project)
    site = db.get(Site, payload.site_id)
    if not site or site.company_id != project.company_id or site.branch_id != project.branch_id:
        raise HTTPException(status_code=422, detail="Project site must belong to the project branch")
    row = ProjectSiteLink(company_id=project.company_id, project_id=project.id, site_id=site.id, site_role=payload.site_role, is_primary=False, linked_by=principal.user.full_name)
    db.add(row); db.flush(); audit(db, principal, "project.site.linked", "project_site", row.id, project=project, detail={"site_id": site.id, "role": row.site_role}); commit(db, "Site is already linked to this project"); return row_dict(row)


@router.post("/{project_id}/team", status_code=201)
def add_project_team(project_id: int, payload: TeamInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    project = project_or_404(db, principal, project_id, "projects.team"); ensure_project_editable(project)
    employee = ensure_employee(db, project.company_id, project.branch_id, payload.employee_id)
    if payload.start_date and payload.end_date and payload.end_date < payload.start_date:
        raise HTTPException(status_code=422, detail="Team assignment end date cannot precede start date")
    row = ProjectTeamMember(company_id=project.company_id, project_id=project.id, employee_id=employee.id, role=payload.role.strip().lower().replace(" ", "_"), allocation_pct=payload.allocation_pct, start_date=payload.start_date or project.mobilisation_date, end_date=payload.end_date, status=payload.status, notes=payload.notes, added_by=principal.user.full_name)
    db.add(row); db.flush()
    if row.role == "project_manager": project.project_manager_employee_id = employee.id
    audit(db, principal, "project.team.added", "project_team_member", row.id, project=project, detail={"employee_id": employee.id, "role": row.role}); commit(db, "Employee already has this role on the project"); return row_dict(row)


@router.post("/team/{member_id}/status")
def update_team_status(member_id: int, payload: TeamStatusInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = db.get(ProjectTeamMember, member_id)
    if not row or row.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Project team member not found")
    project = project_or_404(db, principal, row.project_id, "projects.team"); ensure_project_editable(project)
    if row.role == "project_manager" and payload.status == "released" and project.project_manager_employee_id == row.employee_id:
        raise HTTPException(status_code=409, detail="Assign a replacement project manager before releasing the current project manager")
    row.status = payload.status
    audit(db, principal, "project.team.status", "project_team_member", row.id, project=project, detail={"status": row.status}); commit(db); return row_dict(row)


@router.post("/{project_id}/budget-lines", status_code=201)
def add_budget_line(project_id: int, payload: BudgetLineInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    project = project_or_404(db, principal, project_id, "projects.budget"); ensure_project_editable(project)
    baseline = current_budget(db, project.id)
    if not baseline or baseline.status != "draft": raise HTTPException(status_code=409, detail="A draft budget baseline is required")
    row = ProjectBudgetLine(company_id=project.company_id, project_id=project.id, baseline_id=baseline.id, cost_code=payload.cost_code, cost_type=payload.cost_type, description=payload.description, amount=money(payload.amount), notes=payload.notes)
    db.add(row); db.flush(); recalc_budget(db, baseline); audit(db, principal, "project.budget.line_added", "project_budget_line", row.id, project=project, detail={"amount": str(row.amount), "version": baseline.version}); commit(db); return row_dict(row)


@router.put("/budget-lines/{line_id}")
def update_budget_line(line_id: int, payload: BudgetLineInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = db.get(ProjectBudgetLine, line_id)
    if not row or row.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Project budget line not found")
    project = project_or_404(db, principal, row.project_id, "projects.budget"); ensure_project_editable(project)
    baseline = db.get(ProjectBudgetBaseline, row.baseline_id)
    if not baseline or baseline.status != "draft": raise HTTPException(status_code=409, detail="Only draft budget baselines can be edited")
    for key, value in payload.model_dump().items(): setattr(row, key, money(value) if key == "amount" else value)
    recalc_budget(db, baseline); audit(db, principal, "project.budget.line_updated", "project_budget_line", row.id, project=project, detail={"amount": str(row.amount)}); commit(db); return row_dict(row)


@router.delete("/budget-lines/{line_id}", status_code=204)
def delete_budget_line(line_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> None:
    row = db.get(ProjectBudgetLine, line_id)
    if not row or row.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Project budget line not found")
    project = project_or_404(db, principal, row.project_id, "projects.budget"); ensure_project_editable(project)
    baseline = db.get(ProjectBudgetBaseline, row.baseline_id)
    if not baseline or baseline.status != "draft": raise HTTPException(status_code=409, detail="Only draft budget baselines can be edited")
    db.delete(row); db.flush(); recalc_budget(db, baseline); audit(db, principal, "project.budget.line_deleted", "project_budget_line", line_id, project=project); commit(db)


@router.post("/{project_id}/budget/revise", status_code=201)
def revise_budget(project_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    project = project_or_404(db, principal, project_id, "projects.budget"); ensure_project_editable(project)
    latest = current_budget(db, project.id)
    if not latest or latest.status != "approved": raise HTTPException(status_code=409, detail="An approved baseline is required before creating a revision")
    version = latest.version + 1
    new = ProjectBudgetBaseline(company_id=project.company_id, project_id=project.id, version=version, source="revision", status="draft", total_amount=latest.total_amount, created_by=principal.user.full_name, notes=f"Revision of baseline v{latest.version}")
    db.add(new); db.flush()
    for line in db.scalars(select(ProjectBudgetLine).where(ProjectBudgetLine.baseline_id == latest.id).order_by(ProjectBudgetLine.id)).all():
        db.add(ProjectBudgetLine(company_id=project.company_id, project_id=project.id, baseline_id=new.id, source_tender_estimate_item_id=line.source_tender_estimate_item_id, cost_code=line.cost_code, cost_type=line.cost_type, description=line.description, amount=line.amount, notes=line.notes))
    audit(db, principal, "project.budget.revision_created", "project_budget_baseline", new.id, project=project, detail={"version": version}); commit(db); return row_dict(new)


@router.post("/{project_id}/budget/submit")
def submit_budget(project_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    project = project_or_404(db, principal, project_id, "projects.budget"); ensure_project_editable(project)
    baseline = current_budget(db, project.id)
    if not baseline or baseline.status not in {"draft", "rejected"}: raise HTTPException(status_code=409, detail="A draft/rejected budget baseline is required")
    recalc_budget(db, baseline)
    if baseline.total_amount <= 0: raise HTTPException(status_code=409, detail="Budget baseline must have a positive total")
    if baseline.approval_request_id:
        existing = db.get(ApprovalRequest, baseline.approval_request_id)
        if existing and existing.status == "pending": return row_dict(existing)
    request = create_approval(db, principal, project, "PROJECT_BUDGET_BASELINE", "project_budget", str(baseline.id), f"Project budget baseline v{baseline.version}: {project.project_number}", baseline.total_amount)
    baseline.approval_request_id = request.id; baseline.status = "pending"
    audit(db, principal, "project.budget.submitted", "approval_request", request.id, project=project, detail={"version": baseline.version, "amount": str(baseline.total_amount)}); commit(db); return row_dict(request)


@router.post("/{project_id}/milestones", status_code=201)
def add_milestone(project_id: int, payload: MilestoneInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    project = project_or_404(db, principal, project_id, "projects.programme"); ensure_project_editable(project)
    if payload.planned_finish < payload.planned_start: raise HTTPException(status_code=422, detail="Milestone finish cannot precede start")
    predecessor = db.get(ProjectMilestone, payload.predecessor_id) if payload.predecessor_id else None
    if predecessor and predecessor.project_id != project.id: raise HTTPException(status_code=422, detail="Milestone predecessor must belong to the same project")
    row = ProjectMilestone(company_id=project.company_id, project_id=project.id, code=payload.code, name=payload.name, planned_start=payload.planned_start, planned_finish=payload.planned_finish, weight_pct=payload.weight_pct, predecessor_id=payload.predecessor_id, notes=payload.notes, created_by=principal.user.full_name)
    db.add(row); db.flush(); audit(db, principal, "project.milestone.added", "project_milestone", row.id, project=project, detail={"weight_pct": str(row.weight_pct)}); commit(db); return row_dict(row)


@router.put("/milestones/{milestone_id}")
def update_milestone(milestone_id: int, payload: MilestoneInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = db.get(ProjectMilestone, milestone_id)
    if not row or row.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Project milestone not found")
    project = project_or_404(db, principal, row.project_id, "projects.programme"); ensure_project_editable(project)
    if payload.planned_finish < payload.planned_start: raise HTTPException(status_code=422, detail="Milestone finish cannot precede start")
    if payload.predecessor_id == row.id: raise HTTPException(status_code=422, detail="Milestone cannot depend on itself")
    predecessor = db.get(ProjectMilestone, payload.predecessor_id) if payload.predecessor_id else None
    if predecessor and predecessor.project_id != project.id: raise HTTPException(status_code=422, detail="Milestone predecessor must belong to the same project")
    for key, value in payload.model_dump().items(): setattr(row, key, value)
    audit(db, principal, "project.milestone.updated", "project_milestone", row.id, project=project); commit(db); return row_dict(row)


@router.delete("/milestones/{milestone_id}", status_code=204)
def delete_milestone(milestone_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> None:
    row = db.get(ProjectMilestone, milestone_id)
    if not row or row.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Project milestone not found")
    project = project_or_404(db, principal, row.project_id, "projects.programme"); ensure_project_editable(project)
    dependents = db.scalar(select(func.count()).select_from(ProjectMilestone).where(ProjectMilestone.predecessor_id == row.id)) or 0
    if dependents: raise HTTPException(status_code=409, detail="Remove milestone dependencies before deleting this milestone")
    db.delete(row); audit(db, principal, "project.milestone.deleted", "project_milestone", row.id, project=project); commit(db)


@router.put("/mobilisation-items/{item_id}")
def update_mobilisation_item(item_id: int, payload: MobilisationItemInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = db.get(ProjectMobilisationItem, item_id)
    if not row or row.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Mobilisation checklist item not found")
    project = project_or_404(db, principal, row.project_id, "projects.manage"); ensure_project_editable(project)
    if row.required and payload.status == "not_applicable": raise HTTPException(status_code=422, detail="Required mobilisation items cannot be marked not applicable")
    ensure_employee(db, project.company_id, project.branch_id, payload.owner_employee_id); ensure_document(db, project.company_id, payload.document_id)
    row.status = payload.status; row.owner_employee_id = payload.owner_employee_id; row.due_date = payload.due_date; row.document_id = payload.document_id; row.notes = payload.notes; row.updated_by = principal.user.full_name
    audit(db, principal, "project.mobilisation_item.updated", "project_mobilisation_item", row.id, project=project, detail={"status": row.status}); commit(db); return row_dict(row)


@router.post("/{project_id}/assets", status_code=201)
def allocate_asset(project_id: int, payload: AssetAllocationInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    project = project_or_404(db, principal, project_id, "projects.assets"); ensure_project_editable(project)
    asset = db.get(FleetAsset, payload.asset_id)
    if not asset or asset.company_id != project.company_id: raise HTTPException(status_code=422, detail="Fleet/plant asset does not belong to this company")
    if asset.branch_id != project.branch_id and not principal.has_company_permission("projects.assets"):
        raise HTTPException(status_code=403, detail="Branch-scoped users cannot allocate fleet/plant owned by another branch")
    site_link = db.scalar(select(ProjectSiteLink).where(ProjectSiteLink.project_id == project.id, ProjectSiteLink.site_id == payload.site_id))
    if not site_link: raise HTTPException(status_code=422, detail="Fleet/plant allocation site must be linked to this project")
    if payload.planned_to and payload.planned_to < payload.planned_from: raise HTTPException(status_code=422, detail="Allocation end date cannot precede start date")
    existing = db.scalars(select(ProjectAssetAllocation).where(ProjectAssetAllocation.asset_id == asset.id, ProjectAssetAllocation.status.in_(["planned", "confirmed"]))).all()
    new_end = payload.planned_to or date.max
    for allocation in existing:
        old_end = allocation.planned_to or date.max
        if payload.planned_from <= old_end and allocation.planned_from <= new_end:
            raise HTTPException(status_code=409, detail=f"Asset already has an overlapping project allocation (allocation {allocation.id})")
    row = ProjectAssetAllocation(company_id=project.company_id, project_id=project.id, asset_id=asset.id, site_id=payload.site_id, planned_from=payload.planned_from, planned_to=payload.planned_to, purpose=payload.purpose, status="planned", allocated_by=principal.user.full_name)
    db.add(row); db.flush(); audit(db, principal, "project.asset.planned", "project_asset_allocation", row.id, project=project, detail={"asset_id": asset.id, "site_id": row.site_id}); commit(db); return row_dict(row)


@router.post("/assets/{allocation_id}/status")
def update_asset_allocation(allocation_id: int, payload: AssetStatusInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = db.get(ProjectAssetAllocation, allocation_id)
    if not row or row.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Project asset allocation not found")
    project = project_or_404(db, principal, row.project_id, "projects.assets"); ensure_project_editable(project)
    asset = db.get(FleetAsset, row.asset_id)
    if payload.status == "confirmed":
        if not asset or asset.serviceability == "unserviceable" or asset.status in {"out_of_service", "disposed"}: raise HTTPException(status_code=409, detail="Unserviceable/out-of-service fleet or plant cannot be confirmed for mobilisation")
        row.status = "confirmed"; row.confirmed_at = utcnow()
    else:
        row.status = "released"; row.released_at = utcnow()
    audit(db, principal, f"project.asset.{payload.status}", "project_asset_allocation", row.id, project=project, detail={"asset_id": row.asset_id}); commit(db); return row_dict(row)


@router.post("/{project_id}/risks", status_code=201)
def add_risk(project_id: int, payload: RiskInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    project = project_or_404(db, principal, project_id, "projects.manage"); ensure_project_editable(project)
    ensure_employee(db, project.company_id, project.branch_id, payload.owner_employee_id)
    row = ProjectRisk(company_id=project.company_id, project_id=project.id, risk_number=issue_reference(db, project.company_id, "PROJECT_RISK", "RSK"), category=payload.category, title=payload.title, description=payload.description, likelihood=payload.likelihood, impact=payload.impact, rating=payload.likelihood * payload.impact, owner_employee_id=payload.owner_employee_id, mitigation=payload.mitigation, status=payload.status, target_date=payload.target_date, created_by=principal.user.full_name)
    db.add(row); db.flush(); audit(db, principal, "project.risk.added", "project_risk", row.id, project=project, detail={"risk_number": row.risk_number, "rating": row.rating}); commit(db); return row_dict(row)


@router.put("/risks/{risk_id}")
def update_risk(risk_id: int, payload: RiskInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = db.get(ProjectRisk, risk_id)
    if not row or row.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Project risk not found")
    project = project_or_404(db, principal, row.project_id, "projects.manage"); ensure_project_editable(project)
    ensure_employee(db, project.company_id, project.branch_id, payload.owner_employee_id)
    for key, value in payload.model_dump().items(): setattr(row, key, value)
    row.rating = row.likelihood * row.impact
    audit(db, principal, "project.risk.updated", "project_risk", row.id, project=project, detail={"rating": row.rating, "status": row.status}); commit(db); return row_dict(row)


@router.put("/handover-documents/{handover_id}")
def update_handover_document(handover_id: int, payload: HandoverInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = db.get(ProjectHandoverDocument, handover_id)
    if not row or row.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Project handover document not found")
    project = project_or_404(db, principal, row.project_id, "projects.manage"); ensure_project_editable(project)
    if row.required and payload.status == "not_applicable": raise HTTPException(status_code=422, detail="Required handover documents cannot be marked not applicable")
    document = ensure_document(db, project.company_id, payload.document_id)
    if payload.status in {"received", "verified"} and not document: raise HTTPException(status_code=422, detail="A document link is required before marking handover evidence received or verified")
    row.document_id = document.id if document else None; row.status = payload.status; row.notes = payload.notes
    if payload.status == "verified": row.verified_by = principal.user.full_name; row.verified_at = utcnow()
    else: row.verified_by = None; row.verified_at = None
    audit(db, principal, "project.handover.updated", "project_handover_document", row.id, project=project, detail={"status": row.status, "document_id": row.document_id}); commit(db); return row_dict(row)


@router.get("/{project_id}/readiness")
def get_readiness(project_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    project = project_or_404(db, principal, project_id); return readiness_state(db, project)


@router.post("/{project_id}/readiness-approval")
def request_readiness_approval(project_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    project = project_or_404(db, principal, project_id, "projects.mobilise")
    if project.status == "ready" or project.readiness_status == "ready":
        request = db.get(ApprovalRequest, project.mobilisation_approval_request_id) if project.mobilisation_approval_request_id else None
        return row_dict(request) if request else {"status": "ready"}
    state = readiness_state(db, project)
    if not state["ready"]: raise HTTPException(status_code=409, detail={"message": "Project is not ready for mobilisation approval", "blockers": state["blockers"]})
    if project.mobilisation_approval_request_id:
        existing = db.get(ApprovalRequest, project.mobilisation_approval_request_id)
        if existing and existing.status == "pending": return row_dict(existing)
    request = create_approval(db, principal, project, "PROJECT_MOBILISATION", "project_mobilisation", str(project.id), f"Project mobilisation readiness: {project.project_number} - {project.name}", project.contract_amount)
    project.mobilisation_approval_request_id = request.id; project.readiness_status = "pending"
    audit(db, principal, "project.readiness.submitted", "approval_request", request.id, project=project, detail={"reference": request.reference}); commit(db); return row_dict(request)


@router.get("/{project_id}/site-operations-handoff")
def site_operations_handoff(project_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    project = project_or_404(db, principal, project_id)
    if project.status != "ready" or project.readiness_status != "ready": raise HTTPException(status_code=409, detail="Project mobilisation must be approved before Phase 7 Site Operations handoff")
    snapshot = db.scalar(select(ProjectReadinessSnapshot).where(ProjectReadinessSnapshot.project_id == project.id).order_by(ProjectReadinessSnapshot.version.desc()).limit(1))
    if not snapshot: raise HTTPException(status_code=409, detail="Approved project readiness snapshot is missing")
    return {"handoff_version": 1, "source_phase": 6, "target_phase": 7, "project_id": project.id, "project_number": project.project_number, "readiness_snapshot_id": snapshot.id, "snapshot": snapshot.snapshot, "ready": True}
