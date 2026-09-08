from __future__ import annotations
from datetime import date,timedelta
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.v1.procurement import allow_self_approval,commit,ensure_document,issue_reference,row_dict,utcnow
from app.db.session import get_db
from app.models import Branch,Document,Employee,NumberSequence,Permission,Project,Role,RolePermission,Site,ToolAsset,ToolAuditEvent,ToolCalibration,ToolIssue
from app.security.access import Principal,current_principal
router=APIRouter(prefix="/tools",tags=["Phase 29 - Tools & Calibration Control"])
P={"tools.view":("tools","view","View controlled tools"),"tools.manage":("tools","manage","Register, issue and return tools"),"tools.calibrate":("tools","calibrate","Record tool calibration evidence"),"tools.verify":("tools","verify","Independently verify calibration evidence")}
def any(p,c):
 if not p.has_permission_anywhere(c):raise HTTPException(status_code=403,detail=f"Permission required: {c}")
def scope(p,c,b,s):
 if not p.can(c,branch_id=b,site_id=s):raise HTTPException(status_code=403,detail=f"Permission required in this branch/site: {c}")
def audit(db,p,a,r):db.add(ToolAuditEvent(company_id=p.user.company_id,branch_id=r.branch_id,site_id=r.site_id,actor=p.user.full_name,action=a,entity_type=r.__tablename__,entity_id=str(r.id),detail={}))
def tool(db,p,i,c):
 r=db.get(ToolAsset,i)
 if not r or r.company_id!=p.user.company_id:raise HTTPException(status_code=404,detail="Tool not found")
 scope(p,c,r.branch_id,r.site_id);return r
def boot(db,cid):
 ps={}
 for c,(m,a,d) in P.items():
  r=db.scalar(select(Permission).where(Permission.code==c))
  if not r:r=Permission(code=c,module=m,action=a,description=d);db.add(r);db.flush()
  ps[c]=r
 roles={r.code:r for r in db.scalars(select(Role).where(Role.company_id==cid)).all()}
 for c,n,l in (("TOOL_MANAGER","Tool Manager","company"),("TOOL_CUSTODIAN","Tool Custodian","branch"),("CALIBRATION_REVIEWER","Calibration Reviewer","company")):
  if c not in roles:roles[c]=Role(company_id=cid,code=c,name=n,scope_level=l,description=f"Phase 29 {n}",is_system=True,is_active=True);db.add(roles[c]);db.flush()
 for rc,cs in {"SYSTEM_ADMIN":set(P),"HQ_EXECUTIVE":set(P),"BRANCH_MANAGER":set(P),"SITE_MANAGER":{"tools.view","tools.manage"},"PROJECT_MANAGER":{"tools.view","tools.manage"},"AUDITOR":{"tools.view"},"TOOL_MANAGER":set(P),"TOOL_CUSTODIAN":{"tools.view","tools.manage","tools.calibrate"},"CALIBRATION_REVIEWER":{"tools.view","tools.verify"}}.items():
  r=roles.get(rc)
  if r:
   old=set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id==r.id)).all())
   for c in cs:
    if ps[c].id not in old:db.add(RolePermission(role_id=r.id,permission_id=ps[c].id));old.add(ps[c].id)
 for c,n,prefix in (("TOOL_ASSET","Tool Asset","TLS"),):
  if not db.scalar(select(NumberSequence).where(NumberSequence.company_id==cid,NumberSequence.code==c)):db.add(NumberSequence(company_id=cid,code=c,name=n,prefix=prefix,next_number=1,padding=5,reset_period="yearly"))
