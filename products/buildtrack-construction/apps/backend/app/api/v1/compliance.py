from __future__ import annotations

import csv
import io
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
from app.models import ApprovalAction, ApprovalRequest, ApprovalStep, ApprovalWorkflow, ComplianceAuditEvent, ComplianceObligation, CompliancePolicy, ComplianceReview, Employee, NumberSequence, Permission, Project, Role, RolePermission
from app.security.access import Principal, current_principal

router = APIRouter(prefix="/compliance", tags=["Phase 22 - Integrated Compliance & Policy Control"])
PERMISSIONS = {"compliance.view": ("compliance", "view", "View policies, obligations, reviews and exceptions"), "compliance.manage": ("compliance", "manage", "Maintain policy and obligation control records"), "compliance.approve": ("compliance", "approve", "Independently approve policies and compliance reviews"), "compliance.export": ("compliance", "export", "Export controlled compliance registers")}

def anywhere(p: Principal, permission: str) -> None:
    if not p.has_permission_anywhere(permission): raise HTTPException(status_code=403, detail=f"Permission required: {permission}")
def scope(p: Principal, permission: str, branch_id: int, site_id: int | None) -> None:
    if not p.can(permission, branch_id=branch_id, site_id=site_id): raise HTTPException(status_code=403, detail=f"Permission required in this branch/site: {permission}")
def audit(db: Session, p: Principal, action: str, entity: Any, detail: dict[str, Any] | None = None) -> None:
    db.add(ComplianceAuditEvent(company_id=p.user.company_id,branch_id=getattr(entity,"branch_id",None),site_id=getattr(entity,"site_id",None),project_id=getattr(entity,"project_id",None),actor=p.user.full_name,action=action,entity_type=entity.__tablename__,entity_id=str(entity.id),detail=detail or {}))
def project_or_404(db: Session,p: Principal,project_id: int,permission: str) -> Project:
    row=db.get(Project,project_id)
    if not row or row.company_id!=p.user.company_id: raise HTTPException(status_code=404,detail="Project not found")
    scope(p,permission,row.branch_id,row.primary_site_id); return row
def owned(db:Session,p:Principal,model:Any,row_id:int,permission:str,label:str)->Any:
    row=db.get(model,row_id)
    if not row or row.company_id!=p.user.company_id: raise HTTPException(status_code=404,detail=f"{label} not found")
    scope(p,permission,row.branch_id,row.site_id); return row
def workflow(db:Session,company_id:int,code:str)->ApprovalWorkflow:
    row=db.scalar(select(ApprovalWorkflow).where(ApprovalWorkflow.company_id==company_id,ApprovalWorkflow.code==code,ApprovalWorkflow.is_active.is_(True)))
    if not row or not db.scalar(select(func.count()).select_from(ApprovalStep).where(ApprovalStep.workflow_id==row.id)): raise HTTPException(status_code=409,detail="Phase 22 approval workflow is not configured")
    return row
def approval_request(db:Session,p:Principal,code:str,entity:Any,title:str)->ApprovalRequest:
    selected=workflow(db,p.user.company_id,code); row=ApprovalRequest(company_id=p.user.company_id,workflow_id=selected.id,branch_id=entity.branch_id,site_id=entity.site_id,entity_type=entity.__tablename__,entity_id=str(entity.id),reference=issue_reference(db,p.user.company_id,"COMPLIANCE_APPROVAL","CMP"),title=title,amount=Decimal("0"),status="pending",current_step_order=1,requested_by=p.user.full_name); db.add(row);db.flush();return row

