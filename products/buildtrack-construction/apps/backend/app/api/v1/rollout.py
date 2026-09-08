from __future__ import annotations
from datetime import date
from typing import Any, Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.v1.procurement import commit,ensure_document,issue_reference,row_dict,utcnow
from app.db.session import get_db
from app.models import Branch,CompanySetting,NumberSequence,Permission,Role,RolePermission,RolloutAuditEvent,RolloutControlItem,RolloutWave
from app.security.access import Principal,current_principal
router=APIRouter(prefix="/rollout",tags=["Phase 16 - Professional Rollout"])
PERMS={"rollout.view":("rollout","view","View rollout readiness and launch evidence"),"rollout.manage":("rollout","manage","Manage rollout plans and readiness evidence"),"rollout.review":("rollout","review","Independently review rollout readiness"),"rollout.launch":("rollout","launch","Confirm an approved branch go-live")}
DEFAULT_CONTROLS=(("backup","Verified backup and restore point"),("recovery_test","Recovery test evidence"),("data_migration","Data migration reconciliation"),("security_review","Security review and remediation"),("uat","User acceptance testing sign-off"),("training","User training and support readiness"),("communications","Go-live communication and support contacts"))
def anywhere(p:Principal,perm:str)->None:
 if not p.has_permission_anywhere(perm):raise HTTPException(status_code=403,detail=f"Permission required: {perm}")
def wave(db:Session,p:Principal,wid:int,perm:str)->RolloutWave:
 r=db.get(RolloutWave,wid)
 if not r or r.company_id!=p.user.company_id:raise HTTPException(status_code=404,detail="Rollout wave not found")
 if not p.can(perm,branch_id=r.branch_id):raise HTTPException(status_code=403,detail=f"Permission required in this branch: {perm}")
 return r
def audit(db:Session,p:Principal,action:str,r:RolloutWave,entity:Any,detail:dict[str,Any]|None=None)->None:
 db.add(RolloutAuditEvent(company_id=r.company_id,branch_id=r.branch_id,rollout_wave_id=r.id,actor=p.user.full_name,action=action,entity_type=entity.__tablename__,entity_id=str(entity.id),detail=detail or {}))
def bootstrap_data(db:Session,cid:int)->None:
 permissions={}
 for code,(module,action,description) in PERMS.items():
  r=db.scalar(select(Permission).where(Permission.code==code))
  if not r:r=Permission(code=code,module=module,action=action,description=description);db.add(r);db.flush()
  permissions[code]=r
 roles={r.code:r for r in db.scalars(select(Role).where(Role.company_id==cid)).all()}
 for code,name,scope in (("ROLLOUT_MANAGER","Rollout Manager","branch"),("ROLLOUT_REVIEWER","Rollout Reviewer","company")):
  if code not in roles:r=Role(company_id=cid,code=code,name=name,scope_level=scope,description=f"Phase 16 {name.lower()} role",is_system=True,is_active=True);db.add(r);db.flush();roles[code]=r
 grants={"SYSTEM_ADMIN":set(PERMS),"HQ_EXECUTIVE":set(PERMS),"BRANCH_MANAGER":set(PERMS),"ROLLOUT_MANAGER":{"rollout.view","rollout.manage"},"ROLLOUT_REVIEWER":{"rollout.view","rollout.review"},"SITE_MANAGER":{"rollout.view"},"AUDITOR":{"rollout.view"}}
 for code,codes in grants.items():
  role=roles.get(code)
  if not role:continue
  old=set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id==role.id)).all())
  for code in codes:
   if permissions[code].id not in old:db.add(RolePermission(role_id=role.id,permission_id=permissions[code].id));old.add(permissions[code].id)
 if not db.scalar(select(NumberSequence).where(NumberSequence.company_id==cid,NumberSequence.code=="ROLLOUT_WAVE")):db.add(NumberSequence(company_id=cid,code="ROLLOUT_WAVE",name="Rollout Wave",prefix="RLW",next_number=1,padding=4,reset_period="yearly"))
 if not db.scalar(select(CompanySetting).where(CompanySetting.company_id==cid,CompanySetting.key=="rollout_policy")):db.add(CompanySetting(company_id=cid,key="rollout_policy",value={"require_control_evidence":True,"minimum_required_controls":len(DEFAULT_CONTROLS)},description="Phase 16 rollout safety policy"))
class WaveInput(BaseModel):
 model_config=ConfigDict(extra="forbid");branch_id:int;name:str=Field(min_length=2,max_length=240);planned_go_live_date:date;owner:str|None=None