class ToolIn(BaseModel):model_config=ConfigDict(extra="forbid");branch_id:int;site_id:int|None=None;name:str=Field(min_length=2,max_length=240);tool_type:Literal["hand_tool","power_tool","measurement","safety","other"];manufacturer:str|None=None;serial_number:str|None=None;calibration_required:bool=False;calibration_due_date:date|None=None;document_id:int|None=None
class IssueIn(BaseModel):model_config=ConfigDict(extra="forbid");employee_id:int|None=None;project_id:int|None=None;due_date:date|None=None;condition_out:Literal["good","fair","new"]
class ReturnIn(BaseModel):model_config=ConfigDict(extra="forbid");condition_in:Literal["good","fair","damaged","missing"];note:str|None=None
class CalIn(BaseModel):model_config=ConfigDict(extra="forbid");calibration_date:date;due_date:date;provider:str=Field(min_length=2,max_length=200);certificate_document_id:int=Field(gt=0)
@router.post("/bootstrap")
def bootstrap(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 if not p.has_company_permission("company.manage") and not p.has_company_permission("tools.manage"):raise HTTPException(status_code=403,detail="Company administration is required")
 boot(db,p.user.company_id);commit(db);return {"phase":29,"status":"ready"}
@router.get("/catalog")
def catalog(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 any(p,"tools.view");return {"branches":[row_dict(r) for r in db.scalars(select(Branch).where(Branch.company_id==p.user.company_id)).all() if p.can("tools.view",branch_id=r.id,site_id=None)],"sites":[row_dict(r) for r in db.scalars(select(Site).where(Site.company_id==p.user.company_id)).all() if p.can("tools.view",branch_id=r.branch_id,site_id=r.id)],"employees":[row_dict(r) for r in db.scalars(select(Employee).where(Employee.company_id==p.user.company_id,Employee.status=="active")).all()],"projects":[row_dict(r) for r in db.scalars(select(Project).where(Project.company_id==p.user.company_id,Project.status.in_(("ready","active")))).all() if p.can("tools.view",branch_id=r.branch_id,site_id=r.primary_site_id)],"documents":[row_dict(r) for r in db.scalars(select(Document).where(Document.company_id==p.user.company_id).order_by(Document.created_at.desc())).all() if p.can("tools.view",branch_id=r.branch_id,site_id=r.site_id)]}
@router.get("")
def rows(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 any(p,"tools.view");return [row_dict(r) for r in db.scalars(select(ToolAsset).where(ToolAsset.company_id==p.user.company_id).order_by(ToolAsset.created_at.desc())).all() if p.can("tools.view",branch_id=r.branch_id,site_id=r.site_id)]
@router.get("/issues")
def issues(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 any(p,"tools.view");return [row_dict(r) for r in db.scalars(select(ToolIssue).where(ToolIssue.company_id==p.user.company_id).order_by(ToolIssue.issued_at.desc())).all() if p.can("tools.view",branch_id=r.branch_id,site_id=r.site_id)]
@router.get("/calibrations")
def calibrations(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 any(p,"tools.view");return [row_dict(r) for r in db.scalars(select(ToolCalibration).where(ToolCalibration.company_id==p.user.company_id).order_by(ToolCalibration.due_date)).all() if p.can("tools.view",branch_id=r.branch_id,site_id=r.site_id)]
@router.get("/dashboard")
def dashboard(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 any(p,"tools.view");rs=[r for r in db.scalars(select(ToolAsset).where(ToolAsset.company_id==p.user.company_id)).all() if p.can("tools.view",branch_id=r.branch_id,site_id=r.site_id)];cs=[r for r in db.scalars(select(ToolCalibration).where(ToolCalibration.company_id==p.user.company_id)).all() if p.can("tools.view",branch_id=r.branch_id,site_id=r.site_id)];return {"tools":len(rs),"issued":sum(r.status=="issued" for r in rs),"maintenance":sum(r.status=="maintenance" for r in rs),"calibration_due":sum(r.calibration_required and r.calibration_due_date and r.calibration_due_date<=date.today()+timedelta(days=30) for r in rs),"calibrations_pending":sum(r.status=="recorded" for r in cs)}
@router.post("",status_code=201)
def create(x:ToolIn,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 scope(p,"tools.manage",x.branch_id,x.site_id);ensure_document(db,p.user.company_id,x.document_id);r=ToolAsset(company_id=p.user.company_id,branch_id=x.branch_id,site_id=x.site_id,tool_number=issue_reference(db,p.user.company_id,"TOOL_ASSET","TLS"),name=x.name.strip(),tool_type=x.tool_type,manufacturer=x.manufacturer,serial_number=x.serial_number,calibration_required=x.calibration_required,calibration_due_date=x.calibration_due_date,document_id=x.document_id,created_by=p.user.full_name);db.add(r);db.flush();audit(db,p,"tools.asset.created",r);commit(db);return row_dict(r)
@router.post("/{i}/issue")
def issue(i:int,x:IssueIn,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=tool(db,p,i,"tools.manage")
 if r.status!="available":raise HTTPException(status_code=409,detail="Only available tools can be issued")
 if r.calibration_required and (not r.calibration_due_date or r.calibration_due_date<date.today()):raise HTTPException(status_code=409,detail="Tool calibration is overdue or missing")
 if x.employee_id:
  e=db.get(Employee,x.employee_id)
  if not e or e.company_id!=r.company_id or e.status!="active":raise HTTPException(status_code=422,detail="Tool recipient is invalid")
 if x.project_id:
  pr=db.get(Project,x.project_id)
  if not pr or pr.company_id!=r.company_id or pr.branch_id!=r.branch_id:raise HTTPException(status_code=422,detail="Tool project scope is invalid")
 db.add(ToolIssue(company_id=r.company_id,tool_id=r.id,employee_id=x.employee_id,project_id=x.project_id,branch_id=r.branch_id,site_id=r.site_id,due_date=x.due_date,condition_out=x.condition_out,issued_by=p.user.full_name));r.status="issued";audit(db,p,"tools.asset.issued",r);commit(db);return row_dict(r)
@router.post("/issues/{i}/return")
def return_tool(i:int,x:ReturnIn,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=db.get(ToolIssue,i)
 if not r or r.company_id!=p.user.company_id:raise HTTPException(status_code=404,detail="Tool issue not found")
 scope(p,"tools.manage",r.branch_id,r.site_id)
 if r.returned_at:raise HTTPException(status_code=409,detail="Tool has already been returned")
 a=tool(db,p,r.tool_id,"tools.manage");r.returned_at,r.returned_by,r.condition_in,r.return_note=utcnow(),p.user.full_name,x.condition_in,x.note;a.status="maintenance" if x.condition_in in {"damaged","missing"} else "available";audit(db,p,"tools.asset.returned",a);commit(db);return row_dict(r)
@router.post("/{i}/calibrations",status_code=201)
def calibrate(i:int,x:CalIn,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=tool(db,p,i,"tools.calibrate")
 if not r.calibration_required or x.due_date<x.calibration_date:raise HTTPException(status_code=422,detail="Tool calibration dates or requirement are invalid")
 ensure_document(db,r.company_id,x.certificate_document_id);c=ToolCalibration(company_id=r.company_id,tool_id=r.id,branch_id=r.branch_id,site_id=r.site_id,calibration_date=x.calibration_date,due_date=x.due_date,provider=x.provider.strip(),certificate_document_id=x.certificate_document_id,recorded_by=p.user.full_name);db.add(c);db.flush();audit(db,p,"tools.calibration.recorded",r);commit(db);return row_dict(c)
@router.post("/calibrations/{i}/verify")
def verify(i:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 c=db.get(ToolCalibration,i)
 if not c or c.company_id!=p.user.company_id:raise HTTPException(status_code=404,detail="Calibration not found")
 scope(p,"tools.verify",c.branch_id,c.site_id)
 if c.status!="recorded":raise HTTPException(status_code=409,detail="Calibration is not awaiting verification")
 if c.recorded_by==p.user.full_name and not allow_self_approval(db,c.company_id):raise HTTPException(status_code=422,detail="Self-verification is disabled by company policy")
 a=tool(db,p,c.tool_id,"tools.verify");c.status,c.verified_by,c.verified_at="verified",p.user.full_name,utcnow();a.calibration_due_date=c.due_date;a.status="available" if a.status=="maintenance" else a.status;audit(db,p,"tools.calibration.verified",a);commit(db);return row_dict(c)