def bootstrap_data(db:Session,company_id:int)->None:
    permissions={}
    for code,(module,action,description) in PERMISSIONS.items():
        row=db.scalar(select(Permission).where(Permission.code==code))
        if not row: row=Permission(code=code,module=module,action=action,description=description);db.add(row);db.flush()
        permissions[code]=row
    roles={row.code:row for row in db.scalars(select(Role).where(Role.company_id==company_id)).all()}
    for code,name,level in (("COMPLIANCE_MANAGER","Compliance Manager","company"),("COMPLIANCE_OFFICER","Compliance Officer","branch"),("COMPLIANCE_REVIEWER","Compliance Reviewer","company")):
        if code not in roles: roles[code]=Role(company_id=company_id,code=code,name=name,scope_level=level,description=f"Phase 22 {name.lower()} role",is_system=True,is_active=True);db.add(roles[code]);db.flush()
    grants={"SYSTEM_ADMIN":set(PERMISSIONS),"HQ_EXECUTIVE":set(PERMISSIONS),"BRANCH_MANAGER":set(PERMISSIONS),"PROJECT_MANAGER":{"compliance.view","compliance.manage","compliance.export"},"SITE_MANAGER":{"compliance.view","compliance.manage"},"APPROVER":{"compliance.approve"},"AUDITOR":{"compliance.view","compliance.export"},"COMPLIANCE_MANAGER":set(PERMISSIONS),"COMPLIANCE_OFFICER":{"compliance.view","compliance.manage","compliance.export"},"COMPLIANCE_REVIEWER":{"compliance.view","compliance.approve","compliance.export"}}
    for role_code,codes in grants.items():
        role=roles.get(role_code)
        if not role: continue
        existing=set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id==role.id)).all())
        for code in codes:
            if permissions[code].id not in existing: db.add(RolePermission(role_id=role.id,permission_id=permissions[code].id));existing.add(permissions[code].id)
    for code,name,prefix in (("COMPLIANCE_POLICY","Compliance Policy","POL"),("COMPLIANCE_OBLIGATION","Compliance Obligation","OBL"),("COMPLIANCE_REVIEW","Compliance Review","CRV"),("COMPLIANCE_APPROVAL","Compliance Approval","CMP")):
        if not db.scalar(select(NumberSequence).where(NumberSequence.company_id==company_id,NumberSequence.code==code)): db.add(NumberSequence(company_id=company_id,code=code,name=name,prefix=prefix,next_number=1,padding=5,reset_period="yearly"))
    branch,hq=roles.get("BRANCH_MANAGER"),roles.get("HQ_EXECUTIVE")
    if not branch or not hq: raise HTTPException(status_code=409,detail="Branch Manager and HQ Executive roles are required for Phase 22")
    for code,name in (("COMPLIANCE_POLICY","Policy Approval"),("COMPLIANCE_REVIEW","Compliance Review Approval")):
        row=db.scalar(select(ApprovalWorkflow).where(ApprovalWorkflow.company_id==company_id,ApprovalWorkflow.code==code))
        if not row: row=ApprovalWorkflow(company_id=company_id,code=code,name=name,module="compliance",description=f"Controlled {name.lower()}",min_amount=Decimal("0"),is_active=True);db.add(row);db.flush()
        if not db.scalar(select(func.count()).select_from(ApprovalStep).where(ApprovalStep.workflow_id==row.id)): db.add_all([ApprovalStep(workflow_id=row.id,step_order=1,name="Branch compliance review",role_id=branch.id,required_approvals=1,escalation_hours=24),ApprovalStep(workflow_id=row.id,step_order=2,name="Head Office compliance approval",role_id=hq.id,required_approvals=1,escalation_hours=48)])

class PolicyInput(BaseModel):
    model_config=ConfigDict(extra="forbid")
    project_id:int; policy_code:str=Field(min_length=2,max_length=80); title:str=Field(min_length=2,max_length=300); category:Literal["governance","environmental","quality","commercial","people","information","other"]; effective_date:date; review_due_date:date|None=None; policy_document_id:int|None=None; notes:str|None=Field(default=None,max_length=4000)
