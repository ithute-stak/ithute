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

from app.api.v1.procurement import (
    allow_self_approval,
    assignment_authorised,
    commit,
    ensure_document,
    issue_reference,
    money,
    row_dict,
    utcnow,
)
from app.db.session import get_db
from app.models import (
    ApprovalAction,
    ApprovalRequest,
    ApprovalStep,
    ApprovalWorkflow,
    CloseoutAuditEvent,
    CloseoutChecklistItem,
    CloseoutDefect,
    CompanySetting,
    NumberSequence,
    Permission,
    Project,
    ProjectCloseout,
    Role,
    RolePermission,
)
from app.security.access import Principal, current_principal


router = APIRouter(prefix="/closeout", tags=["Phase 17 - Project Closeout & Defects Liability"])

PERMISSIONS = {
    "closeout.view": ("closeout", "view", "View project closeout, handover and defects-liability records"),
    "closeout.manage": ("closeout", "manage", "Prepare closeout evidence and manage defects"),
    "closeout.approve": ("closeout", "approve", "Independently approve project closeout"),
    "closeout.close": ("closeout", "close", "Close the project after defects-liability completion"),
    "closeout.export": ("closeout", "export", "Export controlled project closeout registers"),
}

POLICY_DEFAULT = {
    "require_checklist_evidence": True,
    "block_high_priority_defects": True,
    "require_defect_closeout_evidence": True,
}

DEFAULT_CHECKLIST = (
    ("practical_completion", "Practical completion certificate", "practical"),
    ("as_builts", "As-built drawings and asset records", "practical"),
    ("operations_manuals", "Operations and maintenance manuals", "practical"),
    ("warranties", "Warranty and guarantee handover", "practical"),
    ("client_handover", "Client handover / training acceptance", "practical"),
    ("final_account", "Final account agreement", "practical"),
    ("retention", "Retention release evidence", "final"),
    ("demobilisation", "Site demobilisation and temporary-works clearance", "practical"),
    ("archive", "Controlled project archive handover", "final"),
)
PRACTICAL_CONTROL_TYPES = {item_type for item_type, _, stage in DEFAULT_CHECKLIST if stage == "practical"}
FINAL_CONTROL_TYPES = {item_type for item_type, _, stage in DEFAULT_CHECKLIST if stage == "final"}


def anywhere(principal: Principal, permission: str) -> None:
    if not principal.has_permission_anywhere(permission):
        raise HTTPException(status_code=403, detail=f"Permission required: {permission}")


def scoped(principal: Principal, permission: str, project: Project) -> None:
    if not principal.can(permission, branch_id=project.branch_id, site_id=project.primary_site_id):
        raise HTTPException(status_code=403, detail=f"Permission required in this branch/site: {permission}")


