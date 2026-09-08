from __future__ import annotations
from datetime import datetime
from typing import Any, Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.v1.procurement import commit, row_dict, utcnow
from app.db.session import get_db
from app.models import OfflineFieldSubmission, Permission, Project, Role, RolePermission
from app.security.access import Principal, current_principal
router=APIRouter(prefix="/mobile",tags=["Phase 14 - Mobile Offline Field Capture"])
PERMISSIONS={"mobile.capture":("mobile","capture","Capture offline field evidence"),"mobile.review":("mobile","review","Review synchronised field evidence")}
TYPES=("daily_diary","attendance","material_delivery","plant_usage","photo_evidence","inspection")
def allowed(p:Principal,permission:str,pr:Project)->None:
 if not p.can(permission,branch_id=pr.branch_id,site_id=pr.primary_site_id):raise HTTPException(status_code=403,detail=f"Permission required in this branch/site: {permission}")
def project(db:Session,p:Principal,pid:int,permission:str)->Project:
 row=db.get(Project,pid)
 if not row or row.company_id!=p.user.company_id:raise HTTPException(status_code=404,detail="Project not found")
 allowed(p,permission,row);return row
def bootstrap_permissions(db:Session,cid:int)->None:
 perms={}
 for code,(module,action,description) in PERMISSIONS.items():
  row=db.scalar(select(Permission).where(Permission.code==code))
  if not row:row=Permission(code=code,module=module,action=action,description=description);db.add(row);db.flush()
  perms[code]=row
 roles={r.code:r for r in db.scalars(select(Role).where(Role.company_id==cid)).all()}
 for code,name,scope in (("FIELD_OFFICER","Field Officer","site"),("MOBILE_REVIEWER","Mobile Reviewer","branch")):
  if code not in roles:row=Role(company_id=cid,code=code,name=name,scope_level=scope,description=f"Phase 14 {name.lower()} role",is_system=True,is_active=True);db.add(row);db.flush();roles[code]=row
 grants={"SYSTEM_ADMIN":set(PERMISSIONS),"HQ_EXECUTIVE":set(PERMISSIONS),"BRANCH_MANAGER":set(PERMISSIONS),"SITE_MANAGER":set(PERMISSIONS),"PROJECT_MANAGER":set(PERMISSIONS),"FIELD_OFFICER":{"mobile.capture"},"MOBILE_REVIEWER":{"mobile.capture","mobile.review"}}
 for code,codes in grants.items():
  role=roles.get(code)
  if not role:continue
  existing=set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id==role.id)).all())
  for permission in codes:
   if perms[permission].id not in existing:db.add(RolePermission(role_id=role.id,permission_id=perms[permission].id));existing.add(perms[permission].id)
class SubmissionInput(BaseModel):
 model_config=ConfigDict(extra="forbid")
 project_id:int;device_id:str=Field(min_length=8,max_length=120);client_submission_id:str=Field(min_length=8,max_length=120);submission_type:Literal["daily_diary","attendance","material_delivery","plant_usage","photo_evidence","inspection"];captured_at:datetime;payload:dict[str,Any]=Field(default_factory=dict)
class ReviewInput(BaseModel):
 model_config=ConfigDict(extra="forbid")
 decision:Literal["accepted","returned"]
 note:str|None=Field(default=None,max_length=2000)
@router.post("/bootstrap")
def bootstrap(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
 if not p.has_company_permission("company.manage") and not p.has_company_permission("mobile.review"):raise HTTPException(status_code=403,detail="Company-level administration is required to initialise mobile capture")
 bootstrap_permissions(db,p.user.company_id);commit(db);return {"phase":14,"status":"ready","offline":"local device queue with controlled server review"}
@router.get("/projects")
def projects(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->list[dict[str,Any]]:
 if not p.has_permission_anywhere("mobile.capture"):raise HTTPException(status_code=403,detail="Permission required: mobile.capture")
 return [row_dict(r) for r in db.scalars(select(Project).where(Project.company_id==p.user.company_id)).all() if p.can("mobile.capture",branch_id=r.branch_id,site_id=r.primary_site_id)]
@router.post("/submissions",status_code=201)
def submit(payload:SubmissionInput,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
 pr=project(db,p,payload.project_id,"mobile.capture")
 existing=db.scalar(select(OfflineFieldSubmission).where(OfflineFieldSubmission.company_id==p.user.company_id,OfflineFieldSubmission.device_id==payload.device_id,OfflineFieldSubmission.client_submission_id==payload.client_submission_id))
 if existing:return {**row_dict(existing),"idempotent":True}
 row=OfflineFieldSubmission(company_id=pr.company_id,branch_id=pr.branch_id,site_id=pr.primary_site_id,project_id=pr.id,device_id=payload.device_id,client_submission_id=payload.client_submission_id,submission_type=payload.submission_type,captured_at=payload.captured_at,payload=payload.payload,received_by=p.user.full_name);db.add(row);commit(db);return row_dict(row)
@router.get("/submissions")
def submissions(project_id:int|None=None,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->list[dict[str,Any]]:
 if not p.has_permission_anywhere("mobile.capture"):raise HTTPException(status_code=403,detail="Permission required: mobile.capture")
 rows=db.scalars(select(OfflineFieldSubmission).where(OfflineFieldSubmission.company_id==p.user.company_id).order_by(OfflineFieldSubmission.captured_at.desc())).all();return [row_dict(r) for r in rows if (project_id is None or r.project_id==project_id) and p.can("mobile.capture",branch_id=r.branch_id,site_id=r.site_id)]
@router.post("/submissions/{submission_id:int}/review")
def review(submission_id:int,payload:ReviewInput,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
 row=db.get(OfflineFieldSubmission,submission_id)
 if not row or row.company_id!=p.user.company_id:raise HTTPException(status_code=404,detail="Mobile submission not found")
 pr=project(db,p,row.project_id,"mobile.review")
 if row.status!="pending_review":raise HTTPException(status_code=409,detail="Mobile submission is not awaiting review")
 if row.received_by==p.user.full_name:raise HTTPException(status_code=422,detail="The synchronising user cannot complete the independent review")
 row.status,row.reviewer_note,row.reviewed_by,row.reviewed_at=payload.decision,payload.note,p.user.full_name,utcnow();commit(db);return row_dict(row)
@router.get("/dashboard")
def dashboard(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
 rows=submissions(db=db,p=p);return {"pending_review":sum(r["status"]=="pending_review" for r in rows),"accepted":sum(r["status"]=="accepted" for r in rows),"returned":sum(r["status"]=="returned" for r in rows),"by_type":{kind:sum(r["submission_type"]==kind for r in rows) for kind in TYPES},"boundary":"Accepted mobile evidence is retained for the responsible controller to post into the authoritative Site Operations workflow; it never auto-posts transactions."}
