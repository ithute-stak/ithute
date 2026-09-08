from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Any
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.v1.procurement import allow_self_approval,commit,ensure_document,issue_reference,row_dict,utcnow
from app.db.session import get_db
from app.models import AuthorityAuditEvent,AuthorityLimit,Branch,NumberSequence,Permission,Role,RolePermission,Site
from app.security.access import Principal,current_principal
router=APIRouter(prefix="/authority",tags=["Phase 24 - Delegated Authority & Approval Limits"])
P={"authority.view":("authority","view","View delegated authority limits"),"authority.manage":("authority","manage","Prepare delegated authority limits"),"authority.approve":("authority","approve","Independently approve authority limits"),"authority.evaluate":("authority","evaluate","Evaluate an approval amount against limits")}
def any(p:Principal,c:str):
 if not p.has_permission_anywhere(c):raise HTTPException(status_code=403,detail=f"Permission required: {c}")
def scope(p:Principal,c:str,b:int,s:int|None):
 if not p.can(c,branch_id=b,site_id=s):raise HTTPException(status_code=403,detail=f"Permission required in this branch/site: {c}")
def audit(db:Session,p:Principal,a:str,e:Any):db.add(AuthorityAuditEvent(company_id=p.user.company_id,branch_id=e.branch_id,site_id=e.site_id,actor=p.user.full_name,action=a,entity_type=e.__tablename__,entity_id=str(e.id),detail={}))
def owned(db:Session,p:Principal,i:int,c:str)->AuthorityLimit:
 r=db.get(AuthorityLimit,i)
 if not r or r.company_id!=p.user.company_id:raise HTTPException(status_code=404,detail="Authority limit not found")
 scope(p,c,r.branch_id,r.site_id);return r
def boot(db:Session,cid:int):
 perms={}
 for code,(m,a,d) in P.items():
  r=db.scalar(select(Permission).where(Permission.code==code))
  if not r:r=Permission(code=code,module=m,action=a,description=d);db.add(r);db.flush()
  perms[code]=r
 roles={r.code:r for r in db.scalars(select(Role).where(Role.company_id==cid)).all()}
 for code,name,lvl in (("AUTHORITY_MANAGER","Authority Manager","company"),("AUTHORITY_OFFICER","Authority Officer","branch"),("AUTHORITY_REVIEWER","Authority Reviewer","company")):
  if code not in roles:roles[code]=Role(company_id=cid,code=code,name=name,scope_level=lvl,description=f"Phase 24 {name}",is_system=True,is_active=True);db.add(roles[code]);db.flush()
 for rc,codes in {"SYSTEM_ADMIN":set(P),"HQ_EXECUTIVE":set(P),"BRANCH_MANAGER":set(P),"APPROVER":{"authority.approve"},"AUDITOR":{"authority.view","authority.evaluate"},"AUTHORITY_MANAGER":set(P),"AUTHORITY_OFFICER":{"authority.view","authority.manage","authority.evaluate"},"AUTHORITY_REVIEWER":{"authority.view","authority.approve","authority.evaluate"}}.items():
  role=roles.get(rc)
  if role:
   old=set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id==role.id)).all())
   for c in codes:
    if perms[c].id not in old:db.add(RolePermission(role_id=role.id,permission_id=perms[c].id));old.add(perms[c].id)
 if not db.scalar(select(NumberSequence).where(NumberSequence.company_id==cid,NumberSequence.code=="AUTHORITY_LIMIT")):db.add(NumberSequence(company_id=cid,code="AUTHORITY_LIMIT",name="Authority Limit",prefix="DAL",next_number=1,padding=5,reset_period="yearly"))
class LimitIn(BaseModel):
 model_config=ConfigDict(extra="forbid");role_id:int;branch_id:int;site_id:int|None=None;module:str=Field(min_length=2,max_length=80);transaction_type:str=Field(min_length=2,max_length=80);minimum_amount:Decimal=Field(default=Decimal("0"),ge=0);maximum_amount:Decimal=Field(gt=0);effective_from:date;effective_to:date|None=None;document_id:int|None=None;notes:str|None=None
class EvalIn(BaseModel):
 model_config=ConfigDict(extra="forbid");role_id:int;branch_id:int;site_id:int|None=None;module:str;transaction_type:str;amount:Decimal=Field(ge=0);on_date:date|None=None
