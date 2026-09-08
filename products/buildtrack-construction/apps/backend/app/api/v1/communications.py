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
from app.models import ApprovalAction, ApprovalRequest, ApprovalStep, ApprovalWorkflow, CommunicationAuditEvent, Employee, MeetingAction, NumberSequence, Permission, Project, ProjectCorrespondence, ProjectMeeting, ProjectStakeholder, Role, RolePermission
from app.security.access import Principal, current_principal

router = APIRouter(prefix="/communications", tags=["Phase 21 - Project Communications & Stakeholder Control"])

PERMISSIONS = {
    "communications.view": ("communications", "view", "View stakeholder, correspondence, meeting and action registers"),
    "communications.manage": ("communications", "manage", "Create controlled communications, minutes and actions"),
    "communications.approve": ("communications", "approve", "Independently approve formal correspondence and minutes"),
    "communications.verify": ("communications", "verify", "Independently verify completed meeting actions"),
    "communications.export": ("communications", "export", "Export controlled communications registers"),
}


def anywhere(principal: Principal, permission: str) -> None:
    if not principal.has_permission_anywhere(permission): raise HTTPException(status_code=403, detail=f"Permission required: {permission}")


def scope(principal: Principal, permission: str, branch_id: int, site_id: int | None) -> None:
    if not principal.can(permission, branch_id=branch_id, site_id=site_id): raise HTTPException(status_code=403, detail=f"Permission required in this branch/site: {permission}")


def audit(db: Session, principal: Principal, action: str, entity: Any, detail: dict[str, Any] | None = None) -> None:
    db.add(CommunicationAuditEvent(company_id=principal.user.company_id, branch_id=getattr(entity, "branch_id", None), site_id=getattr(entity, "site_id", None), project_id=getattr(entity, "project_id", None), actor=principal.user.full_name, action=action, entity_type=entity.__tablename__, entity_id=str(entity.id), detail=detail or {}))


def project_or_404(db: Session, principal: Principal, project_id: int, permission: str) -> Project:
    row = db.get(Project, project_id)
    if not row or row.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Project not found")
    scope(principal, permission, row.branch_id, row.primary_site_id)
    return row


def owned(db: Session, principal: Principal, model: Any, row_id: int, permission: str, label: str) -> Any:
    row = db.get(model, row_id)
    if not row or row.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail=f"{label} not found")
    scope(principal, permission, row.branch_id, row.site_id)
    return row


def workflow(db: Session, company_id: int, code: str) -> ApprovalWorkflow:
    row = db.scalar(select(ApprovalWorkflow).where(ApprovalWorkflow.company_id == company_id, ApprovalWorkflow.code == code, ApprovalWorkflow.is_active.is_(True)))
    if not row or not db.scalar(select(func.count()).select_from(ApprovalStep).where(ApprovalStep.workflow_id == row.id)): raise HTTPException(status_code=409, detail="Phase 21 approval workflow is not configured")
    return row


def request_approval(db: Session, principal: Principal, code: str, entity: Any, title: str) -> ApprovalRequest:
    selected = workflow(db, principal.user.company_id, code)
    row = ApprovalRequest(company_id=principal.user.company_id, workflow_id=selected.id, branch_id=entity.branch_id, site_id=entity.site_id, entity_type=entity.__tablename__, entity_id=str(entity.id), reference=issue_reference(db, principal.user.company_id, "COMMUNICATION_APPROVAL", "CAP"), title=title, amount=Decimal("0"), status="pending", current_step_order=1, requested_by=principal.user.full_name)
    db.add(row); db.flush(); return row


