from __future__ import annotations
from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.v1.procurement import allow_self_approval,commit,ensure_document,issue_reference,row_dict,utcnow
from app.db.session import get_db
from app.models import Branch,ChangeAuditEvent,ChangeRequest,NumberSequence,Permission,Role,RolePermission,Site
from app.security.access import Principal,current_principal
router=APIRouter(prefix="/changes",tags=["Phase 25 - System Change & Release Control"])
P={"changes.view":("changes","view","View controlled changes"),"changes.manage":("changes","manage","Prepare changes and pilot evidence"),"changes.approve":("changes","approve","Independently approve changes"),"changes.release":("changes","release","Record approved release evidence")}
def any(p,c):
 if not p.has_permission_anywhere(c):raise HTTPException(status_code=403,detail=f"Permission required: {c}")
def scope(p,c,b,s):
 if not p.can(c,branch_id=b,site_id=s):raise HTTPException(status_code=403,detail=f"Permission required in this branch/site: {c}")
def audit(db,p,a,r):db.add(ChangeAuditEvent(company_id=p.user.company_id,branch_id=r.branch_id,site_id=r.site_id,actor=p.user.full_name,action=a,entity_type=r.__tablename__,entity_id=str(r.id),detail={}))
def get(db,p,i,c):
 r=db.get(ChangeRequest,i)
 if not r or r.company_id!=p.user.company_id:raise HTTPException(status_code=404,detail="Change request not found")
 scope(p,c,r.branch_id,r.site_id);return r
def boot(db,cid):
 perms={}
 for code,(m,a,d) in P.items():
  r=db.scalar(select(Permission).where(Permission.code==code))
  if not r:r=Permission(code=code,module=m,action=a,description=d);db.add(r);db.flush()
  perms[code]=r
 roles={r.code:r for r in db.scalars(select(Role).where(Role.company_id==cid)).all()}
 for code,name,lvl in (("CHANGE_MANAGER","Change Manager","company"),("CHANGE_COORDINATOR","Change Coordinator","branch"),("CHANGE_REVIEWER","Change Reviewer","company")):
  if code not in roles:roles[code]=Role(company_id=cid,code=code,name=name,scope_level=lvl,description=f"Phase 25 {name}",is_system=True,is_active=True);db.add(roles[code]);db.flush()
 for rc,cs in {"SYSTEM_ADMIN":set(P),"HQ_EXECUTIVE":set(P),"BRANCH_MANAGER":set(P),"APPROVER":{"changes.approve"},"CHANGE_MANAGER":set(P),"CHANGE_COORDINATOR":{"changes.view","changes.manage"},"CHANGE_REVIEWER":{"changes.view","changes.approve","changes.release"}}.items():
  r=roles.get(rc)
  if r:
   old=set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id==r.id)).all())
   for c in cs:
    if perms[c].id not in old:db.add(RolePermission(role_id=r.id,permission_id=perms[c].id));old.add(perms[c].id)
 if not db.scalar(select(NumberSequence).where(NumberSequence.company_id==cid,NumberSequence.code=="CHANGE_REQUEST")):db.add(NumberSequence(company_id=cid,code="CHANGE_REQUEST",name="Change Request",prefix="CRQ",next_number=1,padding=5,reset_period="yearly"))
class In(BaseModel):
 model_config=ConfigDict(extra="forbid");branch_id:int;site_id:int|None=None;title:str=Field(min_length=2,max_length=300);change_type:Literal["system","process","configuration","data","other"];risk_level:Literal["low","medium","high","critical"];description:str=Field(min_length=2,max_length=4000);impact_assessment:str|None=None;pilot_plan:str|None=None;planned_release_date:date|None=None;evidence_document_id:int|None=None
class Doc(BaseModel):model_config=ConfigDict(extra="forbid");document_id:int=Field(gt=0)
@router.post("/bootstrap")
def bootstrap(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 if not p.has_company_permission("company.manage") and not p.has_company_permission("changes.manage"):raise HTTPException(status_code=403,detail="Company administration is required")
 boot(db,p.user.company_id);commit(db);return {"phase":25,"status":"ready"}
@router.get("/catalog")
def catalog(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 any(p,"changes.view");return {"branches":[row_dict(r) for r in db.scalars(select(Branch).where(Branch.company_id==p.user.company_id)).all()],"sites":[row_dict(r) for r in db.scalars(select(Site).where(Site.company_id==p.user.company_id)).all()]}
@router.get("")
def rows(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 any(p,"changes.view");return [row_dict(r) for r in db.scalars(select(ChangeRequest).where(ChangeRequest.company_id==p.user.company_id).order_by(ChangeRequest.created_at.desc())).all() if p.can("changes.view",branch_id=r.branch_id,site_id=r.site_id)]
@router.post("",status_code=201)
def create(x:In,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 scope(p,"changes.manage",x.branch_id,x.site_id);b=db.get(Branch,x.branch_id);s=db.get(Site,x.site_id) if x.site_id else None
 if not b or b.company_id!=p.user.company_id or s and(s.company_id!=p.user.company_id or s.branch_id!=b.id):raise HTTPException(status_code=422,detail="Change branch/site scope is invalid")
 ensure_document(db,p.user.company_id,x.evidence_document_id);r=ChangeRequest(company_id=p.user.company_id,branch_id=x.branch_id,site_id=x.site_id,change_number=issue_reference(db,p.user.company_id,"CHANGE_REQUEST","CRQ"),title=x.title,change_type=x.change_type,risk_level=x.risk_level,description=x.description,impact_assessment=x.impact_assessment,pilot_plan=x.pilot_plan,planned_release_date=x.planned_release_date,evidence_document_id=x.evidence_document_id,prepared_by=p.user.full_name);db.add(r);db.flush();audit(db,p,"change.created",r);commit(db);return row_dict(r)
@router.post("/{i}/submit")
def submit(i:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=get(db,p,i,"changes.manage")
 if r.status not in {"draft","rejected"} or not r.evidence_document_id or not r.impact_assessment or not r.pilot_plan:raise HTTPException(status_code=409,detail="Evidence, impact assessment and a limited pilot plan are required")
 r.status,r.submitted_at="submitted",utcnow();audit(db,p,"change.submitted",r);commit(db);return row_dict(r)
@router.post("/{i}/approve")
def approve(i:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=get(db,p,i,"changes.approve")
 if r.status!="submitted":raise HTTPException(status_code=409,detail="Change is not awaiting approval")
 if r.prepared_by==p.user.full_name and not allow_self_approval(db,r.company_id):raise HTTPException(status_code=422,detail="Self-approval is disabled by company policy")
 r.status,r.approved_at,r.approved_by="approved",utcnow(),p.user.full_name;audit(db,p,"change.approved",r);commit(db);return row_dict(r)
@router.post("/{i}/release")
def release(i:int,x:Doc,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=get(db,p,i,"changes.release")
 if r.status!="approved":raise HTTPException(status_code=409,detail="Only approved pilot changes can be released")
 ensure_document(db,r.company_id,x.document_id);r.status,r.uat_document_id,r.release_document_id,r.released_at="released",x.document_id,x.document_id,utcnow();audit(db,p,"change.released",r);commit(db);return row_dict(r)