def closeout_or_404(db: Session, principal: Principal, closeout_id: int, permission: str = "closeout.view") -> tuple[ProjectCloseout, Project]:
    row = db.get(ProjectCloseout, closeout_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Project closeout not found")
    project = db.get(Project, row.project_id)
    if not project:
        raise HTTPException(status_code=409, detail="Closeout project is unavailable")
    scoped(principal, permission, project)
    return row, project


def policy(db: Session, company_id: int) -> dict[str, Any]:
    setting = db.scalar(select(CompanySetting).where(CompanySetting.company_id == company_id, CompanySetting.key == "closeout_policy"))
    return {**POLICY_DEFAULT, **(setting.value if setting and isinstance(setting.value, dict) else {})}


def audit(db: Session, principal: Principal, action: str, closeout: ProjectCloseout, project: Project, entity: Any, detail: dict[str, Any] | None = None) -> None:
    db.add(CloseoutAuditEvent(
        company_id=closeout.company_id,
        branch_id=project.branch_id,
        site_id=project.primary_site_id,
        project_id=project.id,
        closeout_id=closeout.id,
        actor=principal.user.full_name,
        action=action,
        entity_type=entity.__tablename__,
        entity_id=str(entity.id),
        detail=detail or {},
    ))


def closeout_payload(db: Session, row: ProjectCloseout) -> dict[str, Any]:
    payload = row_dict(row)
    project = db.get(Project, row.project_id)
    if project:
        payload.update({"project_number": project.project_number, "project_name": project.name, "client_name": project.client_name})
    return payload


def workflow(db: Session, company_id: int) -> ApprovalWorkflow:
    row = db.scalar(select(ApprovalWorkflow).where(ApprovalWorkflow.company_id == company_id, ApprovalWorkflow.code == "PROJECT_CLOSEOUT", ApprovalWorkflow.is_active.is_(True)))
    if not row or not db.scalar(select(func.count()).select_from(ApprovalStep).where(ApprovalStep.workflow_id == row.id)):
        raise HTTPException(status_code=409, detail="Project closeout approval workflow is not configured")
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
    for code, name, scope in (("CLOSEOUT_MANAGER", "Closeout Manager", "branch"), ("CLOSEOUT_REVIEWER", "Closeout Reviewer", "company")):
        if code not in roles:
            row = Role(company_id=company_id, code=code, name=name, scope_level=scope, description=f"Phase 17 {name.lower()} role", is_system=True, is_active=True)
            db.add(row)
            db.flush()
            roles[code] = row
    grants = {
        "SYSTEM_ADMIN": set(PERMISSIONS),
        "HQ_EXECUTIVE": set(PERMISSIONS),
        "BRANCH_MANAGER": set(PERMISSIONS),
        "PROJECT_MANAGER": {"closeout.view", "closeout.manage"},
        "SITE_MANAGER": {"closeout.view", "closeout.manage"},
        "APPROVER": {"closeout.approve"},
        "AUDITOR": {"closeout.view", "closeout.export"},
        "CLOSEOUT_MANAGER": {"closeout.view", "closeout.manage"},
        "CLOSEOUT_REVIEWER": {"closeout.view", "closeout.approve", "closeout.close", "closeout.export"},
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
    for code, name, prefix in (("PROJECT_CLOSEOUT", "Project Closeout", "PCO"), ("CLOSEOUT_DEFECT", "Closeout Defect", "CDF"), ("CLOSEOUT_APPROVAL", "Closeout Approval", "COA")):
        if not db.scalar(select(NumberSequence).where(NumberSequence.company_id == company_id, NumberSequence.code == code)):
            db.add(NumberSequence(company_id=company_id, code=code, name=name, prefix=prefix, next_number=1, padding=5, reset_period="yearly"))
    branch, hq = roles.get("BRANCH_MANAGER"), roles.get("HQ_EXECUTIVE")
    if not branch or not hq:
        raise HTTPException(status_code=409, detail="Branch Manager and HQ Executive roles are required for Phase 17")
    approval = db.scalar(select(ApprovalWorkflow).where(ApprovalWorkflow.company_id == company_id, ApprovalWorkflow.code == "PROJECT_CLOSEOUT"))
    if not approval:
        approval = ApprovalWorkflow(company_id=company_id, code="PROJECT_CLOSEOUT", name="Project Closeout Approval", module="closeout", description="Controlled project completion and defects-liability handover", min_amount=Decimal("0"), is_active=True)
        db.add(approval)
        db.flush()
    if not db.scalar(select(func.count()).select_from(ApprovalStep).where(ApprovalStep.workflow_id == approval.id)):
        db.add_all([
            ApprovalStep(workflow_id=approval.id, step_order=1, name="Branch Closeout Review", role_id=branch.id, required_approvals=1, escalation_hours=24),
            ApprovalStep(workflow_id=approval.id, step_order=2, name="Head Office Closeout Approval", role_id=hq.id, required_approvals=1, escalation_hours=48),
        ])
    if not db.scalar(select(CompanySetting).where(CompanySetting.company_id == company_id, CompanySetting.key == "closeout_policy")):
        db.add(CompanySetting(company_id=company_id, key="closeout_policy", value=dict(POLICY_DEFAULT), description="Phase 17 project closeout governance"))


class CloseoutInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: int
    practical_completion_date: date
    defects_liability_end_date: date
    final_account_value: Decimal = Field(default=Decimal("0"), ge=0)
    retention_release_amount: Decimal = Field(default=Decimal("0"), ge=0)
    practical_completion_document_id: int | None = None
    client_acceptance_document_id: int | None = None
    final_account_document_id: int | None = None
    retention_release_document_id: int | None = None
    notes: str | None = Field(default=None, max_length=4000)


class ChecklistUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["open", "completed", "waived"]
    evidence_document_id: int | None = None
    notes: str | None = Field(default=None, max_length=4000)


class DefectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str = Field(default="general", min_length=2, max_length=80)
    title: str = Field(min_length=2, max_length=240)
    description: str = Field(min_length=5, max_length=6000)
    priority: Literal["low", "normal", "high", "critical"] = "normal"
    raised_date: date
    due_date: date | None = None
    evidence_document_id: int | None = None
    notes: str | None = Field(default=None, max_length=4000)


class DefectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["open", "in_progress", "closed"]
    closeout_document_id: int | None = None
    notes: str | None = Field(default=None, max_length=4000)


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]
    comment: str | None = Field(default=None, max_length=2000)


@router.post("/bootstrap")
def bootstrap(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if not principal.has_company_permission("company.manage") and not principal.has_company_permission("closeout.manage"):
        raise HTTPException(status_code=403, detail="Company administration is required to initialise Phase 17")
    bootstrap_data(db, principal.user.company_id)
    commit(db)
    return {"phase": 17, "status": "ready"}


@router.get("/catalog")
def catalog(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    anywhere(principal, "closeout.view")
    projects = [row_dict(row) for row in db.scalars(select(Project).where(Project.company_id == principal.user.company_id, Project.status != "closed").order_by(Project.contract_completion_date.desc())).all() if principal.can("closeout.view", branch_id=row.branch_id, site_id=row.primary_site_id)]
    return {"projects": projects, "permissions": [code for code in PERMISSIONS if principal.has_permission_anywhere(code)]}


@router.get("/cases")
def cases(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    anywhere(principal, "closeout.view")
    rows = db.scalars(select(ProjectCloseout).where(ProjectCloseout.company_id == principal.user.company_id).order_by(ProjectCloseout.practical_completion_date.desc(), ProjectCloseout.id.desc())).all()
    result: list[dict[str, Any]] = []
    for row in rows:
        project = db.get(Project, row.project_id)
        if project and principal.can("closeout.view", branch_id=project.branch_id, site_id=project.primary_site_id):
            result.append(closeout_payload(db, row))
    return result


@router.post("/cases", status_code=201)
def create_case(payload: CloseoutInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    project = db.get(Project, payload.project_id)
    if not project or project.company_id != principal.user.company_id:
        raise HTTPException(status_code=422, detail="Project does not belong to this company")
    scoped(principal, "closeout.manage", project)
    if project.status == "closed":
        raise HTTPException(status_code=409, detail="A closed project cannot start a new closeout record")
    if payload.defects_liability_end_date < payload.practical_completion_date:
        raise HTTPException(status_code=422, detail="Defects-liability end date cannot precede practical completion")
    if db.scalar(select(ProjectCloseout).where(ProjectCloseout.project_id == project.id)):
        raise HTTPException(status_code=409, detail="This project already has a controlled closeout record")
    for document_id in (payload.practical_completion_document_id, payload.client_acceptance_document_id, payload.final_account_document_id, payload.retention_release_document_id):
        ensure_document(db, project.company_id, document_id)
    row = ProjectCloseout(
        company_id=project.company_id, branch_id=project.branch_id, site_id=project.primary_site_id, project_id=project.id,
        closeout_number=issue_reference(db, project.company_id, "PROJECT_CLOSEOUT", "PCO"),
        practical_completion_date=payload.practical_completion_date, defects_liability_end_date=payload.defects_liability_end_date,
        final_account_value=money(payload.final_account_value), retention_release_amount=money(payload.retention_release_amount),
        practical_completion_document_id=payload.practical_completion_document_id, client_acceptance_document_id=payload.client_acceptance_document_id,
        final_account_document_id=payload.final_account_document_id, retention_release_document_id=payload.retention_release_document_id,
        notes=payload.notes, created_by=principal.user.full_name,
    )
    db.add(row)
    db.flush()
    evidence_by_type = {
        "practical_completion": payload.practical_completion_document_id,
        "client_handover": payload.client_acceptance_document_id,
        "final_account": payload.final_account_document_id,
        "retention": payload.retention_release_document_id,
    }
    for item_type, title, stage in DEFAULT_CHECKLIST:
        evidence = evidence_by_type.get(item_type)
        db.add(CloseoutChecklistItem(
            company_id=project.company_id, branch_id=project.branch_id, closeout_id=row.id, item_type=item_type, title=title,
            due_date=payload.practical_completion_date if stage == "practical" else payload.defects_liability_end_date,
            status="completed" if evidence else "open", evidence_document_id=evidence,
            completed_by=principal.user.full_name if evidence else None, completed_at=utcnow() if evidence else None,
        ))
    audit(db, principal, "closeout.case.created", row, project, row, {"practical_completion_date": row.practical_completion_date.isoformat()})
    commit(db)
    return closeout_payload(db, row)


@router.get("/cases/{closeout_id:int}")
def case_detail(closeout_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row, _ = closeout_or_404(db, principal, closeout_id)
    payload = closeout_payload(db, row)
    payload["checklist"] = [row_dict(item) for item in db.scalars(select(CloseoutChecklistItem).where(CloseoutChecklistItem.closeout_id == row.id).order_by(CloseoutChecklistItem.required.desc(), CloseoutChecklistItem.due_date, CloseoutChecklistItem.id)).all()]
    payload["defects"] = [row_dict(item) for item in db.scalars(select(CloseoutDefect).where(CloseoutDefect.closeout_id == row.id).order_by(CloseoutDefect.priority.desc(), CloseoutDefect.due_date, CloseoutDefect.id)).all()]
    return payload


@router.put("/checklist/{item_id:int}")
def update_checklist(item_id: int, payload: ChecklistUpdate, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    item = db.get(CloseoutChecklistItem, item_id)
    if not item or item.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Closeout checklist item not found")
    row, project = closeout_or_404(db, principal, item.closeout_id, "closeout.manage")
    if row.status not in {"draft", "rejected", "defects_liability"}:
        raise HTTPException(status_code=409, detail="Closeout checklist evidence is frozen while approval is active or after final closure")
    if row.status == "defects_liability" and item.item_type not in FINAL_CONTROL_TYPES:
        raise HTTPException(status_code=409, detail="Practical-completion handover controls are frozen after closeout approval")
    current_policy = policy(db, row.company_id)
    if payload.status == "completed" and current_policy["require_checklist_evidence"] and not (payload.evidence_document_id or item.evidence_document_id):
        raise HTTPException(status_code=409, detail="Controlled evidence is required before this checklist item can be completed")
    if payload.status == "waived" and not payload.notes:
        raise HTTPException(status_code=422, detail="A waiver reason is required")
    ensure_document(db, row.company_id, payload.evidence_document_id)
    item.status = payload.status
    item.evidence_document_id = payload.evidence_document_id or item.evidence_document_id
    item.notes = payload.notes or item.notes
    item.completed_by = principal.user.full_name if payload.status in {"completed", "waived"} else None
    item.completed_at = utcnow() if payload.status in {"completed", "waived"} else None
    audit(db, principal, "closeout.checklist.updated", row, project, item, {"status": item.status})
    commit(db)
    return row_dict(item)


@router.post("/cases/{closeout_id:int}/defects", status_code=201)
def create_defect(closeout_id: int, payload: DefectInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row, project = closeout_or_404(db, principal, closeout_id, "closeout.manage")
    if row.status not in {"draft", "rejected", "defects_liability"}:
        raise HTTPException(status_code=409, detail="Defects can only be managed in draft, returned or approved defects-liability closeout records")
    if payload.due_date and payload.due_date < payload.raised_date:
        raise HTTPException(status_code=422, detail="Defect due date cannot precede its raised date")
    ensure_document(db, row.company_id, payload.evidence_document_id)
    defect = CloseoutDefect(
        company_id=row.company_id, branch_id=row.branch_id, site_id=row.site_id, project_id=row.project_id, closeout_id=row.id,
        defect_number=issue_reference(db, row.company_id, "CLOSEOUT_DEFECT", "CDF"), category=payload.category, title=payload.title,
        description=payload.description, priority=payload.priority, raised_date=payload.raised_date, due_date=payload.due_date,
        evidence_document_id=payload.evidence_document_id, notes=payload.notes, raised_by=principal.user.full_name,
    )
    db.add(defect)
    db.flush()
    audit(db, principal, "closeout.defect.created", row, project, defect, {"priority": defect.priority})
    commit(db)
    return row_dict(defect)


@router.put("/defects/{defect_id:int}")
def update_defect(defect_id: int, payload: DefectUpdate, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    defect = db.get(CloseoutDefect, defect_id)
    if not defect or defect.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Closeout defect not found")
    row, project = closeout_or_404(db, principal, defect.closeout_id, "closeout.manage")
    if row.status not in {"draft", "rejected", "defects_liability"}:
        raise HTTPException(status_code=409, detail="Defect updates are locked while the closeout is under approval or after final project closure")
    current_policy = policy(db, row.company_id)
    if payload.status == "closed" and current_policy["require_defect_closeout_evidence"] and not (payload.closeout_document_id or defect.closeout_document_id):
        raise HTTPException(status_code=409, detail="Controlled closeout evidence is required before a defect can be closed")
    ensure_document(db, row.company_id, payload.closeout_document_id)
    defect.status = payload.status
    defect.closeout_document_id = payload.closeout_document_id or defect.closeout_document_id
    defect.notes = payload.notes or defect.notes
    defect.closed_by = principal.user.full_name if payload.status == "closed" else None
    defect.closed_at = utcnow() if payload.status == "closed" else None
    audit(db, principal, "closeout.defect.updated", row, project, defect, {"status": defect.status})
    commit(db)
    return row_dict(defect)


@router.post("/cases/{closeout_id:int}/submit")
def submit_case(closeout_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row, project = closeout_or_404(db, principal, closeout_id, "closeout.manage")
    if row.status not in {"draft", "rejected"}:
        raise HTTPException(status_code=409, detail="Only draft or rejected closeout records can be submitted")
    items = db.scalars(select(CloseoutChecklistItem).where(CloseoutChecklistItem.closeout_id == row.id, CloseoutChecklistItem.required.is_(True), CloseoutChecklistItem.item_type.in_(PRACTICAL_CONTROL_TYPES))).all()
    if not items or any(item.status not in {"completed", "waived"} for item in items):
        raise HTTPException(status_code=409, detail="Every required practical-completion and handover control must be completed or formally waived before independent approval")
    defects = db.scalars(select(CloseoutDefect).where(CloseoutDefect.closeout_id == row.id)).all()
    if policy(db, row.company_id)["block_high_priority_defects"] and any(item.priority in {"high", "critical"} and item.status != "closed" for item in defects):
        raise HTTPException(status_code=409, detail="High or critical defects must be closed before closeout approval")
    flow = workflow(db, row.company_id)
    request = ApprovalRequest(
        company_id=row.company_id, workflow_id=flow.id, branch_id=row.branch_id, site_id=row.site_id,
        entity_type="project_closeout", entity_id=str(row.id), reference=issue_reference(db, row.company_id, "CLOSEOUT_APPROVAL", "COA"),
        title=f"Project closeout {row.closeout_number}", amount=money(row.final_account_value), status="pending", current_step_order=1,
        requested_by=principal.user.full_name,
    )
    db.add(request)
    db.flush()
    row.status, row.approval_request_id, row.submitted_at = "submitted", request.id, utcnow()
    audit(db, principal, "closeout.case.submitted", row, project, row, {"approval_reference": request.reference})
    commit(db)
    return row_dict(request)


@router.get("/approvals")
def approvals(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    anywhere(principal, "closeout.view")
    rows = db.scalars(select(ApprovalRequest).where(ApprovalRequest.company_id == principal.user.company_id, ApprovalRequest.entity_type == "project_closeout", ApprovalRequest.status == "pending").order_by(ApprovalRequest.requested_at)).all()
    result: list[dict[str, Any]] = []
    for request in rows:
        row = db.get(ProjectCloseout, int(request.entity_id))
        project = db.get(Project, row.project_id) if row else None
        if row and project and principal.can("closeout.view", branch_id=project.branch_id, site_id=project.primary_site_id):
            payload = row_dict(request)
            payload.update({"closeout_number": row.closeout_number, "project_number": project.project_number, "project_name": project.name})
            result.append(payload)
    return result


@router.post("/approvals/{request_id:int}/decision")
def decide_approval(request_id: int, payload: ApprovalDecision, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    request = db.get(ApprovalRequest, request_id)
    if not request or request.company_id != principal.user.company_id or request.entity_type != "project_closeout":
        raise HTTPException(status_code=404, detail="Closeout approval request not found")
    row = db.get(ProjectCloseout, int(request.entity_id))
    if not row:
        raise HTTPException(status_code=404, detail="Project closeout is unavailable")
    _, project = closeout_or_404(db, principal, row.id, "closeout.approve")
    if request.status != "pending" or row.status != "submitted":
        raise HTTPException(status_code=409, detail="Closeout approval request is not pending")
    step = db.scalar(select(ApprovalStep).where(ApprovalStep.workflow_id == request.workflow_id, ApprovalStep.step_order == request.current_step_order))
    if not step or not assignment_authorised(db, principal, step.role_id, project.branch_id, project.primary_site_id):
        raise HTTPException(status_code=403, detail="Your active role assignment is not authorised for this approval step")
    if request.requested_by == principal.user.full_name and not allow_self_approval(db, row.company_id):
        raise HTTPException(status_code=422, detail="Self-approval is disabled by company policy")
    db.add(ApprovalAction(request_id=request.id, step_order=step.step_order, role_id=step.role_id, actor_name=principal.user.full_name, action=payload.decision, comment=payload.comment))
    if payload.decision == "reject":
        request.status, request.completed_at, row.status = "rejected", utcnow(), "rejected"
    else:
        approved = (db.scalar(select(func.count()).select_from(ApprovalAction).where(ApprovalAction.request_id == request.id, ApprovalAction.step_order == step.step_order, ApprovalAction.action == "approve")) or 0) + 1
        if approved >= step.required_approvals:
            next_step = db.scalar(select(ApprovalStep).where(ApprovalStep.workflow_id == request.workflow_id, ApprovalStep.step_order > step.step_order).order_by(ApprovalStep.step_order).limit(1))
            if next_step:
                request.current_step_order = next_step.step_order
            else:
                request.status, request.completed_at = "approved", utcnow()
                row.status, row.approved_at, project.status = "defects_liability", utcnow(), "defects_liability"
    audit(db, principal, f"closeout.approval.{payload.decision}", row, project, request, {"approval_status": request.status, "step": step.step_order})
    commit(db)
    return row_dict(request)


@router.post("/cases/{closeout_id:int}/close")
def close_case(closeout_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row, project = closeout_or_404(db, principal, closeout_id, "closeout.close")
    if row.status != "defects_liability":
        raise HTTPException(status_code=409, detail="Only an approved defects-liability closeout can be finally closed")
    if row.defects_liability_end_date > date.today():
        raise HTTPException(status_code=409, detail="The configured defects-liability period has not ended")
    final_items = db.scalars(select(CloseoutChecklistItem).where(CloseoutChecklistItem.closeout_id == row.id, CloseoutChecklistItem.required.is_(True))).all()
    if any(item.status not in {"completed", "waived"} for item in final_items):
        raise HTTPException(status_code=409, detail="Retention release and final archive controls must be completed or formally waived before final project closure")
    open_defects = db.scalar(select(func.count()).select_from(CloseoutDefect).where(CloseoutDefect.closeout_id == row.id, CloseoutDefect.status != "closed")) or 0
    if open_defects:
        raise HTTPException(status_code=409, detail="Every defects-liability item must be closed before final project closure")
    row.status, row.closed_at, project.status = "closed", utcnow(), "closed"
    audit(db, principal, "closeout.case.closed", row, project, row, {"project_status": project.status})
    commit(db)
    return closeout_payload(db, row)


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    anywhere(principal, "closeout.view")
    eligible: list[ProjectCloseout] = []
    for row in db.scalars(select(ProjectCloseout).where(ProjectCloseout.company_id == principal.user.company_id)).all():
        project = db.get(Project, row.project_id)
        if project and principal.can("closeout.view", branch_id=project.branch_id, site_id=project.primary_site_id):
            eligible.append(row)
    ids = {row.id for row in eligible}
    defects = [row for row in db.scalars(select(CloseoutDefect).where(CloseoutDefect.company_id == principal.user.company_id)).all() if row.closeout_id in ids]
    today = date.today()
    return {
        "closeouts": len(eligible),
        "draft": sum(row.status in {"draft", "rejected"} for row in eligible),
        "awaiting_approval": sum(row.status == "submitted" for row in eligible),
        "defects_liability": sum(row.status == "defects_liability" for row in eligible),
        "closed": sum(row.status == "closed" for row in eligible),
        "open_defects": sum(row.status != "closed" for row in defects),
        "overdue_defects": sum(row.status != "closed" and row.due_date is not None and row.due_date < today for row in defects),
        "due_for_final_close": sum(row.status == "defects_liability" and row.defects_liability_end_date <= today for row in eligible),
    }


@router.get("/exports/cases.csv")
def export_cases(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> StreamingResponse:
    anywhere(principal, "closeout.export")
    rows = [row for row in cases(db, principal)]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=["closeout_number", "project_number", "project_name", "client_name", "practical_completion_date", "defects_liability_end_date", "final_account_value", "retention_release_amount", "status"])
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in writer.fieldnames})
    return StreamingResponse(iter([stream.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=project-closeout-register.csv"})


@router.get("/audit")
def audit_events(limit: int = Query(default=250, ge=1, le=1000), db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    anywhere(principal, "closeout.view")
    rows = db.scalars(select(CloseoutAuditEvent).where(CloseoutAuditEvent.company_id == principal.user.company_id).order_by(CloseoutAuditEvent.occurred_at.desc()).limit(limit)).all()
    return [row_dict(row) for row in rows if row.branch_id is not None and principal.can("closeout.view", branch_id=row.branch_id, site_id=row.site_id)]
