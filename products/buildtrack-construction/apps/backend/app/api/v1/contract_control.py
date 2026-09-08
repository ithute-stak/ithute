from __future__ import annotations
from datetime import date
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.v1.procurement import commit,ensure_scope,issue_reference,row_dict,utcnow
from app.db.session import get_db
from app.models import Branch,ClientContract,ContractControlAuditEvent,ExtensionOfTime,ContractNotice,ContractVariationInstruction,NumberSequence,Permission,Role,RolePermission,Site
from app.security.access import Principal,current_principal
router=APIRouter(prefix="/contract-control",tags=["Phase 34 - Contract Administration & Variation Control"])
P={"contractcontrol.view":("contract_control","view","View contract controls"),"contractcontrol.manage":("contract_control","manage","Prepare contract notices and instructions"),"contractcontrol.approve":("contract_control","approve","Independently issue and approve contract controls")}
def scope(p,c,b,s):
 if not p.can(c,branch_id=b,site_id=s):raise HTTPException(status_code=403,detail=f"Permission required in this branch/site: {c}")
def get(db,p,m,i,c):
 r=db.get(m,i)
 if not r or r.company_id!=p.user.company_id:raise HTTPException(status_code=404,detail="Contract-control record not found")
 scope(p,c,r.branch_id,r.site_id);return r
def audit(db,p,a,r,d=None):db.add(ContractControlAuditEvent(company_id=r.company_id,branch_id=r.branch_id,site_id=r.site_id,actor=p.user.full_name,action=a,entity_type=r.__tablename__,entity_id=str(r.id),detail=d or {}))
def boot(db,cid):
 ps={}
 for c,(m,a,d) in P.items():
  x=db.scalar(select(Permission).where(Permission.code==c))
  if not x:x=Permission(code=c,module=m,action=a,description=d);db.add(x);db.flush()
  ps[c]=x
 roles={x.code:x for x in db.scalars(select(Role).where(Role.company_id==cid)).all()}
 for code,name,level in (("CONTRACT_ADMINISTRATOR","Contract Administrator","branch"),("CONTRACT_CONTROLLER","Contract Controller","company")):
  if code not in roles:roles[code]=Role(company_id=cid,code=code,name=name,scope_level=level,description=f"Phase 34 {name}",is_system=True,is_active=True);db.add(roles[code]);db.flush()
 for rc,cs in {"SYSTEM_ADMIN":set(P),"HQ_EXECUTIVE":set(P),"COMMERCIAL_MANAGER":set(P),"PROJECT_MANAGER":{"contractcontrol.view","contractcontrol.manage"},"AUDITOR":{"contractcontrol.view"},"CONTRACT_ADMINISTRATOR":{"contractcontrol.view","contractcontrol.manage"},"CONTRACT_CONTROLLER":set(P)}.items():
  r=roles.get(rc)
  if r:
   old=set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id==r.id)).all())
   for c in cs:
    if ps[c].id not in old:db.add(RolePermission(role_id=r.id,permission_id=ps[c].id));old.add(ps[c].id)
 for code,name,prefix in (("CONTRACT_NOTICE","Contract Notice","CNT"),("CONTRACT_INSTRUCTION","Contract Instruction","CVI")):
  if not db.scalar(select(NumberSequence).where(NumberSequence.company_id==cid,NumberSequence.code==code)):db.add(NumberSequence(company_id=cid,code=code,name=name,prefix=prefix,next_number=1,padding=5,reset_period="yearly"))
