from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Literal,Any
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from app.api.v1.procurement import allow_self_approval,commit,ensure_document,issue_reference,row_dict,utcnow
from app.db.session import get_db
from app.models import Document,EnvironmentalAuditEvent,EnvironmentalInspection,EnvironmentalPlan,EnvironmentalWasteRecord,NumberSequence,Permission,Project,Role,RolePermission
from app.security.access import Principal,current_principal
router=APIRouter(prefix="/environment",tags=["Phase 28 - Environmental & Sustainability Control"])
P={"environment.view":("environment","view","View environmental controls"),"environment.manage":("environment","manage","Prepare plans, waste and inspection evidence"),"environment.approve":("environment","approve","Independently approve environmental plans and verify evidence"),"environment.export":("environment","export","Export environmental registers")}
def any(p,c):
 if not p.has_permission_anywhere(c):raise HTTPException(status_code=403,detail=f"Permission required: {c}")
def scope(p,c,b,s):
 if not p.can(c,branch_id=b,site_id=s):raise HTTPException(status_code=403,detail=f"Permission required in this branch/site: {c}")
def project(db,p,i,c):
 r=db.get(Project,i)
 if not r or r.company_id!=p.user.company_id:raise HTTPException(status_code=404,detail="Project not found")
 scope(p,c,r.branch_id,r.primary_site_id);return r
def owned(db,p,m,i,c,label):
 r=db.get(m,i)
 if not r or r.company_id!=p.user.company_id:raise HTTPException(status_code=404,detail=f"{label} not found")
 scope(p,c,r.branch_id,r.site_id);return r
def audit(db,p,a,r):db.add(EnvironmentalAuditEvent(company_id=p.user.company_id,branch_id=r.branch_id,site_id=r.site_id,project_id=r.project_id,actor=p.user.full_name,action=a,entity_type=r.__tablename__,entity_id=str(r.id),detail={}))
def boot(db,cid):
 perms={}
 for c,(m,a,d) in P.items():
  r=db.scalar(select(Permission).where(Permission.code==c))
  if not r:r=Permission(code=c,module=m,action=a,description=d);db.add(r);db.flush()
  perms[c]=r
 roles={r.code:r for r in db.scalars(select(Role).where(Role.company_id==cid)).all()}
 for c,n,l in (("ENVIRONMENT_MANAGER","Environment Manager","company"),("ENVIRONMENT_OFFICER","Environment Officer","branch"),("ENVIRONMENT_REVIEWER","Environment Reviewer","company")):
  if c not in roles:roles[c]=Role(company_id=cid,code=c,name=n,scope_level=l,description=f"Phase 28 {n}",is_system=True,is_active=True);db.add(roles[c]);db.flush()
 for rc,cs in {"SYSTEM_ADMIN":set(P),"HQ_EXECUTIVE":set(P),"BRANCH_MANAGER":set(P),"PROJECT_MANAGER":{"environment.view","environment.manage","environment.export"},"SITE_MANAGER":{"environment.view","environment.manage"},"AUDITOR":{"environment.view","environment.export"},"ENVIRONMENT_MANAGER":set(P),"ENVIRONMENT_OFFICER":{"environment.view","environment.manage"},"ENVIRONMENT_REVIEWER":{"environment.view","environment.approve","environment.export"}}.items():
  r=roles.get(rc)
  if r:
   old=set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id==r.id)).all())
   for c in cs:
    if perms[c].id not in old:db.add(RolePermission(role_id=r.id,permission_id=perms[c].id));old.add(perms[c].id)
 for c,n,prefix in (("ENVIRONMENT_PLAN","Environmental Plan","ENV"),("ENVIRONMENT_WASTE","Waste Record","WST"),("ENVIRONMENT_INSPECTION","Environmental Inspection","EIN")):
  if not db.scalar(select(NumberSequence).where(NumberSequence.company_id==cid,NumberSequence.code==c)):db.add(NumberSequence(company_id=cid,code=c,name=n,prefix=prefix,next_number=1,padding=5,reset_period="yearly"))
class PlanIn(BaseModel):
 model_config=ConfigDict(extra="forbid");project_id:int;title:str=Field(min_length=2,max_length=300);aspects:str=Field(min_length=10,max_length=6000);controls:str=Field(min_length=10,max_length=6000);review_due_date:date|None=None;document_id:int|None=None
class WasteIn(BaseModel):
 model_config=ConfigDict(extra="forbid");project_id:int;record_date:date;waste_stream:Literal["general","recyclable","inert","hazardous","other"];quantity:Decimal=Field(gt=0);unit:str=Field(min_length=1,max_length=24);destination:str=Field(min_length=2,max_length=300);carrier_reference:str|None=None;hazardous:bool=False;document_id:int|None=None
