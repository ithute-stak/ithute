from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.v1.procurement import commit,ensure_scope,issue_reference,row_dict,utcnow
from app.db.session import get_db
from app.models import Branch,BusinessDevelopmentAuditEvent,BusinessOpportunity,BusinessOpportunityActivity,NumberSequence,Permission,Role,RolePermission,Site,Tender
from app.security.access import Principal,current_principal
router=APIRouter(prefix="/business-development",tags=["Phase 32 - Business Development & Opportunity Pipeline"])
P={"businessdevelopment.view":("business_development","view","View business opportunities"),"businessdevelopment.manage":("business_development","manage","Manage business opportunities"),"businessdevelopment.qualify":("business_development","qualify","Independently qualify business opportunities")}
def any(p,c):
 if not p.has_permission_anywhere(c):raise HTTPException(status_code=403,detail=f"Permission required: {c}")
def scope(p,c,b,s):
 if not p.can(c,branch_id=b,site_id=s):raise HTTPException(status_code=403,detail=f"Permission required in this branch/site: {c}")
def audit(db,p,a,r,d=None):db.add(BusinessDevelopmentAuditEvent(company_id=r.company_id,branch_id=r.branch_id,site_id=r.site_id,actor=p.user.full_name,action=a,entity_type=r.__tablename__,entity_id=str(r.id),detail=d or {}))
def get(db,p,i,c):
 r=db.get(BusinessOpportunity,i)
 if not r or r.company_id!=p.user.company_id:raise HTTPException(status_code=404,detail="Business opportunity not found")
 scope(p,c,r.branch_id,r.site_id);return r
def boot(db,cid):
 ps={}
 for c,(m,a,d) in P.items():
  r=db.scalar(select(Permission).where(Permission.code==c))
  if not r:r=Permission(code=c,module=m,action=a,description=d);db.add(r);db.flush()
  ps[c]=r
 roles={r.code:r for r in db.scalars(select(Role).where(Role.company_id==cid)).all()}
 for c,n,l in (("BUSINESS_DEVELOPMENT_MANAGER","Business Development Manager","company"),("BUSINESS_DEVELOPMENT_OFFICER","Business Development Officer","branch"),("BUSINESS_DEVELOPMENT_REVIEWER","Business Development Reviewer","company")):
  if c not in roles:roles[c]=Role(company_id=cid,code=c,name=n,scope_level=l,description=f"Phase 32 {n}",is_system=True,is_active=True);db.add(roles[c]);db.flush()
 for rc,cs in {"SYSTEM_ADMIN":set(P),"HQ_EXECUTIVE":set(P),"BRANCH_MANAGER":set(P),"TENDER_MANAGER":{"businessdevelopment.view","businessdevelopment.manage"},"TENDER_COORDINATOR":{"businessdevelopment.view","businessdevelopment.manage"},"AUDITOR":{"businessdevelopment.view"},"BUSINESS_DEVELOPMENT_MANAGER":set(P),"BUSINESS_DEVELOPMENT_OFFICER":{"businessdevelopment.view","businessdevelopment.manage"},"BUSINESS_DEVELOPMENT_REVIEWER":{"businessdevelopment.view","businessdevelopment.qualify"}}.items():
  r=roles.get(rc)
  if r:
   old=set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id==r.id)).all())
   for c in cs:
    if ps[c].id not in old:db.add(RolePermission(role_id=r.id,permission_id=ps[c].id));old.add(ps[c].id)
 if not db.scalar(select(NumberSequence).where(NumberSequence.company_id==cid,NumberSequence.code=="BUSINESS_OPPORTUNITY")):db.add(NumberSequence(company_id=cid,code="BUSINESS_OPPORTUNITY",name="Business Opportunity",prefix="BDO",next_number=1,padding=5,reset_period="yearly"))
class In(BaseModel):
 model_config=ConfigDict(extra="forbid");branch_id:int;site_id:int|None=None;title:str=Field(min_length=2,max_length=300);client_name:str=Field(min_length=2,max_length=240);client_contact:str|None=None;sector:str|None=None;source:str=Field(min_length=2,max_length=80);estimated_value:Decimal|None=Field(default=None,ge=0);probability:int=Field(default=0,ge=0,le=100);expected_bid_date:date|None=None;scope_summary:str|None=None;next_action:str|None=None;next_action_date:date|None=None