def bootstrap_data(db: Session, company_id: int) -> None:
    permissions: dict[str, Permission] = {}
    for code, (module, action, description) in PERMISSIONS.items():
        row = db.scalar(select(Permission).where(Permission.code == code))
        if not row: row = Permission(code=code, module=module, action=action, description=description); db.add(row); db.flush()
        permissions[code] = row
    roles = {row.code: row for row in db.scalars(select(Role).where(Role.company_id == company_id)).all()}
    for code, name, level in (("COMMUNICATIONS_MANAGER", "Communications Manager", "company"), ("PROJECT_COORDINATOR", "Project Coordinator", "branch"), ("COMMUNICATIONS_REVIEWER", "Communications Reviewer", "company")):
        if code not in roles: roles[code] = Role(company_id=company_id, code=code, name=name, scope_level=level, description=f"Phase 21 {name.lower()} role", is_system=True, is_active=True); db.add(roles[code]); db.flush()
    grants = {"SYSTEM_ADMIN": set(PERMISSIONS), "HQ_EXECUTIVE": set(PERMISSIONS), "BRANCH_MANAGER": set(PERMISSIONS), "PROJECT_MANAGER": {"communications.view", "communications.manage", "communications.export"}, "SITE_MANAGER": {"communications.view", "communications.manage"}, "APPROVER": {"communications.approve", "communications.verify"}, "AUDITOR": {"communications.view", "communications.export"}, "COMMUNICATIONS_MANAGER": set(PERMISSIONS), "PROJECT_COORDINATOR": {"communications.view", "communications.manage", "communications.export"}, "COMMUNICATIONS_REVIEWER": {"communications.view", "communications.approve", "communications.verify", "communications.export"}}
    for role_code, codes in grants.items():
        role = roles.get(role_code)
        if not role: continue
        existing = set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id == role.id)).all())
        for code in codes:
            if permissions[code].id not in existing: db.add(RolePermission(role_id=role.id, permission_id=permissions[code].id)); existing.add(permissions[code].id)
    for code, name, prefix in (("PROJECT_STAKEHOLDER", "Project Stakeholder", "STK"), ("PROJECT_CORRESPONDENCE", "Project Correspondence", "COR"), ("PROJECT_MEETING", "Project Meeting", "MTG"), ("COMMUNICATION_APPROVAL", "Communication Approval", "CAP")):
        if not db.scalar(select(NumberSequence).where(NumberSequence.company_id == company_id, NumberSequence.code == code)): db.add(NumberSequence(company_id=company_id, code=code, name=name, prefix=prefix, next_number=1, padding=5, reset_period="yearly"))
    branch, hq = roles.get("BRANCH_MANAGER"), roles.get("HQ_EXECUTIVE")
    if not branch or not hq: raise HTTPException(status_code=409, detail="Branch Manager and HQ Executive roles are required for Phase 21")
    for code, name in (("FORMAL_CORRESPONDENCE", "Formal Correspondence Approval"), ("MEETING_MINUTES", "Meeting Minutes Approval")):
        row = db.scalar(select(ApprovalWorkflow).where(ApprovalWorkflow.company_id == company_id, ApprovalWorkflow.code == code))
        if not row: row = ApprovalWorkflow(company_id=company_id, code=code, name=name, module="communications", description=f"Controlled {name.lower()}", min_amount=Decimal("0"), is_active=True); db.add(row); db.flush()
        if not db.scalar(select(func.count()).select_from(ApprovalStep).where(ApprovalStep.workflow_id == row.id)): db.add_all([ApprovalStep(workflow_id=row.id, step_order=1, name="Branch communications review", role_id=branch.id, required_approvals=1, escalation_hours=24), ApprovalStep(workflow_id=row.id, step_order=2, name="Head office communications approval", role_id=hq.id, required_approvals=1, escalation_hours=48)])


class StakeholderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: int; organisation: str = Field(min_length=2, max_length=240); contact_name: str = Field(min_length=2, max_length=240)
    stakeholder_role: Literal["client", "consultant", "authority", "subcontractor", "supplier", "internal", "other"]
    email: str | None = Field(default=None, max_length=320); phone: str | None = Field(default=None, max_length=80); notes: str | None = Field(default=None, max_length=4000)


class CorrespondenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: int; stakeholder_id: int | None = None; direction: Literal["incoming", "outgoing"]; classification: Literal["formal", "operational", "internal"]; correspondence_type: Literal["letter", "email", "transmittal", "notice", "other"]
    subject: str = Field(min_length=2, max_length=300); external_reference: str | None = Field(default=None, max_length=160); correspondence_date: date; response_due_date: date | None = None; correspondence_document_id: int | None = None; notes: str | None = Field(default=None, max_length=4000)


class MeetingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: int; meeting_type: Literal["site", "progress", "commercial", "client", "technical", "internal", "other"]; title: str = Field(min_length=2, max_length=300); meeting_date: date; minutes_document_id: int | None = None; notes: str | None = Field(default=None, max_length=4000)


class ActionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=2, max_length=300); owner_employee_id: int | None = None; due_date: date | None = None


class DocumentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: int = Field(gt=0); note: str | None = Field(default=None, max_length=4000)


class DecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]; comment: str | None = Field(default=None, max_length=2000)


@router.post("/bootstrap")
def bootstrap(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if not principal.has_company_permission("company.manage") and not principal.has_company_permission("communications.manage"): raise HTTPException(status_code=403, detail="Company administration is required to initialise Phase 21")
    bootstrap_data(db, principal.user.company_id); commit(db); return {"phase": 21, "status": "ready"}


@router.get("/catalog")
def catalog(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    anywhere(principal, "communications.view")
    projects = [row_dict(row) for row in db.scalars(select(Project).where(Project.company_id == principal.user.company_id, Project.status.in_(("mobilising", "ready", "active"))).order_by(Project.name)).all() if principal.can("communications.view", branch_id=row.branch_id, site_id=row.primary_site_id)]
    employees = [row_dict(row) for row in db.scalars(select(Employee).where(Employee.company_id == principal.user.company_id, Employee.employment_status == "active").order_by(Employee.first_name, Employee.last_name)).all()]
    return {"projects": projects, "employees": employees, "permissions": [code for code in PERMISSIONS if principal.has_permission_anywhere(code)]}


@router.get("/stakeholders")
def stakeholders(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    anywhere(principal, "communications.view")
    return [row_dict(row) for row in db.scalars(select(ProjectStakeholder).where(ProjectStakeholder.company_id == principal.user.company_id).order_by(ProjectStakeholder.organisation, ProjectStakeholder.contact_name)).all() if principal.can("communications.view", branch_id=row.branch_id, site_id=row.site_id)]


@router.post("/stakeholders", status_code=201)
def create_stakeholder(payload: StakeholderInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    project = project_or_404(db, principal, payload.project_id, "communications.manage")
    row = ProjectStakeholder(company_id=project.company_id, branch_id=project.branch_id, site_id=project.primary_site_id, project_id=project.id, stakeholder_number=issue_reference(db, project.company_id, "PROJECT_STAKEHOLDER", "STK"), organisation=payload.organisation.strip(), contact_name=payload.contact_name.strip(), stakeholder_role=payload.stakeholder_role, email=payload.email, phone=payload.phone, notes=payload.notes, created_by=principal.user.full_name)
    db.add(row); db.flush(); audit(db, principal, "communications.stakeholder.created", row); commit(db); return row_dict(row)


@router.get("/correspondence")
def correspondence(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    anywhere(principal, "communications.view"); result=[]
    for row in db.scalars(select(ProjectCorrespondence).where(ProjectCorrespondence.company_id == principal.user.company_id).order_by(ProjectCorrespondence.correspondence_date.desc(), ProjectCorrespondence.id.desc())).all():
        if not principal.can("communications.view", branch_id=row.branch_id, site_id=row.site_id): continue
        item=row_dict(row); project=db.get(Project,row.project_id); stakeholder=db.get(ProjectStakeholder,row.stakeholder_id) if row.stakeholder_id else None; item.update({"project_number": project.project_number if project else "", "project_name": project.name if project else "", "stakeholder": f"{stakeholder.organisation} · {stakeholder.contact_name}" if stakeholder else ""}); result.append(item)
    return result


@router.post("/correspondence", status_code=201)
def create_correspondence(payload: CorrespondenceInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    project = project_or_404(db, principal, payload.project_id, "communications.manage")
    if payload.response_due_date and payload.response_due_date < payload.correspondence_date: raise HTTPException(status_code=422, detail="Response due date cannot precede correspondence date")
    if payload.stakeholder_id:
        stakeholder = owned(db, principal, ProjectStakeholder, payload.stakeholder_id, "communications.manage", "Stakeholder")
        if stakeholder.project_id != project.id: raise HTTPException(status_code=422, detail="Stakeholder must belong to the selected project")
    ensure_document(db, project.company_id, payload.correspondence_document_id)
    row = ProjectCorrespondence(company_id=project.company_id, branch_id=project.branch_id, site_id=project.primary_site_id, project_id=project.id, stakeholder_id=payload.stakeholder_id, correspondence_number=issue_reference(db, project.company_id, "PROJECT_CORRESPONDENCE", "COR"), direction=payload.direction, classification=payload.classification, correspondence_type=payload.correspondence_type, subject=payload.subject.strip(), external_reference=payload.external_reference, correspondence_date=payload.correspondence_date, response_due_date=payload.response_due_date, status="draft", correspondence_document_id=payload.correspondence_document_id, notes=payload.notes, prepared_by=principal.user.full_name)
    db.add(row); db.flush(); audit(db, principal, "communications.correspondence.created", row); commit(db); return row_dict(row)


@router.post("/correspondence/{correspondence_id:int}/submit")
def submit_correspondence(correspondence_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = owned(db, principal, ProjectCorrespondence, correspondence_id, "communications.manage", "Correspondence")
    if row.status not in {"draft", "rejected"}: raise HTTPException(status_code=409, detail="Only draft or rejected correspondence can be submitted")
    if not row.correspondence_document_id: raise HTTPException(status_code=409, detail="Controlled correspondence evidence is required before submission")
    if row.direction == "outgoing" and row.classification == "formal":
        approval = request_approval(db, principal, "FORMAL_CORRESPONDENCE", row, f"Formal correspondence {row.correspondence_number}"); row.status, row.approval_request_id = "submitted", approval.id
    else: row.status, row.recorded_at = "recorded", utcnow()
    row.submitted_at = utcnow(); audit(db, principal, "communications.correspondence.submitted", row); commit(db); return row_dict(row)


@router.post("/correspondence/{correspondence_id:int}/record-dispatch")
def record_dispatch(correspondence_id: int, payload: DocumentInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = owned(db, principal, ProjectCorrespondence, correspondence_id, "communications.manage", "Correspondence")
    if row.status != "approved" or row.direction != "outgoing" or row.classification != "formal": raise HTTPException(status_code=409, detail="Only approved formal outgoing correspondence can be recorded as dispatched")
    ensure_document(db, row.company_id, payload.document_id); row.dispatch_evidence_document_id, row.recorded_at, row.status = payload.document_id, utcnow(), "recorded"; audit(db, principal, "communications.correspondence.dispatch_recorded", row); commit(db); return row_dict(row)


@router.post("/correspondence/{correspondence_id:int}/close")
def close_correspondence(correspondence_id: int, payload: DocumentInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = owned(db, principal, ProjectCorrespondence, correspondence_id, "communications.manage", "Correspondence")
    if row.status != "recorded": raise HTTPException(status_code=409, detail="Only recorded correspondence can be closed")
    ensure_document(db, row.company_id, payload.document_id); row.response_document_id, row.closed_at, row.status = payload.document_id, utcnow(), "closed"; audit(db, principal, "communications.correspondence.closed", row); commit(db); return row_dict(row)


@router.get("/meetings")
def meetings(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    anywhere(principal, "communications.view"); result=[]
    for row in db.scalars(select(ProjectMeeting).where(ProjectMeeting.company_id == principal.user.company_id).order_by(ProjectMeeting.meeting_date.desc(), ProjectMeeting.id.desc())).all():
        if not principal.can("communications.view", branch_id=row.branch_id, site_id=row.site_id): continue
        item=row_dict(row); project=db.get(Project,row.project_id); item.update({"project_number": project.project_number if project else "", "action_count": db.scalar(select(func.count()).select_from(MeetingAction).where(MeetingAction.meeting_id == row.id)) or 0}); result.append(item)
    return result


@router.post("/meetings", status_code=201)
def create_meeting(payload: MeetingInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    project = project_or_404(db, principal, payload.project_id, "communications.manage"); ensure_document(db, project.company_id, payload.minutes_document_id)
    row = ProjectMeeting(company_id=project.company_id, branch_id=project.branch_id, site_id=project.primary_site_id, project_id=project.id, meeting_number=issue_reference(db, project.company_id, "PROJECT_MEETING", "MTG"), meeting_type=payload.meeting_type, title=payload.title.strip(), meeting_date=payload.meeting_date, minutes_document_id=payload.minutes_document_id, notes=payload.notes, prepared_by=principal.user.full_name)
    db.add(row); db.flush(); audit(db, principal, "communications.meeting.created", row); commit(db); return row_dict(row)


@router.post("/meetings/{meeting_id:int}/actions", status_code=201)
def create_action(meeting_id: int, payload: ActionInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    meeting = owned(db, principal, ProjectMeeting, meeting_id, "communications.manage", "Meeting")
    if meeting.status not in {"draft", "rejected"}: raise HTTPException(status_code=409, detail="Meeting actions are frozen once minutes enter approval")
    if payload.owner_employee_id:
        employee=db.get(Employee,payload.owner_employee_id)
        if not employee or employee.company_id != meeting.company_id or employee.employment_status != "active": raise HTTPException(status_code=422, detail="Action owner must be an active company employee")
    next_number=(db.scalar(select(func.max(MeetingAction.action_number)).where(MeetingAction.meeting_id == meeting.id)) or 0)+1
    row=MeetingAction(company_id=meeting.company_id,branch_id=meeting.branch_id,site_id=meeting.site_id,project_id=meeting.project_id,meeting_id=meeting.id,action_number=next_number,title=payload.title.strip(),owner_employee_id=payload.owner_employee_id,due_date=payload.due_date,created_by=principal.user.full_name)
    db.add(row); db.flush(); audit(db,principal,"communications.meeting.action.created",row,{"meeting_id":meeting.id}); commit(db); return row_dict(row)


@router.post("/meetings/{meeting_id:int}/submit")
def submit_meeting(meeting_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row=owned(db,principal,ProjectMeeting,meeting_id,"communications.manage","Meeting")
    if row.status not in {"draft","rejected"}: raise HTTPException(status_code=409,detail="Only draft or rejected minutes can be submitted")
    if not row.minutes_document_id: raise HTTPException(status_code=409,detail="Controlled meeting-minutes evidence is required before submission")
    approval=request_approval(db,principal,"MEETING_MINUTES",row,f"Meeting minutes {row.meeting_number}"); row.status,row.approval_request_id,row.submitted_at="submitted",approval.id,utcnow(); audit(db,principal,"communications.meeting.submitted",row); commit(db); return row_dict(row)


@router.get("/actions")
def actions(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    anywhere(principal,"communications.view"); result=[]
    for row in db.scalars(select(MeetingAction).where(MeetingAction.company_id == principal.user.company_id).order_by(MeetingAction.due_date,MeetingAction.id.desc())).all():
        if not principal.can("communications.view",branch_id=row.branch_id,site_id=row.site_id): continue
        item=row_dict(row); meeting=db.get(ProjectMeeting,row.meeting_id); employee=db.get(Employee,row.owner_employee_id) if row.owner_employee_id else None; item.update({"meeting_number":meeting.meeting_number if meeting else "","meeting_title":meeting.title if meeting else "","owner_name":f"{employee.first_name} {employee.last_name}" if employee else ""}); result.append(item)
    return result


@router.post("/actions/{action_id:int}/complete")
def complete_action(action_id: int, payload: DocumentInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row=owned(db,principal,MeetingAction,action_id,"communications.manage","Meeting action")
    if row.status not in {"open","in_progress"}: raise HTTPException(status_code=409,detail="Only open meeting actions can be completed")
    ensure_document(db,row.company_id,payload.document_id); row.evidence_document_id,row.completion_note,row.status,row.completed_by,row.completed_at=payload.document_id,payload.note,"completed",principal.user.full_name,utcnow(); audit(db,principal,"communications.action.completed",row); commit(db); return row_dict(row)


@router.post("/actions/{action_id:int}/verify")
def verify_action(action_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row=owned(db,principal,MeetingAction,action_id,"communications.verify","Meeting action")
    if row.status != "completed": raise HTTPException(status_code=409,detail="Only completed meeting actions can be verified")
    if row.completed_by == principal.user.full_name and not allow_self_approval(db,row.company_id): raise HTTPException(status_code=422,detail="Self-verification is disabled by company policy")
    row.status,row.verified_by,row.verified_at="verified",principal.user.full_name,utcnow(); audit(db,principal,"communications.action.verified",row); commit(db); return row_dict(row)


@router.get("/approvals")
def approvals(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    anywhere(principal,"communications.view"); allowed={"project_correspondence","project_meetings"}; result=[]
    for row in db.scalars(select(ApprovalRequest).where(ApprovalRequest.company_id == principal.user.company_id,ApprovalRequest.entity_type.in_(allowed),ApprovalRequest.status == "pending").order_by(ApprovalRequest.requested_at)).all():
        if not principal.can("communications.view",branch_id=row.branch_id,site_id=row.site_id): continue
        item=row_dict(row); entity=db.get(ProjectCorrespondence,int(row.entity_id)) if row.entity_type=="project_correspondence" else db.get(ProjectMeeting,int(row.entity_id)); item["communication_reference"]=getattr(entity,"correspondence_number",None) or getattr(entity,"meeting_number",""); result.append(item)
    return result


@router.post("/approvals/{approval_id:int}/decision")
def decide(approval_id:int,payload:DecisionInput,db:Session=Depends(get_db),principal:Principal=Depends(current_principal))->dict[str,Any]:
    approval=db.get(ApprovalRequest,approval_id)
    if not approval or approval.company_id!=principal.user.company_id or approval.entity_type not in {"project_correspondence","project_meetings"}: raise HTTPException(status_code=404,detail="Communication approval request not found")
    entity=db.get(ProjectCorrespondence,int(approval.entity_id)) if approval.entity_type=="project_correspondence" else db.get(ProjectMeeting,int(approval.entity_id))
    if not entity: raise HTTPException(status_code=404,detail="Communication approval entity is unavailable")
    scope(principal,"communications.approve",entity.branch_id,entity.site_id)
    if approval.status!="pending" or entity.status!="submitted": raise HTTPException(status_code=409,detail="Communication approval request is not pending")
    step=db.scalar(select(ApprovalStep).where(ApprovalStep.workflow_id==approval.workflow_id,ApprovalStep.step_order==approval.current_step_order))
    if not step or not assignment_authorised(db,principal,step.role_id,entity.branch_id,entity.site_id): raise HTTPException(status_code=403,detail="Your active role assignment is not authorised for this communications approval step")
    if approval.requested_by==principal.user.full_name and not allow_self_approval(db,approval.company_id): raise HTTPException(status_code=422,detail="Self-approval is disabled by company policy")
    db.add(ApprovalAction(request_id=approval.id,step_order=step.step_order,role_id=step.role_id,actor_name=principal.user.full_name,action=payload.decision,comment=payload.comment))
    if payload.decision=="reject": approval.status,approval.completed_at,entity.status="rejected",utcnow(),"rejected"
    else:
        count=(db.scalar(select(func.count()).select_from(ApprovalAction).where(ApprovalAction.request_id==approval.id,ApprovalAction.step_order==step.step_order,ApprovalAction.action=="approve")) or 0)+1
        next_step=db.scalar(select(ApprovalStep).where(ApprovalStep.workflow_id==approval.workflow_id,ApprovalStep.step_order>step.step_order).order_by(ApprovalStep.step_order).limit(1)) if count>=step.required_approvals else None
        if next_step: approval.current_step_order=next_step.step_order
        elif count>=step.required_approvals: approval.status,approval.completed_at,entity.status,entity.approved_at="approved",utcnow(),"approved",utcnow()
    audit(db,principal,f"communications.approval.{payload.decision}",entity,{"approval_id":approval.id,"approval_status":approval.status,"step":step.step_order}); commit(db); return row_dict(approval)


@router.get("/dashboard")
def dashboard(db:Session=Depends(get_db),principal:Principal=Depends(current_principal))->dict[str,Any]:
    anywhere(principal,"communications.view"); today=date.today(); correspondence=[r for r in db.scalars(select(ProjectCorrespondence).where(ProjectCorrespondence.company_id==principal.user.company_id)).all() if principal.can("communications.view",branch_id=r.branch_id,site_id=r.site_id)]; actions_rows=[r for r in db.scalars(select(MeetingAction).where(MeetingAction.company_id==principal.user.company_id)).all() if principal.can("communications.view",branch_id=r.branch_id,site_id=r.site_id)]
    return {"open_correspondence":sum(r.status in {"draft","submitted","approved","recorded"} for r in correspondence),"overdue_responses":sum(bool(r.response_due_date and r.response_due_date<today and r.status!="closed") for r in correspondence),"pending_approvals":sum(r.status=="submitted" for r in correspondence)+sum(r.status=="submitted" for r in db.scalars(select(ProjectMeeting).where(ProjectMeeting.company_id==principal.user.company_id)).all()),"open_actions":sum(r.status in {"open","in_progress","completed"} for r in actions_rows),"overdue_actions":sum(bool(r.due_date and r.due_date<today and r.status!="verified") for r in actions_rows)}


@router.get("/exports/correspondence.csv")
def export_correspondence(db:Session=Depends(get_db),principal:Principal=Depends(current_principal))->StreamingResponse:
    anywhere(principal,"communications.export"); stream=io.StringIO(); fields=["correspondence_number","project_id","direction","classification","correspondence_type","subject","correspondence_date","response_due_date","status","external_reference"]; writer=csv.DictWriter(stream,fieldnames=fields); writer.writeheader()
    for row in db.scalars(select(ProjectCorrespondence).where(ProjectCorrespondence.company_id==principal.user.company_id)).all():
        if principal.can("communications.export",branch_id=row.branch_id,site_id=row.site_id): writer.writerow({key:row_dict(row).get(key,"") for key in fields})
    return StreamingResponse(iter([stream.getvalue()]),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=project-correspondence.csv"})


@router.get("/audit")
def audit_events(limit:int=Query(default=250,ge=1,le=1000),db:Session=Depends(get_db),principal:Principal=Depends(current_principal))->list[dict[str,Any]]:
    anywhere(principal,"communications.view"); rows=db.scalars(select(CommunicationAuditEvent).where(CommunicationAuditEvent.company_id==principal.user.company_id).order_by(CommunicationAuditEvent.occurred_at.desc()).limit(limit)).all(); return [row_dict(r) for r in rows if r.branch_id is None or principal.can("communications.view",branch_id=r.branch_id,site_id=r.site_id)]
