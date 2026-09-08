from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.procurement import commit, ensure_document, issue_reference, row_dict, utcnow
from app.db.session import get_db
from app.models import AssuranceAuditEvent, CompanySetting, NumberSequence, Permission, Project, ProjectAssuranceRecord, ProjectDocumentRegister, Role, RolePermission
from app.security.access import Principal, current_principal

router = APIRouter(prefix="/assurance", tags=["Phase 13 - Document, HSE and Quality Assurance"])
PERMISSIONS = {"assurance.view": ("assurance", "view", "View controlled project assurance records"), "assurance.manage": ("assurance", "manage", "Register documents, HSE and quality records"), "assurance.review": ("assurance", "review", "Independently review HSE and quality records")}
RECORD_TYPES = ("rfi", "site_instruction", "permit_to_work", "toolbox_talk", "hse_inspection", "quality_nonconformance", "corrective_action")

def require_anywhere(p: Principal, permission: str) -> None:
    if not p.has_permission_anywhere(permission): raise HTTPException(status_code=403, detail=f"Permission required: {permission}")
def project(db: Session, p: Principal, project_id: int, permission: str) -> Project:
    row=db.get(Project,project_id)
    if not row or row.company_id!=p.user.company_id: raise HTTPException(status_code=404,detail="Project not found")
    if not p.can(permission,branch_id=row.branch_id,site_id=row.primary_site_id): raise HTTPException(status_code=403,detail=f"Permission required in this branch/site: {permission}")
    return row
def audit(db: Session,p:Principal,action:str,entity:Any,project_row:Project,detail:dict[str,Any]|None=None)->None:
    db.add(AssuranceAuditEvent(company_id=p.user.company_id,branch_id=project_row.branch_id,site_id=project_row.primary_site_id,project_id=project_row.id,actor=p.user.full_name,action=action,entity_type=entity.__tablename__,entity_id=str(entity.id),detail=detail or {}))
def bootstrap_permissions(db:Session,company_id:int)->None:
    permissions={}
    for code,(module,action,description) in PERMISSIONS.items():
        row=db.scalar(select(Permission).where(Permission.code==code))
        if not row: row=Permission(code=code,module=module,action=action,description=description);db.add(row);db.flush()
        permissions[code]=row
    roles={row.code:row for row in db.scalars(select(Role).where(Role.company_id==company_id)).all()}
    for code,name,scope in (("HSE_MANAGER","HSE Manager","company"),("QUALITY_MANAGER","Quality Manager","company"),("DOCUMENT_CONTROLLER","Document Controller","branch")):
        if code not in roles: row=Role(company_id=company_id,code=code,name=name,scope_level=scope,description=f"Phase 13 {name.lower()} role",is_system=True,is_active=True);db.add(row);db.flush();roles[code]=row
    grants={"SYSTEM_ADMIN":set(PERMISSIONS),"HQ_EXECUTIVE":set(PERMISSIONS),"BRANCH_MANAGER":set(PERMISSIONS),"SITE_MANAGER":set(PERMISSIONS),"PROJECT_MANAGER":set(PERMISSIONS),"HSE_MANAGER":set(PERMISSIONS),"QUALITY_MANAGER":set(PERMISSIONS),"DOCUMENT_CONTROLLER":{"assurance.view","assurance.manage"},"AUDITOR":{"assurance.view"}}
    for role_code,codes in grants.items():
        role=roles.get(role_code)
        if not role: continue
        existing=set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id==role.id)).all())
        for code in codes:
            if permissions[code].id not in existing: db.add(RolePermission(role_id=role.id,permission_id=permissions[code].id));existing.add(permissions[code].id)
    if not db.scalar(select(NumberSequence).where(NumberSequence.company_id==company_id,NumberSequence.code=="ASSURANCE_RECORD")):
        db.add(NumberSequence(company_id=company_id,code="ASSURANCE_RECORD",name="Project Assurance Record",prefix="ASR",next_number=1,padding=5,reset_period="yearly"))
    if not db.scalar(select(CompanySetting).where(CompanySetting.company_id==company_id,CompanySetting.key=="assurance_policy")): db.add(CompanySetting(company_id=company_id,key="assurance_policy",value={"critical_evidence_required":True,"review_required_types":["permit_to_work","hse_inspection","quality_nonconformance","corrective_action"]},description="Phase 13 assurance governance"))