class ObligationInput(BaseModel):
    model_config=ConfigDict(extra="forbid")
    project_id:int; policy_id:int|None=None; source_type:Literal["policy","contract","client","regulatory","internal","other"]; source_reference:str=Field(min_length=2,max_length=240); title:str=Field(min_length=2,max_length=300); owner_employee_id:int|None=None; next_due_date:date; recurrence_days:int|None=Field(default=None,ge=1,le=3650); evidence_document_id:int|None=None; notes:str|None=Field(default=None,max_length=4000)
class ReviewInput(BaseModel):
    model_config=ConfigDict(extra="forbid")
    review_type:Literal["acknowledgement","evidence_review","internal_assessment","other"]; review_date:date; result:Literal["compliant","attention","non_compliant"]; evidence_document_id:int|None=None; finding:str|None=Field(default=None,max_length=4000); corrective_action:str|None=Field(default=None,max_length=4000)
class DecisionInput(BaseModel):
    model_config=ConfigDict(extra="forbid")
    decision:Literal["approve","reject"];comment:str|None=Field(default=None,max_length=2000)

@router.post("/bootstrap")
def bootstrap(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
    if not p.has_company_permission("company.manage") and not p.has_company_permission("compliance.manage"): raise HTTPException(status_code=403,detail="Company administration is required to initialise Phase 22")
    bootstrap_data(db,p.user.company_id);commit(db);return {"phase":22,"status":"ready"}
@router.get("/catalog")
def catalog(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
    anywhere(p,"compliance.view");projects=[row_dict(r) for r in db.scalars(select(Project).where(Project.company_id==p.user.company_id,Project.status.in_(("mobilising","ready","active"))).order_by(Project.name)).all() if p.can("compliance.view",branch_id=r.branch_id,site_id=r.primary_site_id)];employees=[row_dict(r) for r in db.scalars(select(Employee).where(Employee.company_id==p.user.company_id,Employee.employment_status=="active").order_by(Employee.first_name,Employee.last_name)).all()];return {"projects":projects,"employees":employees,"permissions":[code for code in PERMISSIONS if p.has_permission_anywhere(code)]}
@router.get("/policies")
def policies(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->list[dict[str,Any]]:
    anywhere(p,"compliance.view");return [row_dict(r) for r in db.scalars(select(CompliancePolicy).where(CompliancePolicy.company_id==p.user.company_id).order_by(CompliancePolicy.review_due_date,CompliancePolicy.id.desc())).all() if p.can("compliance.view",branch_id=r.branch_id,site_id=r.site_id)]
@router.post("/policies",status_code=201)
def create_policy(payload:PolicyInput,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
    project=project_or_404(db,p,payload.project_id,"compliance.manage")
    if payload.review_due_date and payload.review_due_date<payload.effective_date: raise HTTPException(status_code=422,detail="Policy review date cannot precede effective date")
    ensure_document(db,project.company_id,payload.policy_document_id);latest=db.scalar(select(func.max(CompliancePolicy.version)).where(CompliancePolicy.project_id==project.id,CompliancePolicy.policy_code==payload.policy_code.strip())) or 0
    row=CompliancePolicy(company_id=project.company_id,branch_id=project.branch_id,site_id=project.primary_site_id,project_id=project.id,policy_number=issue_reference(db,project.company_id,"COMPLIANCE_POLICY","POL"),policy_code=payload.policy_code.strip().upper(),version=int(latest)+1,title=payload.title.strip(),category=payload.category,effective_date=payload.effective_date,review_due_date=payload.review_due_date,policy_document_id=payload.policy_document_id,notes=payload.notes,prepared_by=p.user.full_name);db.add(row);db.flush();audit(db,p,"compliance.policy.created",row,{"version":row.version});commit(db);return row_dict(row)
@router.post("/policies/{policy_id:int}/submit")
def submit_policy(policy_id:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
    row=owned(db,p,CompliancePolicy,policy_id,"compliance.manage","Policy")
    if row.status not in {"draft","rejected"}: raise HTTPException(status_code=409,detail="Only draft or rejected policies can be submitted")
    if not row.policy_document_id: raise HTTPException(status_code=409,detail="An active controlled policy document is required before approval")
    approval=approval_request(db,p,"COMPLIANCE_POLICY",row,f"Policy {row.policy_number}");row.status,row.approval_request_id,row.submitted_at="submitted",approval.id,utcnow();audit(db,p,"compliance.policy.submitted",row);commit(db);return row_dict(row)
@router.get("/obligations")
def obligations(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->list[dict[str,Any]]:
    anywhere(p,"compliance.view");out=[]
    for r in db.scalars(select(ComplianceObligation).where(ComplianceObligation.company_id==p.user.company_id).order_by(ComplianceObligation.next_due_date)).all():
        if not p.can("compliance.view",branch_id=r.branch_id,site_id=r.site_id):continue
        item=row_dict(r);policy=db.get(CompliancePolicy,r.policy_id) if r.policy_id else None;employee=db.get(Employee,r.owner_employee_id) if r.owner_employee_id else None;item.update({"policy_number":policy.policy_number if policy else "","owner_name":f"{employee.first_name} {employee.last_name}" if employee else ""});out.append(item)
    return out
@router.post("/obligations",status_code=201)
def create_obligation(payload:ObligationInput,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
    project=project_or_404(db,p,payload.project_id,"compliance.manage");ensure_document(db,project.company_id,payload.evidence_document_id)
    if payload.policy_id:
        policy=owned(db,p,CompliancePolicy,payload.policy_id,"compliance.manage","Policy")
        if policy.project_id!=project.id or policy.status!="approved":raise HTTPException(status_code=422,detail="Linked policy must be approved and belong to the selected project")
    if payload.owner_employee_id:
        employee=db.get(Employee,payload.owner_employee_id)
        if not employee or employee.company_id!=project.company_id or employee.employment_status!="active":raise HTTPException(status_code=422,detail="Obligation owner must be an active company employee")
    row=ComplianceObligation(company_id=project.company_id,branch_id=project.branch_id,site_id=project.primary_site_id,project_id=project.id,policy_id=payload.policy_id,obligation_number=issue_reference(db,project.company_id,"COMPLIANCE_OBLIGATION","OBL"),source_type=payload.source_type,source_reference=payload.source_reference.strip(),title=payload.title.strip(),owner_employee_id=payload.owner_employee_id,next_due_date=payload.next_due_date,recurrence_days=payload.recurrence_days,evidence_document_id=payload.evidence_document_id,notes=payload.notes,created_by=p.user.full_name);db.add(row);db.flush();audit(db,p,"compliance.obligation.created",row);commit(db);return row_dict(row)
@router.get("/reviews")
def reviews(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->list[dict[str,Any]]:
    anywhere(p,"compliance.view");out=[]
    for r in db.scalars(select(ComplianceReview).where(ComplianceReview.company_id==p.user.company_id).order_by(ComplianceReview.review_date.desc(),ComplianceReview.id.desc())).all():
        if p.can("compliance.view",branch_id=r.branch_id,site_id=r.site_id): item=row_dict(r);obligation=db.get(ComplianceObligation,r.obligation_id);item["obligation_number"]=obligation.obligation_number if obligation else "";item["obligation_title"]=obligation.title if obligation else "";out.append(item)
    return out
@router.post("/obligations/{obligation_id:int}/reviews",status_code=201)
def create_review(obligation_id:int,payload:ReviewInput,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
    obligation=owned(db,p,ComplianceObligation,obligation_id,"compliance.manage","Compliance obligation")
    if obligation.status!="active":raise HTTPException(status_code=409,detail="Only active compliance obligations can be reviewed")
    ensure_document(db,obligation.company_id,payload.evidence_document_id)
    if payload.result!="compliant" and not payload.corrective_action:raise HTTPException(status_code=422,detail="A corrective action is required for an attention or non-compliant review")
    row=ComplianceReview(company_id=obligation.company_id,branch_id=obligation.branch_id,site_id=obligation.site_id,project_id=obligation.project_id,obligation_id=obligation.id,review_number=issue_reference(db,obligation.company_id,"COMPLIANCE_REVIEW","CRV"),review_type=payload.review_type,review_date=payload.review_date,result=payload.result,evidence_document_id=payload.evidence_document_id,finding=payload.finding,corrective_action=payload.corrective_action,prepared_by=p.user.full_name);db.add(row);db.flush();audit(db,p,"compliance.review.created",row,{"obligation_id":obligation.id});commit(db);return row_dict(row)
@router.post("/reviews/{review_id:int}/submit")
def submit_review(review_id:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
    row=owned(db,p,ComplianceReview,review_id,"compliance.manage","Compliance review")
    if row.status not in {"draft","rejected"}:raise HTTPException(status_code=409,detail="Only draft or rejected reviews can be submitted")
    if not row.evidence_document_id:raise HTTPException(status_code=409,detail="Controlled review evidence is required before approval")
    approval=approval_request(db,p,"COMPLIANCE_REVIEW",row,f"Compliance review {row.review_number}");row.status,row.approval_request_id,row.submitted_at="submitted",approval.id,utcnow();audit(db,p,"compliance.review.submitted",row);commit(db);return row_dict(row)
@router.get("/approvals")
def approvals(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->list[dict[str,Any]]:
    anywhere(p,"compliance.view");out=[]
    for r in db.scalars(select(ApprovalRequest).where(ApprovalRequest.company_id==p.user.company_id,ApprovalRequest.entity_type.in_(("compliance_policies","compliance_reviews")),ApprovalRequest.status=="pending").order_by(ApprovalRequest.requested_at)).all():
        if not p.can("compliance.view",branch_id=r.branch_id,site_id=r.site_id):continue
        item=row_dict(r);entity=db.get(CompliancePolicy,int(r.entity_id)) if r.entity_type=="compliance_policies" else db.get(ComplianceReview,int(r.entity_id));item["control_reference"]=getattr(entity,"policy_number",None) or getattr(entity,"review_number","");out.append(item)
    return out
@router.post("/approvals/{approval_id:int}/decision")
def decide(approval_id:int,payload:DecisionInput,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
    approval=db.get(ApprovalRequest,approval_id)
    if not approval or approval.company_id!=p.user.company_id or approval.entity_type not in {"compliance_policies","compliance_reviews"}:raise HTTPException(status_code=404,detail="Compliance approval request not found")
    entity=db.get(CompliancePolicy,int(approval.entity_id)) if approval.entity_type=="compliance_policies" else db.get(ComplianceReview,int(approval.entity_id))
    if not entity:raise HTTPException(status_code=404,detail="Compliance approval entity is unavailable")
    scope(p,"compliance.approve",entity.branch_id,entity.site_id)
    if approval.status!="pending" or entity.status!="submitted":raise HTTPException(status_code=409,detail="Compliance approval request is not pending")
    step=db.scalar(select(ApprovalStep).where(ApprovalStep.workflow_id==approval.workflow_id,ApprovalStep.step_order==approval.current_step_order))
    if not step or not assignment_authorised(db,p,step.role_id,entity.branch_id,entity.site_id):raise HTTPException(status_code=403,detail="Your active role assignment is not authorised for this compliance approval step")
    if approval.requested_by==p.user.full_name and not allow_self_approval(db,approval.company_id):raise HTTPException(status_code=422,detail="Self-approval is disabled by company policy")
    db.add(ApprovalAction(request_id=approval.id,step_order=step.step_order,role_id=step.role_id,actor_name=p.user.full_name,action=payload.decision,comment=payload.comment))
    if payload.decision=="reject":approval.status,approval.completed_at,entity.status="rejected",utcnow(),"rejected"
    else:
        count=(db.scalar(select(func.count()).select_from(ApprovalAction).where(ApprovalAction.request_id==approval.id,ApprovalAction.step_order==step.step_order,ApprovalAction.action=="approve")) or 0)+1;next_step=db.scalar(select(ApprovalStep).where(ApprovalStep.workflow_id==approval.workflow_id,ApprovalStep.step_order>step.step_order).order_by(ApprovalStep.step_order).limit(1)) if count>=step.required_approvals else None
        if next_step:approval.current_step_order=next_step.step_order
        elif count>=step.required_approvals:
            approval.status,approval.completed_at,entity.status,entity.approved_at="approved",utcnow(),"approved",utcnow()
            if approval.entity_type=="compliance_policies":
                for old in db.scalars(select(CompliancePolicy).where(CompliancePolicy.project_id==entity.project_id,CompliancePolicy.policy_code==entity.policy_code,CompliancePolicy.status=="approved",CompliancePolicy.id!=entity.id)).all():old.status,old.superseded_at="superseded",utcnow()
            else:
                obligation=db.get(ComplianceObligation,entity.obligation_id)
                if obligation and obligation.recurrence_days:obligation.next_due_date=entity.review_date+timedelta(days=obligation.recurrence_days)
    audit(db,p,f"compliance.approval.{payload.decision}",entity,{"approval_id":approval.id,"step":step.step_order});commit(db);return row_dict(approval)
@router.get("/dashboard")
def dashboard(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
    anywhere(p,"compliance.view");today=date.today();policies=[r for r in db.scalars(select(CompliancePolicy).where(CompliancePolicy.company_id==p.user.company_id)).all() if p.can("compliance.view",branch_id=r.branch_id,site_id=r.site_id)];obligations=[r for r in db.scalars(select(ComplianceObligation).where(ComplianceObligation.company_id==p.user.company_id)).all() if p.can("compliance.view",branch_id=r.branch_id,site_id=r.site_id)];reviews=[r for r in db.scalars(select(ComplianceReview).where(ComplianceReview.company_id==p.user.company_id)).all() if p.can("compliance.view",branch_id=r.branch_id,site_id=r.site_id)];return {"approved_policies":sum(r.status=="approved" for r in policies),"policy_reviews_due":sum(bool(r.review_due_date and r.review_due_date<=today+timedelta(days=30) and r.status=="approved") for r in policies),"active_obligations":sum(r.status=="active" for r in obligations),"overdue_obligations":sum(r.status=="active" and r.next_due_date<today for r in obligations),"pending_reviews":sum(r.status=="submitted" for r in reviews),"non_compliant_reviews":sum(r.result=="non_compliant" and r.status=="approved" for r in reviews)}
@router.get("/exports/obligations.csv")
def export_obligations(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->StreamingResponse:
    anywhere(p,"compliance.export");stream=io.StringIO();fields=["obligation_number","project_id","source_type","source_reference","title","next_due_date","recurrence_days","status"];writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
    for row in db.scalars(select(ComplianceObligation).where(ComplianceObligation.company_id==p.user.company_id)).all():
        if p.can("compliance.export",branch_id=row.branch_id,site_id=row.site_id):writer.writerow({key:row_dict(row).get(key,"") for key in fields})
    return StreamingResponse(iter([stream.getvalue()]),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=compliance-obligations.csv"})
@router.get("/audit")
def audit_events(limit:int=Query(default=250,ge=1,le=1000),db:Session=Depends(get_db),p:Principal=Depends(current_principal))->list[dict[str,Any]]:
    anywhere(p,"compliance.view");rows=db.scalars(select(ComplianceAuditEvent).where(ComplianceAuditEvent.company_id==p.user.company_id).order_by(ComplianceAuditEvent.occurred_at.desc()).limit(limit)).all();return [row_dict(r) for r in rows if r.branch_id is None or p.can("compliance.view",branch_id=r.branch_id,site_id=r.site_id)]