@router.post("/bootstrap")
def bootstrap(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict:
 if not p.has_company_permission("company.manage") and not p.has_company_permission("authority.manage"):raise HTTPException(status_code=403,detail="Company administration is required")
 boot(db,p.user.company_id);commit(db);return {"phase":24,"status":"ready"}
@router.get("/catalog")
def catalog(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict:
 any(p,"authority.view");return {"roles":[row_dict(r) for r in db.scalars(select(Role).where(Role.company_id==p.user.company_id,Role.is_active.is_(True))).all()],"branches":[row_dict(r) for r in db.scalars(select(Branch).where(Branch.company_id==p.user.company_id)).all()],"sites":[row_dict(r) for r in db.scalars(select(Site).where(Site.company_id==p.user.company_id)).all()]}
@router.get("/limits")
def limits(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->list[dict]:
 any(p,"authority.view");return [row_dict(r) for r in db.scalars(select(AuthorityLimit).where(AuthorityLimit.company_id==p.user.company_id).order_by(AuthorityLimit.created_at.desc())).all() if p.can("authority.view",branch_id=r.branch_id,site_id=r.site_id)]
@router.post("/limits",status_code=201)
def create(x:LimitIn,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict:
 scope(p,"authority.manage",x.branch_id,x.site_id)
 if x.maximum_amount<x.minimum_amount or x.effective_to and x.effective_to<x.effective_from:raise HTTPException(status_code=422,detail="Authority range or effective dates are invalid")
 role=db.get(Role,x.role_id);branch=db.get(Branch,x.branch_id);site=db.get(Site,x.site_id) if x.site_id else None
 if not role or role.company_id!=p.user.company_id or not branch or branch.company_id!=p.user.company_id or site and (site.company_id!=p.user.company_id or site.branch_id!=branch.id):raise HTTPException(status_code=422,detail="Authority role/branch/site scope is invalid")
 ensure_document(db,p.user.company_id,x.document_id);r=AuthorityLimit(company_id=p.user.company_id,role_id=x.role_id,branch_id=x.branch_id,site_id=x.site_id,limit_number=issue_reference(db,p.user.company_id,"AUTHORITY_LIMIT","DAL"),module=x.module.strip(),transaction_type=x.transaction_type.strip(),minimum_amount=x.minimum_amount,maximum_amount=x.maximum_amount,effective_from=x.effective_from,effective_to=x.effective_to,document_id=x.document_id,notes=x.notes,prepared_by=p.user.full_name);db.add(r);db.flush();audit(db,p,"authority.limit.created",r);commit(db);return row_dict(r)
@router.post("/limits/{limit_id:int}/submit")
def submit(limit_id:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict:
 r=owned(db,p,limit_id,"authority.manage")
 if r.status not in {"draft","rejected"} or not r.document_id:raise HTTPException(status_code=409,detail="A draft authority limit needs controlled evidence before submission")
 r.status,r.submitted_at="submitted",utcnow();audit(db,p,"authority.limit.submitted",r);commit(db);return row_dict(r)
@router.post("/limits/{limit_id:int}/approve")
def approve(limit_id:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict:
 r=owned(db,p,limit_id,"authority.approve")
 if r.status!="submitted":raise HTTPException(status_code=409,detail="Authority limit is not awaiting approval")
 if r.prepared_by==p.user.full_name and not allow_self_approval(db,r.company_id):raise HTTPException(status_code=422,detail="Self-approval is disabled by company policy")
 r.status,r.approved_at,r.approved_by="approved",utcnow(),p.user.full_name;audit(db,p,"authority.limit.approved",r);commit(db);return row_dict(r)
@router.post("/evaluate")
def evaluate(x:EvalIn,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict:
 any(p,"authority.evaluate");scope(p,"authority.evaluate",x.branch_id,x.site_id);d=x.on_date or date.today();rows=db.scalars(select(AuthorityLimit).where(AuthorityLimit.company_id==p.user.company_id,AuthorityLimit.role_id==x.role_id,AuthorityLimit.branch_id==x.branch_id,AuthorityLimit.module==x.module,AuthorityLimit.transaction_type==x.transaction_type,AuthorityLimit.status=="approved",AuthorityLimit.effective_from<=d)).all();rows=[r for r in rows if (r.site_id is None or r.site_id==x.site_id) and (r.effective_to is None or r.effective_to>=d)];matches=[r for r in rows if r.minimum_amount<=x.amount<=r.maximum_amount];return {"authorised":bool(matches),"amount":str(x.amount),"matching_limits":[row_dict(r) for r in matches]}