class RegisterInput(BaseModel):
    model_config=ConfigDict(extra="forbid")
    project_id:int; document_id:int; document_number:str=Field(min_length=2,max_length=120); revision_code:str=Field(min_length=1,max_length=64); discipline:str=Field(default="general",max_length=80); title:str=Field(min_length=2,max_length=300); issue_date:date; issued_to:str|None=Field(default=None,max_length=255); supersedes_id:int|None=None; notes:str|None=None
class RecordInput(BaseModel):
    model_config=ConfigDict(extra="forbid")
    project_id:int; record_type:Literal["rfi","site_instruction","permit_to_work","toolbox_talk","hse_inspection","quality_nonconformance","corrective_action"]; title:str=Field(min_length=2,max_length=300); description:str=Field(min_length=5); priority:Literal["low","normal","high","critical"]="normal"; record_date:date; due_date:date|None=None; document_id:int|None=None; parent_record_id:int|None=None; checklist:dict[str,Any]=Field(default_factory=dict); assigned_to:str|None=Field(default=None,max_length=255)
class ReviewInput(BaseModel):
    model_config=ConfigDict(extra="forbid")
    decision:Literal["close","return"]
    comment:str|None=Field(default=None,max_length=2000)

@router.post("/bootstrap")
def bootstrap(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
    if not p.has_company_permission("company.manage") and not p.has_company_permission("assurance.manage"): raise HTTPException(status_code=403,detail="Company-level administration is required to initialise Phase 13")
    bootstrap_permissions(db,p.user.company_id);commit(db);return {"phase":13,"status":"ready"}
@router.get("/projects")
def projects(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->list[dict[str,Any]]:
    require_anywhere(p,"assurance.view");return [row_dict(row) for row in db.scalars(select(Project).where(Project.company_id==p.user.company_id)).all() if p.can("assurance.view",branch_id=row.branch_id,site_id=row.primary_site_id)]
@router.get("/documents")
def documents(project_id:int|None=None,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->list[dict[str,Any]]:
    require_anywhere(p,"assurance.view"); rows=db.scalars(select(ProjectDocumentRegister).where(ProjectDocumentRegister.company_id==p.user.company_id).order_by(ProjectDocumentRegister.registered_at.desc())).all();return [row_dict(row) for row in rows if (project_id is None or row.project_id==project_id) and p.can("assurance.view",branch_id=row.branch_id,site_id=row.site_id)]
@router.post("/documents",status_code=201)
def register_document(payload:RegisterInput,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
    pr=project(db,p,payload.project_id,"assurance.manage");ensure_document(db,pr.company_id,payload.document_id)
    if payload.supersedes_id:
        old=db.get(ProjectDocumentRegister,payload.supersedes_id)
        if not old or old.project_id!=pr.id: raise HTTPException(status_code=422,detail="Superseded revision does not belong to this project")
        old.status="superseded"
    row=ProjectDocumentRegister(company_id=pr.company_id,branch_id=pr.branch_id,site_id=pr.primary_site_id,project_id=pr.id,document_id=payload.document_id,document_number=payload.document_number,revision_code=payload.revision_code,discipline=payload.discipline,title=payload.title,issue_date=payload.issue_date,issued_to=payload.issued_to,supersedes_id=payload.supersedes_id,notes=payload.notes,registered_by=p.user.full_name);db.add(row);db.flush();audit(db,p,"assurance.document.registered",row,pr);commit(db,"That project document revision already exists");return row_dict(row)
@router.get("/records")
def records(project_id:int|None=None,record_type:str|None=None,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->list[dict[str,Any]]:
    require_anywhere(p,"assurance.view");rows=db.scalars(select(ProjectAssuranceRecord).where(ProjectAssuranceRecord.company_id==p.user.company_id).order_by(ProjectAssuranceRecord.record_date.desc(),ProjectAssuranceRecord.id.desc())).all();return [row_dict(row) for row in rows if (project_id is None or row.project_id==project_id) and (record_type is None or row.record_type==record_type) and p.can("assurance.view",branch_id=row.branch_id,site_id=row.site_id)]
@router.post("/records",status_code=201)
def create_record(payload:RecordInput,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
    pr=project(db,p,payload.project_id,"assurance.manage");ensure_document(db,pr.company_id,payload.document_id)
    if payload.parent_record_id:
        parent=db.get(ProjectAssuranceRecord,payload.parent_record_id)
        if not parent or parent.project_id!=pr.id: raise HTTPException(status_code=422,detail="Parent assurance record does not belong to this project")
    row=ProjectAssuranceRecord(company_id=pr.company_id,branch_id=pr.branch_id,site_id=pr.primary_site_id,project_id=pr.id,parent_record_id=payload.parent_record_id,document_id=payload.document_id,record_number=issue_reference(db,pr.company_id,"ASSURANCE_RECORD","ASR"),record_type=payload.record_type,title=payload.title,description=payload.description,priority=payload.priority,record_date=payload.record_date,due_date=payload.due_date,checklist=payload.checklist,assigned_to=payload.assigned_to,created_by=p.user.full_name);db.add(row);db.flush();audit(db,p,"assurance.record.created",row,pr,{"type":row.record_type,"priority":row.priority});commit(db);return row_dict(row)
@router.post("/records/{record_id:int}/submit")
def submit_record(record_id:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
    row=db.get(ProjectAssuranceRecord,record_id)
    if not row or row.company_id!=p.user.company_id: raise HTTPException(status_code=404,detail="Assurance record not found")
    pr=project(db,p,row.project_id,"assurance.manage")
    if row.status not in {"draft","returned"}: raise HTTPException(status_code=409,detail="Only draft/returned assurance records can be submitted")
    cfg=db.scalar(select(CompanySetting).where(CompanySetting.company_id==p.user.company_id,CompanySetting.key=="assurance_policy"));require_evidence=bool((cfg.value if cfg else {}).get("critical_evidence_required",True))
    if require_evidence and row.priority=="critical" and not row.document_id: raise HTTPException(status_code=409,detail="Critical assurance records require controlled evidence before review")
    row.status,row.submitted_at="pending_review",utcnow();audit(db,p,"assurance.record.submitted",row,pr);commit(db);return row_dict(row)
@router.post("/records/{record_id:int}/review")
def review_record(record_id:int,payload:ReviewInput,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
    row=db.get(ProjectAssuranceRecord,record_id)
    if not row or row.company_id!=p.user.company_id: raise HTTPException(status_code=404,detail="Assurance record not found")
    pr=project(db,p,row.project_id,"assurance.review")
    if row.status!="pending_review": raise HTTPException(status_code=409,detail="Assurance record is not awaiting review")
    if row.created_by==p.user.full_name: raise HTTPException(status_code=422,detail="The record creator cannot complete its independent review")
    row.status="closed" if payload.decision=="close" else "returned";row.reviewed_by=p.user.full_name;row.reviewed_at=utcnow();row.review_comment=payload.comment;audit(db,p,f"assurance.record.{payload.decision}d",row,pr,{"comment":payload.comment});commit(db);return row_dict(row)
@router.get("/dashboard")
def dashboard(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
    require_anywhere(p,"assurance.view"); rows=[row for row in db.scalars(select(ProjectAssuranceRecord).where(ProjectAssuranceRecord.company_id==p.user.company_id)).all() if p.can("assurance.view",branch_id=row.branch_id,site_id=row.site_id)]; today=date.today();return {"open":sum(row.status in {"draft","returned","pending_review"} for row in rows),"critical_open":sum(row.priority=="critical" and row.status!="closed" for row in rows),"overdue":sum(row.due_date is not None and row.due_date<today and row.status!="closed" for row in rows),"by_type":{kind:sum(row.record_type==kind for row in rows) for kind in RECORD_TYPES},"document_revisions":len(documents(db=db,p=p))}
@router.get("/audit")
def audit_events(limit:int=Query(default=250,ge=1,le=1000),db:Session=Depends(get_db),p:Principal=Depends(current_principal))->list[dict[str,Any]]:
    require_anywhere(p,"assurance.view");rows=db.scalars(select(AssuranceAuditEvent).where(AssuranceAuditEvent.company_id==p.user.company_id).order_by(AssuranceAuditEvent.occurred_at.desc()).limit(limit)).all();return [row_dict(row) for row in rows if row.branch_id is None or p.can("assurance.view",branch_id=row.branch_id,site_id=row.site_id)]