class ActivityIn(BaseModel):model_config=ConfigDict(extra="forbid");activity_date:date;activity_type:Literal["call","meeting","site_visit","email","research","other"];note:str=Field(min_length=2,max_length=4000);next_action:str|None=None;next_action_date:date|None=None
class TenderIn(BaseModel):model_config=ConfigDict(extra="forbid");tender_id:int
class CloseIn(BaseModel):model_config=ConfigDict(extra="forbid");outcome:Literal["won","lost"];note:str=Field(min_length=2,max_length=4000)
@router.post("/bootstrap")
def bootstrap(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 if not p.has_company_permission("company.manage") and not p.has_company_permission("businessdevelopment.manage"):raise HTTPException(status_code=403,detail="Company administration is required")
 boot(db,p.user.company_id);commit(db);return {"phase":32,"status":"ready"}
@router.get("/catalog")
def catalog(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 any(p,"businessdevelopment.view");return {"branches":[row_dict(x) for x in db.scalars(select(Branch).where(Branch.company_id==p.user.company_id)).all() if p.can("businessdevelopment.view",branch_id=x.id,site_id=None)],"sites":[row_dict(x) for x in db.scalars(select(Site).where(Site.company_id==p.user.company_id)).all() if p.can("businessdevelopment.view",branch_id=x.branch_id,site_id=x.id)],"tenders":[row_dict(x) for x in db.scalars(select(Tender).where(Tender.company_id==p.user.company_id)).all() if p.can("businessdevelopment.view",branch_id=x.branch_id,site_id=x.site_id)]}
@router.get("")
def rows(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 any(p,"businessdevelopment.view");return [row_dict(x) for x in db.scalars(select(BusinessOpportunity).where(BusinessOpportunity.company_id==p.user.company_id).order_by(BusinessOpportunity.created_at.desc())).all() if p.can("businessdevelopment.view",branch_id=x.branch_id,site_id=x.site_id)]
@router.post("",status_code=201)
def create(x:In,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 ensure_scope(db,p.user.company_id,x.branch_id,x.site_id);scope(p,"businessdevelopment.manage",x.branch_id,x.site_id)
 r=BusinessOpportunity(company_id=p.user.company_id,branch_id=x.branch_id,site_id=x.site_id,opportunity_number=issue_reference(db,p.user.company_id,"BUSINESS_OPPORTUNITY","BDO"),**x.model_dump(),prepared_by=p.user.full_name);db.add(r);db.flush();audit(db,p,"businessdevelopment.opportunity.created",r);commit(db);return row_dict(r)
@router.post("/{i}/qualify")
def qualify(i:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=get(db,p,i,"businessdevelopment.qualify")
 if r.status!="lead" or not r.client_contact or not r.scope_summary or not r.expected_bid_date:raise HTTPException(status_code=422,detail="Qualification requires client contact, scope summary and expected bid date")
 if r.prepared_by==p.user.full_name:raise HTTPException(status_code=422,detail="Independent qualification is required")
 r.status,r.qualified_by,r.qualified_at="qualified",p.user.full_name,utcnow();audit(db,p,"businessdevelopment.opportunity.qualified",r);commit(db);return row_dict(r)
@router.post("/{i}/activities",status_code=201)
def activity(i:int,x:ActivityIn,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=get(db,p,i,"businessdevelopment.manage")
 if r.status in {"won","lost"}:raise HTTPException(status_code=409,detail="Closed opportunities cannot receive further activities")
 a=BusinessOpportunityActivity(company_id=r.company_id,opportunity_id=r.id,**x.model_dump(),recorded_by=p.user.full_name);db.add(a);r.next_action,r.next_action_date=x.next_action,x.next_action_date;audit(db,p,"businessdevelopment.activity.recorded",r,{"type":x.activity_type});commit(db);return row_dict(a)
@router.post("/{i}/link-tender")
def link_tender(i:int,x:TenderIn,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=get(db,p,i,"businessdevelopment.manage");t=db.get(Tender,x.tender_id)
 if r.status!="qualified" or not t or t.company_id!=r.company_id or t.branch_id!=r.branch_id:raise HTTPException(status_code=422,detail="A qualified opportunity must link to a tender in the same company branch")
 r.status,r.tender_id="tendering",t.id;audit(db,p,"businessdevelopment.opportunity.tender_linked",r,{"tender_id":t.id});commit(db);return row_dict(r)
@router.post("/{i}/close")
def close(i:int,x:CloseIn,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=get(db,p,i,"businessdevelopment.manage")
 if r.status not in {"qualified","tendering"}:raise HTTPException(status_code=409,detail="Only a qualified or tendering opportunity can be closed")
 r.status,r.close_note,r.closed_by,r.closed_at=x.outcome,x.note,p.user.full_name,utcnow();audit(db,p,"businessdevelopment.opportunity.closed",r,{"outcome":x.outcome});commit(db);return row_dict(r)
