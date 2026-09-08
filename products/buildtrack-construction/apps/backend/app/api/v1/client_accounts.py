from __future__ import annotations
from datetime import date
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.v1.procurement import commit,ensure_scope,issue_reference,row_dict,utcnow
from app.db.session import get_db
from app.models import Branch,ClientAccount,ClientAccountAuditEvent,ClientAccountContact,ClientFeedback,NumberSequence,Permission,Role,RolePermission,Site
from app.security.access import Principal,current_principal
router=APIRouter(prefix="/client-accounts",tags=["Phase 33 - Client Relationship & Account Management"])
P={"clientaccounts.view":("client_accounts","view","View client accounts and feedback"),"clientaccounts.manage":("client_accounts","manage","Manage client accounts and feedback"),"clientaccounts.verify":("client_accounts","verify","Independently verify client feedback remediation")}
def any(p,c):
 if not p.has_permission_anywhere(c):raise HTTPException(status_code=403,detail=f"Permission required: {c}")
def scope(p,c,b,s):
 if not p.can(c,branch_id=b,site_id=s):raise HTTPException(status_code=403,detail=f"Permission required in this branch/site: {c}")
def audit(db,p,a,r,d=None):db.add(ClientAccountAuditEvent(company_id=r.company_id,branch_id=r.branch_id,site_id=r.site_id,actor=p.user.full_name,action=a,entity_type=r.__tablename__,entity_id=str(r.id),detail=d or {}))
def get(db,p,i,c):
 r=db.get(ClientAccount,i)
 if not r or r.company_id!=p.user.company_id:raise HTTPException(status_code=404,detail="Client account not found")
 scope(p,c,r.branch_id,r.site_id);return r
def boot(db,cid):
 ps={}
 for c,(m,a,d) in P.items():
  r=db.scalar(select(Permission).where(Permission.code==c))
  if not r:r=Permission(code=c,module=m,action=a,description=d);db.add(r);db.flush()
  ps[c]=r
 roles={r.code:r for r in db.scalars(select(Role).where(Role.company_id==cid)).all()}
 for c,n,l in (("CLIENT_ACCOUNT_MANAGER","Client Account Manager","company"),("CLIENT_ACCOUNT_OFFICER","Client Account Officer","branch"),("CLIENT_ACCOUNT_REVIEWER","Client Account Reviewer","company")):
  if c not in roles:roles[c]=Role(company_id=cid,code=c,name=n,scope_level=l,description=f"Phase 33 {n}",is_system=True,is_active=True);db.add(roles[c]);db.flush()
 for rc,cs in {"SYSTEM_ADMIN":set(P),"HQ_EXECUTIVE":set(P),"BRANCH_MANAGER":set(P),"BUSINESS_DEVELOPMENT_MANAGER":{"clientaccounts.view","clientaccounts.manage"},"PROJECT_MANAGER":{"clientaccounts.view","clientaccounts.manage"},"AUDITOR":{"clientaccounts.view"},"CLIENT_ACCOUNT_MANAGER":set(P),"CLIENT_ACCOUNT_OFFICER":{"clientaccounts.view","clientaccounts.manage"},"CLIENT_ACCOUNT_REVIEWER":{"clientaccounts.view","clientaccounts.verify"}}.items():
  r=roles.get(rc)
  if r:
   old=set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id==r.id)).all())
   for c in cs:
    if ps[c].id not in old:db.add(RolePermission(role_id=r.id,permission_id=ps[c].id));old.add(ps[c].id)
 if not db.scalar(select(NumberSequence).where(NumberSequence.company_id==cid,NumberSequence.code=="CLIENT_ACCOUNT")):db.add(NumberSequence(company_id=cid,code="CLIENT_ACCOUNT",name="Client Account",prefix="CLA",next_number=1,padding=5,reset_period="yearly"))
class AccountIn(BaseModel):model_config=ConfigDict(extra="forbid");branch_id:int;site_id:int|None=None;legal_name:str=Field(min_length=2,max_length=240);trading_name:str|None=None;sector:str|None=None;account_manager:str|None=None;notes:str|None=None
class ContactIn(BaseModel):model_config=ConfigDict(extra="forbid");full_name:str=Field(min_length=2,max_length=240);role:str|None=None;email:str|None=None;phone:str|None=None;is_primary:bool=False
class FeedbackIn(BaseModel):model_config=ConfigDict(extra="forbid");feedback_date:date;category:str=Field(min_length=2,max_length=80);score:int=Field(ge=1,le=5);comment:str=Field(min_length=2,max_length=4000);action_plan:str|None=None
@router.post("/bootstrap")
def bootstrap(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 if not p.has_company_permission("company.manage") and not p.has_company_permission("clientaccounts.manage"):raise HTTPException(status_code=403,detail="Company administration is required")
 boot(db,p.user.company_id);commit(db);return {"phase":33,"status":"ready"}
@router.get("/catalog")
def catalog(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 any(p,"clientaccounts.view");return {"branches":[row_dict(x) for x in db.scalars(select(Branch).where(Branch.company_id==p.user.company_id)).all() if p.can("clientaccounts.view",branch_id=x.id,site_id=None)],"sites":[row_dict(x) for x in db.scalars(select(Site).where(Site.company_id==p.user.company_id)).all() if p.can("clientaccounts.view",branch_id=x.branch_id,site_id=x.id)]}
@router.get("")
def rows(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 any(p,"clientaccounts.view");return [row_dict(x) for x in db.scalars(select(ClientAccount).where(ClientAccount.company_id==p.user.company_id).order_by(ClientAccount.created_at.desc())).all() if p.can("clientaccounts.view",branch_id=x.branch_id,site_id=x.site_id)]
@router.post("",status_code=201)
def create(x:AccountIn,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 ensure_scope(db,p.user.company_id,x.branch_id,x.site_id);scope(p,"clientaccounts.manage",x.branch_id,x.site_id);r=ClientAccount(company_id=p.user.company_id,account_number=issue_reference(db,p.user.company_id,"CLIENT_ACCOUNT","CLA"),**x.model_dump(),created_by=p.user.full_name);db.add(r);db.flush();audit(db,p,"clientaccounts.account.created",r);commit(db);return row_dict(r)
@router.post("/{i}/contacts",status_code=201)
def contact(i:int,x:ContactIn,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=get(db,p,i,"clientaccounts.manage");c=ClientAccountContact(company_id=r.company_id,account_id=r.id,**x.model_dump());db.add(c);audit(db,p,"clientaccounts.contact.created",r);commit(db);return row_dict(c)
@router.post("/{i}/feedback",status_code=201)
def feedback(i:int,x:FeedbackIn,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=get(db,p,i,"clientaccounts.manage");f=ClientFeedback(company_id=r.company_id,account_id=r.id,**x.model_dump(),recorded_by=p.user.full_name);db.add(f);audit(db,p,"clientaccounts.feedback.recorded",r,{"score":x.score});commit(db);return row_dict(f)
@router.post("/{i}/feedback/{f}/verify")
def verify(i:int,f:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=get(db,p,i,"clientaccounts.verify");x=db.get(ClientFeedback,f)
 if not x or x.account_id!=r.id or x.status!="received" or not x.action_plan:raise HTTPException(status_code=422,detail="Received feedback with a remediation action plan is required")
 if x.recorded_by==p.user.full_name:raise HTTPException(status_code=422,detail="Independent feedback verification is required")
 x.status,x.verified_by,x.verified_at="verified",p.user.full_name,utcnow();audit(db,p,"clientaccounts.feedback.verified",r,{"feedback_id":x.id});commit(db);return row_dict(x)