class InspectionIn(BaseModel):
 model_config=ConfigDict(extra="forbid");project_id:int;inspection_date:date;category:Literal["waste","water","dust","noise","spill","biodiversity","other"];severity:Literal["low","medium","high","critical"];finding:str=Field(min_length=2,max_length=6000);due_date:date|None=None;document_id:int|None=None
class Correct(BaseModel):
 model_config=ConfigDict(extra="forbid");corrective_action:str=Field(min_length=2,max_length=6000);document_id:int=Field(gt=0)
@router.post("/bootstrap")
def bootstrap(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 if not p.has_company_permission("company.manage") and not p.has_company_permission("environment.manage"):raise HTTPException(status_code=403,detail="Company administration is required")
 boot(db,p.user.company_id);commit(db);return {"phase":28,"status":"ready"}
@router.get("/catalog")
def catalog(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 any(p,"environment.view");projects=[r for r in db.scalars(select(Project).where(Project.company_id==p.user.company_id,Project.status.in_(("ready","active"))).order_by(Project.name)).all() if p.can("environment.view",branch_id=r.branch_id,site_id=r.primary_site_id)];docs=[r for r in db.scalars(select(Document).where(Document.company_id==p.user.company_id).order_by(Document.created_at.desc())).all() if p.can("environment.view",branch_id=r.branch_id,site_id=r.site_id)];return {"projects":[row_dict(r) for r in projects],"documents":[row_dict(r) for r in docs]}
@router.get("/plans")
def plans(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 any(p,"environment.view");return [row_dict(r) for r in db.scalars(select(EnvironmentalPlan).where(EnvironmentalPlan.company_id==p.user.company_id).order_by(EnvironmentalPlan.created_at.desc())).all() if p.can("environment.view",branch_id=r.branch_id,site_id=r.site_id)]
@router.get("/waste")
def waste(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 any(p,"environment.view");return [row_dict(r) for r in db.scalars(select(EnvironmentalWasteRecord).where(EnvironmentalWasteRecord.company_id==p.user.company_id).order_by(EnvironmentalWasteRecord.record_date.desc())).all() if p.can("environment.view",branch_id=r.branch_id,site_id=r.site_id)]
@router.get("/inspections")
def inspections(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 any(p,"environment.view");return [row_dict(r) for r in db.scalars(select(EnvironmentalInspection).where(EnvironmentalInspection.company_id==p.user.company_id).order_by(EnvironmentalInspection.inspection_date.desc())).all() if p.can("environment.view",branch_id=r.branch_id,site_id=r.site_id)]
@router.get("/dashboard")
def dashboard(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 any(p,"environment.view");ps=[r for r in db.scalars(select(EnvironmentalPlan).where(EnvironmentalPlan.company_id==p.user.company_id)).all() if p.can("environment.view",branch_id=r.branch_id,site_id=r.site_id)];ws=[r for r in db.scalars(select(EnvironmentalWasteRecord).where(EnvironmentalWasteRecord.company_id==p.user.company_id)).all() if p.can("environment.view",branch_id=r.branch_id,site_id=r.site_id)];ins=[r for r in db.scalars(select(EnvironmentalInspection).where(EnvironmentalInspection.company_id==p.user.company_id)).all() if p.can("environment.view",branch_id=r.branch_id,site_id=r.site_id)];return {"approved_plans":sum(r.status=="approved" for r in ps),"pending_plans":sum(r.status=="submitted" for r in ps),"waste_quantity":str(sum((r.quantity for r in ws),Decimal("0"))),"hazardous_pending":sum(r.hazardous and r.status!="verified" for r in ws),"open_inspections":sum(r.status!="verified" for r in ins),"critical_open":sum(r.status!="verified" and r.severity=="critical" for r in ins)}
@router.post("/plans",status_code=201)
def create_plan(x:PlanIn,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 pr=project(db,p,x.project_id,"environment.manage");ensure_document(db,p.user.company_id,x.document_id);r=EnvironmentalPlan(company_id=p.user.company_id,project_id=pr.id,branch_id=pr.branch_id,site_id=pr.primary_site_id,plan_number=issue_reference(db,p.user.company_id,"ENVIRONMENT_PLAN","ENV"),title=x.title.strip(),aspects=x.aspects.strip(),controls=x.controls.strip(),review_due_date=x.review_due_date,document_id=x.document_id,prepared_by=p.user.full_name);db.add(r);db.flush();audit(db,p,"environment.plan.created",r);commit(db);return row_dict(r)
@router.post("/plans/{i}/submit")
def submit(i:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=owned(db,p,EnvironmentalPlan,i,"environment.manage","Environmental plan")
 if r.status not in {"draft","rejected"} or not r.document_id or not r.review_due_date:raise HTTPException(status_code=409,detail="A controlled document and review date are required")
 r.status,r.submitted_at="submitted",utcnow();audit(db,p,"environment.plan.submitted",r);commit(db);return row_dict(r)
@router.post("/plans/{i}/approve")
def approve(i:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=owned(db,p,EnvironmentalPlan,i,"environment.approve","Environmental plan")
 if r.status!="submitted":raise HTTPException(status_code=409,detail="Plan is not awaiting approval")
 if r.prepared_by==p.user.full_name and not allow_self_approval(db,r.company_id):raise HTTPException(status_code=422,detail="Self-approval is disabled by company policy")
 r.status,r.approved_by,r.approved_at="approved",p.user.full_name,utcnow();audit(db,p,"environment.plan.approved",r);commit(db);return row_dict(r)
@router.post("/waste",status_code=201)
def create_waste(x:WasteIn,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 pr=project(db,p,x.project_id,"environment.manage");ensure_document(db,p.user.company_id,x.document_id)
 if x.hazardous and not x.document_id:raise HTTPException(status_code=422,detail="Hazardous waste needs controlled evidence")
 r=EnvironmentalWasteRecord(company_id=p.user.company_id,project_id=pr.id,branch_id=pr.branch_id,site_id=pr.primary_site_id,waste_number=issue_reference(db,p.user.company_id,"ENVIRONMENT_WASTE","WST"),record_date=x.record_date,waste_stream=x.waste_stream,quantity=x.quantity,unit=x.unit.strip(),destination=x.destination.strip(),carrier_reference=x.carrier_reference, hazardous=x.hazardous,document_id=x.document_id,recorded_by=p.user.full_name);db.add(r);db.flush();audit(db,p,"environment.waste.recorded",r);commit(db);return row_dict(r)
@router.post("/waste/{i}/verify")
def verify_waste(i:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=owned(db,p,EnvironmentalWasteRecord,i,"environment.approve","Waste record")
 if r.status!="recorded":raise HTTPException(status_code=409,detail="Waste record is not awaiting verification")
 if r.recorded_by==p.user.full_name and not allow_self_approval(db,r.company_id):raise HTTPException(status_code=422,detail="Self-verification is disabled by company policy")
 r.status,r.verified_by,r.verified_at="verified",p.user.full_name,utcnow();audit(db,p,"environment.waste.verified",r);commit(db);return row_dict(r)
@router.post("/inspections",status_code=201)
def create_inspection(x:InspectionIn,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 pr=project(db,p,x.project_id,"environment.manage");ensure_document(db,p.user.company_id,x.document_id);r=EnvironmentalInspection(company_id=p.user.company_id,project_id=pr.id,branch_id=pr.branch_id,site_id=pr.primary_site_id,inspection_number=issue_reference(db,p.user.company_id,"ENVIRONMENT_INSPECTION","EIN"),inspection_date=x.inspection_date,category=x.category,severity=x.severity,finding=x.finding.strip(),due_date=x.due_date,document_id=x.document_id,created_by=p.user.full_name);db.add(r);db.flush();audit(db,p,"environment.inspection.created",r);commit(db);return row_dict(r)
@router.post("/inspections/{i}/remediate")
def remediate(i:int,x:Correct,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=owned(db,p,EnvironmentalInspection,i,"environment.manage","Environmental inspection")
 if r.status!="open":raise HTTPException(status_code=409,detail="Only open inspections can be remediated")
 ensure_document(db,r.company_id,x.document_id);r.status,r.corrective_action,r.document_id,r.remediated_by,r.remediated_at="remediated",x.corrective_action,x.document_id,p.user.full_name,utcnow();audit(db,p,"environment.inspection.remediated",r);commit(db);return row_dict(r)
@router.post("/inspections/{i}/verify")
def verify_inspection(i:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=owned(db,p,EnvironmentalInspection,i,"environment.approve","Environmental inspection")
 if r.status!="remediated":raise HTTPException(status_code=409,detail="Only remediated inspections can be verified")
 if r.remediated_by==p.user.full_name and not allow_self_approval(db,r.company_id):raise HTTPException(status_code=422,detail="Self-verification is disabled by company policy")
 r.status,r.verified_by,r.verified_at="verified",p.user.full_name,utcnow();audit(db,p,"environment.inspection.verified",r);commit(db);return row_dict(r)