class NoticeIn(BaseModel):model_config=ConfigDict(extra="forbid");branch_id:int;site_id:int|None=None;contract_id:int;notice_type:str=Field(min_length=2,max_length=80);subject:str=Field(min_length=2,max_length=300);event_date:date;due_date:date|None=None;detail:str=Field(min_length=2,max_length=6000)
class EotIn(BaseModel):model_config=ConfigDict(extra="forbid");contract_id:int;notice_id:int|None=None;reason:str=Field(min_length=2,max_length=300);days_requested:int=Field(gt=0,le=3650);impact_summary:str=Field(min_length=2,max_length=6000)
class InstructionIn(BaseModel):model_config=ConfigDict(extra="forbid");branch_id:int;site_id:int|None=None;contract_id:int;description:str=Field(min_length=2,max_length=6000);estimated_value:float=Field(ge=0)
@router.post("/bootstrap")
def bootstrap(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 if not p.has_company_permission("company.manage") and not p.has_company_permission("contractcontrol.manage"):raise HTTPException(status_code=403,detail="Company administration is required")
 boot(db,p.user.company_id);commit(db);return {"phase":34,"status":"ready"}
@router.get("/catalog")
def catalog(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 if not p.has_permission_anywhere("contractcontrol.view"):raise HTTPException(status_code=403,detail="Permission required: contractcontrol.view")
 return {"branches":[row_dict(x) for x in db.scalars(select(Branch).where(Branch.company_id==p.user.company_id)).all() if p.can("contractcontrol.view",branch_id=x.id,site_id=None)],"sites":[row_dict(x) for x in db.scalars(select(Site).where(Site.company_id==p.user.company_id)).all() if p.can("contractcontrol.view",branch_id=x.branch_id,site_id=x.id)],"contracts":[row_dict(x) for x in db.scalars(select(ClientContract).where(ClientContract.company_id==p.user.company_id)).all() if p.can("contractcontrol.view",branch_id=x.branch_id,site_id=x.site_id)]}
@router.get("")
def rows(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 if not p.has_permission_anywhere("contractcontrol.view"):raise HTTPException(status_code=403,detail="Permission required: contractcontrol.view")
 q=lambda m:[row_dict(x) for x in db.scalars(select(m).where(m.company_id==p.user.company_id).order_by(m.created_at.desc())).all() if p.can("contractcontrol.view",branch_id=x.branch_id,site_id=x.site_id)]
 return {"notices":q(ContractNotice),"extensions":q(ExtensionOfTime),"instructions":q(ContractVariationInstruction)}
@router.post("/notices",status_code=201)
def notice(x:NoticeIn,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 ensure_scope(db,p.user.company_id,x.branch_id,x.site_id);scope(p,"contractcontrol.manage",x.branch_id,x.site_id);c=db.get(ClientContract,x.contract_id)
 if not c or c.company_id!=p.user.company_id:raise HTTPException(status_code=422,detail="A company contract is required")
 r=ContractNotice(company_id=p.user.company_id,notice_number=issue_reference(db,p.user.company_id,"CONTRACT_NOTICE","CNT"),prepared_by=p.user.full_name,**x.model_dump());db.add(r);db.flush();audit(db,p,"contract.notice.prepared",r);commit(db);return row_dict(r)
@router.post("/notices/{i}/issue")
def issue(i:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=get(db,p,ContractNotice,i,"contractcontrol.approve")
 if r.status!="draft":raise HTTPException(status_code=422,detail="Only a draft notice may be issued")
 if r.prepared_by==p.user.full_name:raise HTTPException(status_code=422,detail="Independent notice issue is required")
 r.status,r.issued_by,r.issued_at="issued",p.user.full_name,utcnow();audit(db,p,"contract.notice.issued",r);commit(db);return row_dict(r)
@router.post("/extensions",status_code=201)
def extension(x:EotIn,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 c=db.get(ClientContract,x.contract_id)
 if not c or c.company_id!=p.user.company_id:raise HTTPException(status_code=422,detail="A company contract is required")
 scope(p,"contractcontrol.manage",c.branch_id,c.site_id);r=ExtensionOfTime(company_id=c.company_id,branch_id=c.branch_id,site_id=c.site_id,submitted_by=p.user.full_name,**x.model_dump());db.add(r);db.flush();audit(db,p,"contract.extension.submitted",r,{"days":x.days_requested});commit(db);return row_dict(r)
@router.post("/extensions/{i}/review")
def review(i:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=get(db,p,ExtensionOfTime,i,"contractcontrol.approve")
 if r.submitted_by==p.user.full_name:raise HTTPException(status_code=422,detail="Independent extension review is required")
 if r.status!="submitted":raise HTTPException(status_code=422,detail="Only a submitted extension may be reviewed")
 r.status,r.reviewed_by,r.reviewed_at="reviewed",p.user.full_name,utcnow();audit(db,p,"contract.extension.reviewed",r);commit(db);return row_dict(r)
@router.post("/instructions",status_code=201)
def instruction(x:InstructionIn,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 ensure_scope(db,p.user.company_id,x.branch_id,x.site_id);scope(p,"contractcontrol.manage",x.branch_id,x.site_id);r=ContractVariationInstruction(company_id=p.user.company_id,instruction_number=issue_reference(db,p.user.company_id,"CONTRACT_INSTRUCTION","CVI"),prepared_by=p.user.full_name,**x.model_dump());db.add(r);db.flush();audit(db,p,"contract.instruction.prepared",r);commit(db);return row_dict(r)
@router.post("/instructions/{i}/approve")
def approve(i:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=get(db,p,ContractVariationInstruction,i,"contractcontrol.approve")
 if r.prepared_by==p.user.full_name:raise HTTPException(status_code=422,detail="Independent instruction approval is required")
 if r.status!="draft":raise HTTPException(status_code=422,detail="Only a draft instruction may be approved")
 r.status,r.approved_by,r.approved_at="approved",p.user.full_name,utcnow();audit(db,p,"contract.instruction.approved",r,{"estimated_value":str(r.estimated_value)});commit(db);return row_dict(r)