class ControlInput(BaseModel):
 model_config=ConfigDict(extra="forbid");title:str=Field(min_length=2,max_length=240);control_type:str=Field(min_length=2,max_length=80);required:bool=True;due_date:date|None=None;evidence_document_id:int|None=None;assigned_to:str|None=None;result_notes:str|None=None
class CompleteInput(BaseModel):
 model_config=ConfigDict(extra="forbid");evidence_document_id:int|None=None;result_notes:str|None=Field(default=None,max_length=4000)
class ReviewInput(BaseModel):
 model_config=ConfigDict(extra="forbid");decision:Literal["approve","return"];comment:str|None=Field(default=None,max_length=2000)
class LaunchInput(BaseModel):
 model_config=ConfigDict(extra="forbid");actual_go_live_date:date|None=None
@router.post("/bootstrap")
def bootstrap(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
 if not p.has_company_permission("company.manage") and not p.has_company_permission("rollout.manage"):raise HTTPException(status_code=403,detail="Company administration is required to initialise Phase 16")
 bootstrap_data(db,p.user.company_id);commit(db);return {"phase":16,"status":"ready"}
@router.get("/branches")
def branches(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->list[dict[str,Any]]:
 anywhere(p,"rollout.view");return [row_dict(r) for r in db.scalars(select(Branch).where(Branch.company_id==p.user.company_id,Branch.is_active==True)).all() if p.can("rollout.view",branch_id=r.id)]
@router.get("/waves")
def waves(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->list[dict[str,Any]]:
 anywhere(p,"rollout.view");return [row_dict(r) for r in db.scalars(select(RolloutWave).where(RolloutWave.company_id==p.user.company_id).order_by(RolloutWave.planned_go_live_date,RolloutWave.id)).all() if p.can("rollout.view",branch_id=r.branch_id)]
@router.post("/waves",status_code=201)
def create_wave(x:WaveInput,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
 b=db.get(Branch,x.branch_id)
 if not b or b.company_id!=p.user.company_id:raise HTTPException(status_code=422,detail="Branch does not belong to this company")
 if not p.can("rollout.manage",branch_id=b.id):raise HTTPException(status_code=403,detail="Permission required in this branch: rollout.manage")
 r=RolloutWave(company_id=b.company_id,branch_id=b.id,wave_number=issue_reference(db,b.company_id,"ROLLOUT_WAVE","RLW"),name=x.name,planned_go_live_date=x.planned_go_live_date,owner=x.owner,created_by=p.user.full_name);db.add(r);db.flush()
 for kind,title in DEFAULT_CONTROLS:db.add(RolloutControlItem(company_id=b.company_id,branch_id=b.id,rollout_wave_id=r.id,control_type=kind,title=title,due_date=x.planned_go_live_date,assigned_to=x.owner))
 audit(db,p,"rollout.wave.created",r,r,{"default_controls":len(DEFAULT_CONTROLS)});commit(db);return row_dict(r)
@router.get("/waves/{wave_id:int}/controls")
def controls(wave_id:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->list[dict[str,Any]]:
 r=wave(db,p,wave_id,"rollout.view");return [row_dict(i) for i in db.scalars(select(RolloutControlItem).where(RolloutControlItem.rollout_wave_id==r.id).order_by(RolloutControlItem.required.desc(),RolloutControlItem.due_date,RolloutControlItem.id)).all()]
@router.post("/waves/{wave_id:int}/controls",status_code=201)
def add_control(wave_id:int,x:ControlInput,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
 r=wave(db,p,wave_id,"rollout.manage")
 if r.status not in {"draft","returned"}:raise HTTPException(status_code=409,detail="Controls can only be changed in draft/returned rollout waves")
 ensure_document(db,r.company_id,x.evidence_document_id);i=RolloutControlItem(company_id=r.company_id,branch_id=r.branch_id,rollout_wave_id=r.id,title=x.title,control_type=x.control_type,required=x.required,due_date=x.due_date,evidence_document_id=x.evidence_document_id,assigned_to=x.assigned_to,result_notes=x.result_notes);db.add(i);db.flush();audit(db,p,"rollout.control.added",r,i);commit(db);return row_dict(i)
@router.post("/controls/{control_id:int}/complete")
def complete_control(control_id:int,x:CompleteInput,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
 i=db.get(RolloutControlItem,control_id)
 if not i or i.company_id!=p.user.company_id:raise HTTPException(status_code=404,detail="Rollout control not found")
 r=wave(db,p,i.rollout_wave_id,"rollout.manage")
 if r.status not in {"draft","returned"}:raise HTTPException(status_code=409,detail="Readiness evidence is frozen while the rollout is under review or launched")
 cfg=db.scalar(select(CompanySetting).where(CompanySetting.company_id==r.company_id,CompanySetting.key=="rollout_policy"));required_evidence=bool((cfg.value if cfg else {}).get("require_control_evidence",True))
 if required_evidence and not (x.evidence_document_id or i.evidence_document_id):raise HTTPException(status_code=409,detail="Controlled evidence is required before this rollout control can be completed")
 ensure_document(db,r.company_id,x.evidence_document_id);i.evidence_document_id=x.evidence_document_id or i.evidence_document_id;i.result_notes=x.result_notes or i.result_notes;i.status="completed";i.completed_by=p.user.full_name;i.completed_at=utcnow();audit(db,p,"rollout.control.completed",r,i);commit(db);return row_dict(i)
@router.post("/waves/{wave_id:int}/submit")
def submit_wave(wave_id:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
 r=wave(db,p,wave_id,"rollout.manage")
 if r.status not in {"draft","returned"}:raise HTTPException(status_code=409,detail="Only draft/returned rollout waves can be submitted")
 required=db.scalars(select(RolloutControlItem).where(RolloutControlItem.rollout_wave_id==r.id,RolloutControlItem.required==True)).all()
 if not required or any(i.status!="completed" for i in required):raise HTTPException(status_code=409,detail="Every required backup, recovery, migration, security, UAT, training and communication control must be completed before review")
 r.status="pending_review";r.submitted_at=utcnow();audit(db,p,"rollout.wave.submitted",r,r);commit(db);return row_dict(r)
@router.post("/waves/{wave_id:int}/review")
def review_wave(wave_id:int,x:ReviewInput,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
 r=wave(db,p,wave_id,"rollout.review")
 if r.status!="pending_review":raise HTTPException(status_code=409,detail="Rollout wave is not awaiting independent review")
 if r.created_by==p.user.full_name:raise HTTPException(status_code=422,detail="The rollout creator cannot complete its independent readiness review")
 r.status="approved" if x.decision=="approve" else "returned";r.reviewed_by=p.user.full_name;r.reviewed_at=utcnow();r.review_comment=x.comment;audit(db,p,f"rollout.wave.{x.decision}d",r,r,{"comment":x.comment});commit(db);return row_dict(r)
@router.post("/waves/{wave_id:int}/launch")
def launch_wave(wave_id:int,x:LaunchInput,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
 r=wave(db,p,wave_id,"rollout.launch")
 if r.status!="approved":raise HTTPException(status_code=409,detail="Only independently approved rollout waves can be launched")
 r.status="launched";r.actual_go_live_date=x.actual_go_live_date or date.today();audit(db,p,"rollout.wave.launched",r,r,{"actual_go_live_date":r.actual_go_live_date.isoformat()});commit(db);return row_dict(r)
@router.get("/dashboard")
def dashboard(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
 anywhere(p,"rollout.view");rows=[r for r in db.scalars(select(RolloutWave).where(RolloutWave.company_id==p.user.company_id)).all() if p.can("rollout.view",branch_id=r.branch_id)];ids={r.id for r in rows};items=[i for i in db.scalars(select(RolloutControlItem).where(RolloutControlItem.company_id==p.user.company_id)).all() if i.rollout_wave_id in ids];today=date.today();return {"waves":len(rows),"draft":sum(r.status in {"draft","returned"} for r in rows),"pending_review":sum(r.status=="pending_review" for r in rows),"approved":sum(r.status=="approved" for r in rows),"launched":sum(r.status=="launched" for r in rows),"required_open":sum(i.required and i.status!="completed" for i in items),"overdue_controls":sum(i.status!="completed" and i.due_date is not None and i.due_date<today for i in items)}
@router.get("/audit")
def audit_events(limit:int=Query(default=250,ge=1,le=1000),db:Session=Depends(get_db),p:Principal=Depends(current_principal))->list[dict[str,Any]]:
 anywhere(p,"rollout.view");return [row_dict(i) for i in db.scalars(select(RolloutAuditEvent).where(RolloutAuditEvent.company_id==p.user.company_id).order_by(RolloutAuditEvent.occurred_at.desc()).limit(limit)).all() if p.can("rollout.view",branch_id=i.branch_id)]
