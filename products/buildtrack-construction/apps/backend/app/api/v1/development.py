from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.v1.procurement import commit,ensure_document,issue_reference,row_dict
from app.db.session import get_db
from app.models import Employee,EmployeeCredential,EmployeeOnboardingItem,EmployeePerformanceReview,EmployeeTrainingRecord,NumberSequence,Permission,RecruitmentCandidate,Role,RolePermission
from app.security.access import Principal,current_principal
router=APIRouter(prefix="/development",tags=["Phase 15 - HR Development and Compliance"])
PERMS={"development.view":("development","view","View recruitment and employee-development records"),"development.manage":("development","manage","Manage recruitment, credentials, training and reviews"),"development.review":("development","review","Acknowledge employee performance reviews")}
def anywhere(p:Principal,perm:str)->None:
 if not p.has_permission_anywhere(perm):raise HTTPException(status_code=403,detail=f"Permission required: {perm}")
def employee(db:Session,p:Principal,eid:int,perm:str)->Employee:
 r=db.get(Employee,eid)
 if not r or r.company_id!=p.user.company_id:raise HTTPException(status_code=404,detail="Employee not found")
 if not p.can(perm,branch_id=r.branch_id,site_id=r.site_id):raise HTTPException(status_code=403,detail=f"Permission required in this branch/site: {perm}")
 return r
def bootstrap(db:Session,cid:int)->None:
 perms={}
 for code,(module,action,desc) in PERMS.items():
  r=db.scalar(select(Permission).where(Permission.code==code))
  if not r:r=Permission(code=code,module=module,action=action,description=desc);db.add(r);db.flush()
  perms[code]=r
 roles={r.code:r for r in db.scalars(select(Role).where(Role.company_id==cid)).all()}
 for code,name,scope in (("HR_MANAGER","HR Manager","company"),("TRAINING_OFFICER","Training Officer","branch")):
  if code not in roles:r=Role(company_id=cid,code=code,name=name,scope_level=scope,description=f"Phase 15 {name.lower()} role",is_system=True,is_active=True);db.add(r);db.flush();roles[code]=r
 grants={"SYSTEM_ADMIN":set(PERMS),"HQ_EXECUTIVE":set(PERMS),"BRANCH_MANAGER":set(PERMS),"HR_MANAGER":set(PERMS),"TRAINING_OFFICER":{"development.view","development.manage"},"SITE_MANAGER":{"development.view"},"AUDITOR":{"development.view"}}
 for code,codes in grants.items():
  role=roles.get(code)
  if not role:continue
  old=set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id==role.id)).all())
  for permission in codes:
   if perms[permission].id not in old:db.add(RolePermission(role_id=role.id,permission_id=perms[permission].id));old.add(perms[permission].id)
 if not db.scalar(select(NumberSequence).where(NumberSequence.company_id==cid,NumberSequence.code=="RECRUITMENT_CANDIDATE")):
  db.add(NumberSequence(company_id=cid,code="RECRUITMENT_CANDIDATE",name="Recruitment Candidate",prefix="CAN",next_number=1,padding=5,reset_period="yearly"))
class CandidateInput(BaseModel):
 model_config=ConfigDict(extra="forbid");full_name:str=Field(min_length=2,max_length=240);position:str=Field(min_length=2,max_length=160);application_date:date;branch_id:int|None=None;site_id:int|None=None;phone:str|None=None;email:str|None=None;cv_document_id:int|None=None;notes:str|None=None
class CandidateStatusInput(BaseModel):
 model_config=ConfigDict(extra="forbid");status:Literal["applied","screening","interview","offer","appointed","rejected","withdrawn"]
class CredentialInput(BaseModel):
 model_config=ConfigDict(extra="forbid");credential_type:str=Field(min_length=2,max_length=80);reference_number:str|None=None;issuer:str|None=None;issue_date:date|None=None;expiry_date:date|None=None;document_id:int|None=None;notes:str|None=None
class TrainingInput(BaseModel):
 model_config=ConfigDict(extra="forbid");course_name:str=Field(min_length=2,max_length=240);category:str="professional";provider:str|None=None;start_date:date|None=None;completion_date:date|None=None;expiry_date:date|None=None;cost:Decimal=Field(default=0,ge=0);status:Literal["planned","in_progress","completed","expired"]="planned";certificate_document_id:int|None=None;notes:str|None=None
class OnboardingInput(BaseModel):
 model_config=ConfigDict(extra="forbid");title:str=Field(min_length=2,max_length=240);onboarding_type:str=Field(default="general",min_length=2,max_length=80);due_date:date|None=None;document_id:int|None=None;notes:str|None=None;assigned_to:str|None=None
