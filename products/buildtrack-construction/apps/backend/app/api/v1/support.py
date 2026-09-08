from __future__ import annotations
from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.v1.procurement import allow_self_approval,commit,ensure_document,issue_reference,row_dict,utcnow
from app.db.session import get_db
from app.models import Branch,Document,NumberSequence,Permission,Role,RolePermission,Site,SupportAuditEvent,SupportTicket
from app.security.access import Principal,current_principal
router=APIRouter(prefix="/support",tags=["Phase 26 - Service Desk & Support Control"])
P={"support.view":("support","view","View support tickets"),"support.manage":("support","manage","Create and resolve support tickets"),"support.verify":("support","verify","Independently verify resolved support tickets")}
def any(p,c):
 if not p.has_permission_anywhere(c):raise HTTPException(status_code=403,detail=f"Permission required: {c}")
def scope(p,c,b,s):
 if not p.can(c,branch_id=b,site_id=s):raise HTTPException(status_code=403,detail=f"Permission required in this branch/site: {c}")
def audit(db,p,a,r):db.add(SupportAuditEvent(company_id=p.user.company_id,branch_id=r.branch_id,site_id=r.site_id,actor=p.user.full_name,action=a,entity_type=r.__tablename__,entity_id=str(r.id),detail={}))
def get(db,p,i,c):
 r=db.get(SupportTicket,i)
 if not r or r.company_id!=p.user.company_id:raise HTTPException(status_code=404,detail="Support ticket not found")
 scope(p,c,r.branch_id,r.site_id);return r
def boot(db,cid):
 q={}
 for c,(m,a,d) in P.items():
  r=db.scalar(select(Permission).where(Permission.code==c))
  if not r:r=Permission(code=c,module=m,action=a,description=d);db.add(r);db.flush()
  q[c]=r
 roles={r.code:r for r in db.scalars(select(Role).where(Role.company_id==cid)).all()}
 for c,n,l in (("SUPPORT_MANAGER","Support Manager","company"),("SUPPORT_OFFICER","Support Officer","branch"),("SUPPORT_REVIEWER","Support Reviewer","company")):
  if c not in roles:roles[c]=Role(company_id=cid,code=c,name=n,scope_level=l,description=f"Phase 26 {n}",is_system=True,is_active=True);db.add(roles[c]);db.flush()
 for rc,cs in {"SYSTEM_ADMIN":set(P),"HQ_EXECUTIVE":set(P),"BRANCH_MANAGER":set(P),"SUPPORT_MANAGER":set(P),"SUPPORT_OFFICER":{"support.view","support.manage"},"SUPPORT_REVIEWER":{"support.view","support.verify"}}.items():
  r=roles.get(rc)
  if r:
   old=set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id==r.id)).all())
   for c in cs:
    if q[c].id not in old:db.add(RolePermission(role_id=r.id,permission_id=q[c].id));old.add(q[c].id)
 if not db.scalar(select(NumberSequence).where(NumberSequence.company_id==cid,NumberSequence.code=="SUPPORT_TICKET")):db.add(NumberSequence(company_id=cid,code="SUPPORT_TICKET",name="Support Ticket",prefix="SUP",next_number=1,padding=5,reset_period="yearly"))
class In(BaseModel):model_config=ConfigDict(extra="forbid");branch_id:int;site_id:int|None=None;category:Literal["system","access","process","data","training","other"];priority:Literal["low","normal","high","critical"];title:str=Field(min_length=2,max_length=300);description:str=Field(min_length=2,max_length=4000);due_date:date|None=None;evidence_document_id:int|None=None
class Res(BaseModel):model_config=ConfigDict(extra="forbid");document_id:int=Field(gt=0);note:str=Field(min_length=2,max_length=4000)
@router.post("/bootstrap")
def bootstrap(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 if not p.has_company_permission("company.manage") and not p.has_company_permission("support.manage"):raise HTTPException(status_code=403,detail="Company administration is required")
 boot(db,p.user.company_id);commit(db);return {"phase":26,"status":"ready"}
@router.get("")
def rows(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 any(p,"support.view");return [row_dict(r) for r in db.scalars(select(SupportTicket).where(SupportTicket.company_id==p.user.company_id).order_by(SupportTicket.created_at.desc())).all() if p.can("support.view",branch_id=r.branch_id,site_id=r.site_id)]
@router.get("/catalog")
def catalog(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 any(p,"support.view");sites=[r for r in db.scalars(select(Site).where(Site.company_id==p.user.company_id)).all() if p.can("support.view",branch_id=r.branch_id,site_id=r.id)];site_branch_ids={r.branch_id for r in sites};branches=[r for r in db.scalars(select(Branch).where(Branch.company_id==p.user.company_id)).all() if p.can("support.view",branch_id=r.id,site_id=None) or r.id in site_branch_ids];documents=[r for r in db.scalars(select(Document).where(Document.company_id==p.user.company_id).order_by(Document.created_at.desc())).all() if p.can("support.view",branch_id=r.branch_id,site_id=r.site_id)];return {"branches":[row_dict(r) for r in branches],"sites":[row_dict(r) for r in sites],"documents":[row_dict(r) for r in documents]}
@router.post("",status_code=201)
def create(x:In,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 scope(p,"support.manage",x.branch_id,x.site_id);ensure_document(db,p.user.company_id,x.evidence_document_id);r=SupportTicket(company_id=p.user.company_id,branch_id=x.branch_id,site_id=x.site_id,ticket_number=issue_reference(db,p.user.company_id,"SUPPORT_TICKET","SUP"),category=x.category,priority=x.priority,title=x.title,description=x.description,due_date=x.due_date,evidence_document_id=x.evidence_document_id,created_by=p.user.full_name);db.add(r);db.flush();audit(db,p,"support.created",r);commit(db);return row_dict(r)
@router.post("/{i}/resolve")
def resolve(i:int,x:Res,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=get(db,p,i,"support.manage")
 if r.status not in {"open","in_progress"}:raise HTTPException(status_code=409,detail="Only open tickets can be resolved")
 ensure_document(db,r.company_id,x.document_id);r.status,r.resolution_document_id,r.resolution_note,r.resolved_by,r.resolved_at="resolved",x.document_id,x.note,p.user.full_name,utcnow();audit(db,p,"support.resolved",r);commit(db);return row_dict(r)
@router.post("/{i}/verify")
def verify(i:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=get(db,p,i,"support.verify")
 if r.status!="resolved":raise HTTPException(status_code=409,detail="Only resolved tickets can be verified")
 if r.resolved_by==p.user.full_name and not allow_self_approval(db,r.company_id):raise HTTPException(status_code=422,detail="Self-verification is disabled by company policy")
 r.status,r.verified_by,r.verified_at="closed",p.user.full_name,utcnow();audit(db,p,"support.verified",r);commit(db);return row_dict(r)