class ReviewInput(BaseModel):
 model_config=ConfigDict(extra="forbid");review_period_start:date;review_period_end:date;delivery_score:Decimal=Field(ge=0,le=5);quality_score:Decimal=Field(ge=0,le=5);safety_score:Decimal=Field(ge=0,le=5);conduct_score:Decimal=Field(ge=0,le=5);development_plan:str|None=None
@router.post("/bootstrap")
def phase_bootstrap(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
 if not p.has_company_permission("company.manage") and not p.has_company_permission("development.manage"):raise HTTPException(status_code=403,detail="Company administration is required to initialise HR Development")
 bootstrap(db,p.user.company_id);commit(db);return {"phase":15,"status":"ready"}
@router.get("/employees")
def employees(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->list[dict[str,Any]]:
 anywhere(p,"development.view");return [row_dict(r) for r in db.scalars(select(Employee).where(Employee.company_id==p.user.company_id)).all() if p.can("development.view",branch_id=r.branch_id,site_id=r.site_id)]
@router.post("/candidates",status_code=201)
def candidate(x:CandidateInput,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
 anywhere(p,"development.manage");ensure_document(db,p.user.company_id,x.cv_document_id);r=RecruitmentCandidate(company_id=p.user.company_id,branch_id=x.branch_id,site_id=x.site_id,candidate_number=issue_reference(db,p.user.company_id,"RECRUITMENT_CANDIDATE","CAN"),full_name=x.full_name,phone=x.phone,email=x.email,position=x.position,application_date=x.application_date,cv_document_id=x.cv_document_id,notes=x.notes,created_by=p.user.full_name);db.add(r);commit(db);return row_dict(r)
@router.get("/candidates")
def candidates(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->list[dict[str,Any]]:
 anywhere(p,"development.view");return [row_dict(r) for r in db.scalars(select(RecruitmentCandidate).where(RecruitmentCandidate.company_id==p.user.company_id).order_by(RecruitmentCandidate.created_at.desc())).all() if r.branch_id is None or p.can("development.view",branch_id=r.branch_id,site_id=r.site_id)]
@router.post("/candidates/{candidate_id:int}/status")
def candidate_status(candidate_id:int,x:CandidateStatusInput,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
 anywhere(p,"development.manage");r=db.get(RecruitmentCandidate,candidate_id)
 if not r or r.company_id!=p.user.company_id:raise HTTPException(status_code=404,detail="Recruitment candidate not found")
 if r.branch_id is not None and not p.can("development.manage",branch_id=r.branch_id,site_id=r.site_id):raise HTTPException(status_code=403,detail="Permission required in this branch/site: development.manage")
 if r.status in {"appointed","rejected","withdrawn"}:raise HTTPException(status_code=409,detail="This candidate has reached a terminal status")
 r.status=x.status;commit(db);return row_dict(r)
@router.post("/employees/{eid:int}/credentials",status_code=201)
def credential(eid:int,x:CredentialInput,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
 e=employee(db,p,eid,"development.manage");ensure_document(db,e.company_id,x.document_id);r=EmployeeCredential(company_id=e.company_id,employee_id=e.id,credential_type=x.credential_type,reference_number=x.reference_number,issuer=x.issuer,issue_date=x.issue_date,expiry_date=x.expiry_date,document_id=x.document_id,notes=x.notes,recorded_by=p.user.full_name);db.add(r);commit(db);return row_dict(r)
@router.get("/employees/{eid:int}/credentials")
def credentials(eid:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->list[dict[str,Any]]:
 e=employee(db,p,eid,"development.view");return [row_dict(r) for r in db.scalars(select(EmployeeCredential).where(EmployeeCredential.employee_id==e.id).order_by(EmployeeCredential.expiry_date)).all()]
@router.post("/employees/{eid:int}/training",status_code=201)
def training(eid:int,x:TrainingInput,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
 e=employee(db,p,eid,"development.manage");ensure_document(db,e.company_id,x.certificate_document_id);r=EmployeeTrainingRecord(company_id=e.company_id,employee_id=e.id,course_name=x.course_name,provider=x.provider,category=x.category,start_date=x.start_date,completion_date=x.completion_date,expiry_date=x.expiry_date,cost=x.cost,status=x.status,certificate_document_id=x.certificate_document_id,notes=x.notes,recorded_by=p.user.full_name);db.add(r);commit(db);return row_dict(r)
@router.get("/employees/{eid:int}/training")
def training_records(eid:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->list[dict[str,Any]]:
 e=employee(db,p,eid,"development.view");return [row_dict(r) for r in db.scalars(select(EmployeeTrainingRecord).where(EmployeeTrainingRecord.employee_id==e.id).order_by(EmployeeTrainingRecord.completion_date.desc())).all()]
@router.post("/employees/{eid:int}/onboarding",status_code=201)
def onboarding(eid:int,x:OnboardingInput,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
 e=employee(db,p,eid,"development.manage");ensure_document(db,e.company_id,x.document_id);r=EmployeeOnboardingItem(company_id=e.company_id,employee_id=e.id,title=x.title,onboarding_type=x.onboarding_type,due_date=x.due_date,document_id=x.document_id,notes=x.notes,assigned_to=x.assigned_to,created_by=p.user.full_name);db.add(r);commit(db);return row_dict(r)
@router.get("/employees/{eid:int}/onboarding")
def onboarding_items(eid:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->list[dict[str,Any]]:
 e=employee(db,p,eid,"development.view");return [row_dict(r) for r in db.scalars(select(EmployeeOnboardingItem).where(EmployeeOnboardingItem.employee_id==e.id).order_by(EmployeeOnboardingItem.status,EmployeeOnboardingItem.due_date)).all()]
@router.post("/employees/{eid:int}/onboarding/{item_id:int}/complete")
def complete_onboarding(eid:int,item_id:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
 e=employee(db,p,eid,"development.manage");r=db.get(EmployeeOnboardingItem,item_id)
 if not r or r.company_id!=e.company_id or r.employee_id!=e.id:raise HTTPException(status_code=404,detail="Onboarding item not found")
 if r.status!="open":raise HTTPException(status_code=409,detail="Only open onboarding items can be completed")
 r.status="completed";r.completed_by=p.user.full_name;r.completed_at=datetime.now(timezone.utc);commit(db);return row_dict(r)
@router.post("/employees/{eid:int}/performance",status_code=201)
def performance(eid:int,x:ReviewInput,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
 e=employee(db,p,eid,"development.manage")
 if x.review_period_end<x.review_period_start:raise HTTPException(status_code=422,detail="Review period end cannot precede its start")
 score=((x.delivery_score+x.quality_score+x.safety_score+x.conduct_score)/Decimal("4")).quantize(Decimal("0.01"));r=EmployeePerformanceReview(company_id=e.company_id,employee_id=e.id,review_period_start=x.review_period_start,review_period_end=x.review_period_end,delivery_score=x.delivery_score,quality_score=x.quality_score,safety_score=x.safety_score,conduct_score=x.conduct_score,overall_score=score,development_plan=x.development_plan,reviewed_by=p.user.full_name);db.add(r);commit(db);return row_dict(r)
@router.get("/employees/{eid:int}/performance")
def performance_reviews(eid:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->list[dict[str,Any]]:
 e=employee(db,p,eid,"development.view");return [row_dict(r) for r in db.scalars(select(EmployeePerformanceReview).where(EmployeePerformanceReview.employee_id==e.id).order_by(EmployeePerformanceReview.review_period_end.desc())).all()]
@router.post("/employees/{eid:int}/performance/{review_id:int}/acknowledge")
def acknowledge_review(eid:int,review_id:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
 e=employee(db,p,eid,"development.review");r=db.get(EmployeePerformanceReview,review_id)
 if not r or r.company_id!=e.company_id or r.employee_id!=e.id:raise HTTPException(status_code=404,detail="Performance review not found")
 if r.acknowledged_at:raise HTTPException(status_code=409,detail="Review was already acknowledged")
 r.status="acknowledged";r.acknowledged_at=datetime.now(timezone.utc);commit(db);return row_dict(r)
@router.get("/dashboard")
def dashboard(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
 anywhere(p,"development.view");ids={r.id for r in db.scalars(select(Employee).where(Employee.company_id==p.user.company_id)).all() if p.can("development.view",branch_id=r.branch_id,site_id=r.site_id)};today=date.today();creds=[r for r in db.scalars(select(EmployeeCredential).where(EmployeeCredential.company_id==p.user.company_id)).all() if r.employee_id in ids];training=[r for r in db.scalars(select(EmployeeTrainingRecord).where(EmployeeTrainingRecord.company_id==p.user.company_id)).all() if r.employee_id in ids];onboarding=[r for r in db.scalars(select(EmployeeOnboardingItem).where(EmployeeOnboardingItem.company_id==p.user.company_id)).all() if r.employee_id in ids];return {"employees":len(ids),"credentials_expiring_30_days":sum(r.expiry_date is not None and today<=r.expiry_date<=today+timedelta(days=30) for r in creds),"credentials_expired":sum(r.expiry_date is not None and r.expiry_date<today for r in creds),"training_planned":sum(r.status in {"planned","in_progress"} for r in training),"training_expiring_30_days":sum(r.expiry_date is not None and today<=r.expiry_date<=today+timedelta(days=30) for r in training),"onboarding_open":sum(r.status=="open" for r in onboarding),"onboarding_overdue":sum(r.status=="open" and r.due_date is not None and r.due_date<today for r in onboarding),"candidates":len(candidates(db=db,p=p))}
