from __future__ import annotations
import csv,io
from datetime import date,timedelta
from typing import Any
from fastapi import APIRouter,Depends,HTTPException,Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from app.api.v1.procurement import allow_self_approval,commit,ensure_document,issue_reference,row_dict,utcnow
from app.db.session import get_db
from app.models import ComplianceObligation,DataQualityAuditEvent,DataQualityFinding,DataQualityRun,NumberSequence,Permission,ProgrammeBaseline,Project,ProjectBudgetBaseline,ProjectCorrespondence,ProjectAssuranceRecord,ResourcePlan,Role,RolePermission,SiteDailyReport
from app.security.access import Principal,current_principal
router=APIRouter(prefix="/data-quality",tags=["Phase 23 - Project Data Quality & Readiness Assurance"])
PERMISSIONS={"dataquality.view":("data_quality","view","View project data quality snapshots and findings"),"dataquality.run":("data_quality","run","Run controlled project data quality checks"),"dataquality.remediate":("data_quality","remediate","Record supplied finding remediation evidence"),"dataquality.verify":("data_quality","verify","Independently verify remediation evidence"),"dataquality.export":("data_quality","export","Export project data quality registers")}
def anywhere(p:Principal,code:str)->None:
 if not p.has_permission_anywhere(code):raise HTTPException(status_code=403,detail=f"Permission required: {code}")
def scope(p:Principal,code:str,b:int,s:int|None)->None:
 if not p.can(code,branch_id=b,site_id=s):raise HTTPException(status_code=403,detail=f"Permission required in this branch/site: {code}")
def audit(db:Session,p:Principal,action:str,e:Any,detail:dict|None=None)->None:db.add(DataQualityAuditEvent(company_id=p.user.company_id,branch_id=getattr(e,"branch_id",None),site_id=getattr(e,"site_id",None),project_id=getattr(e,"project_id",None),actor=p.user.full_name,action=action,entity_type=e.__tablename__,entity_id=str(e.id),detail=detail or {}))
def project(db:Session,p:Principal,project_id:int,code:str)->Project:
 r=db.get(Project,project_id)
 if not r or r.company_id!=p.user.company_id:raise HTTPException(status_code=404,detail="Project not found")
 scope(p,code,r.branch_id,r.primary_site_id);return r
def owned(db:Session,p:Principal,m:Any,i:int,code:str,label:str)->Any:
 r=db.get(m,i)
 if not r or r.company_id!=p.user.company_id:raise HTTPException(status_code=404,detail=f"{label} not found")
 scope(p,code,r.branch_id,r.site_id);return r
def bootstrap_data(db:Session,cid:int)->None:
 perms={}
 for code,(module,action,description) in PERMISSIONS.items():
  r=db.scalar(select(Permission).where(Permission.code==code))
  if not r:r=Permission(code=code,module=module,action=action,description=description);db.add(r);db.flush()
  perms[code]=r
 roles={r.code:r for r in db.scalars(select(Role).where(Role.company_id==cid)).all()}
 for code,name,level in (("DATA_QUALITY_MANAGER","Data Quality Manager","company"),("DATA_QUALITY_OFFICER","Data Quality Officer","branch"),("DATA_QUALITY_REVIEWER","Data Quality Reviewer","company")):
  if code not in roles:roles[code]=Role(company_id=cid,code=code,name=name,scope_level=level,description=f"Phase 23 {name.lower()} role",is_system=True,is_active=True);db.add(roles[code]);db.flush()
 grants={"SYSTEM_ADMIN":set(PERMISSIONS),"HQ_EXECUTIVE":set(PERMISSIONS),"BRANCH_MANAGER":set(PERMISSIONS),"PROJECT_MANAGER":{"dataquality.view","dataquality.run","dataquality.remediate","dataquality.export"},"SITE_MANAGER":{"dataquality.view","dataquality.run","dataquality.remediate"},"APPROVER":{"dataquality.verify"},"AUDITOR":{"dataquality.view","dataquality.export"},"DATA_QUALITY_MANAGER":set(PERMISSIONS),"DATA_QUALITY_OFFICER":{"dataquality.view","dataquality.run","dataquality.remediate","dataquality.export"},"DATA_QUALITY_REVIEWER":{"dataquality.view","dataquality.verify","dataquality.export"}}
 for rc,codes in grants.items():
  role=roles.get(rc)
  if not role:continue
  existing=set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id==role.id)).all())
  for code in codes:
   if perms[code].id not in existing:db.add(RolePermission(role_id=role.id,permission_id=perms[code].id));existing.add(perms[code].id)
 if not db.scalar(select(NumberSequence).where(NumberSequence.company_id==cid,NumberSequence.code=="DATA_QUALITY_RUN")):db.add(NumberSequence(company_id=cid,code="DATA_QUALITY_RUN",name="Data Quality Run",prefix="DQR",next_number=1,padding=5,reset_period="yearly"))
class RemediateInput(BaseModel):
 model_config=ConfigDict(extra="forbid");document_id:int=Field(gt=0);note:str=Field(min_length=2,max_length=4000)
@router.post("/bootstrap")
def bootstrap(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
 if not p.has_company_permission("company.manage") and not p.has_company_permission("dataquality.run"):raise HTTPException(status_code=403,detail="Company administration is required to initialise Phase 23")
 bootstrap_data(db,p.user.company_id);commit(db);return {"phase":23,"status":"ready"}
@router.get("/catalog")
def catalog(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
 anywhere(p,"dataquality.view");rows=[row_dict(r) for r in db.scalars(select(Project).where(Project.company_id==p.user.company_id,Project.status.in_(("ready","active"))).order_by(Project.name)).all() if p.can("dataquality.view",branch_id=r.branch_id,site_id=r.primary_site_id)];return {"projects":rows,"permissions":[x for x in PERMISSIONS if p.has_permission_anywhere(x)]}
def checks(db:Session,r:Project)->list[dict[str,Any]]:
 today=date.today();recent=today-timedelta(days=7);active=db.scalar(select(func.count()).select_from(SiteDailyReport).where(SiteDailyReport.project_id==r.id,SiteDailyReport.status=="approved",SiteDailyReport.report_date>=recent)) or 0
 values=[("approved_budget",bool(db.scalar(select(func.count()).select_from(ProjectBudgetBaseline).where(ProjectBudgetBaseline.project_id==r.id,ProjectBudgetBaseline.status=="approved"))),"critical","No approved project budget baseline"),("approved_programme",bool(db.scalar(select(func.count()).select_from(ProgrammeBaseline).where(ProgrammeBaseline.project_id==r.id,ProgrammeBaseline.status=="approved"))),"critical","No approved programme baseline"),("approved_resource_plan",bool(db.scalar(select(func.count()).select_from(ResourcePlan).where(ResourcePlan.project_id==r.id,ResourcePlan.status=="approved"))),"warning","No approved resource plan"),("recent_daily_evidence",bool(active),"warning","No approved daily site report in the last seven days"),("overdue_correspondence",not bool(db.scalar(select(func.count()).select_from(ProjectCorrespondence).where(ProjectCorrespondence.project_id==r.id,ProjectCorrespondence.response_due_date<today,ProjectCorrespondence.status!="closed"))),"warning","Overdue project correspondence remains open"),("overdue_compliance",not bool(db.scalar(select(func.count()).select_from(ComplianceObligation).where(ComplianceObligation.project_id==r.id,ComplianceObligation.status=="active",ComplianceObligation.next_due_date<today))),"warning","Overdue active compliance obligation"),("critical_assurance",not bool(db.scalar(select(func.count()).select_from(ProjectAssuranceRecord).where(ProjectAssuranceRecord.project_id==r.id,ProjectAssuranceRecord.priority=="critical",ProjectAssuranceRecord.status!="closed"))),"critical","Critical assurance record remains open")]
 return [{"code":c,"passed":ok,"severity":s,"message":m} for c,ok,s,m in values]
@router.post("/projects/{project_id:int}/runs",status_code=201)
def run(project_id:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
 pr=project(db,p,project_id,"dataquality.run");rows=checks(db,pr);fails=[x for x in rows if not x["passed"]];sequence=(db.scalar(select(func.max(DataQualityRun.sequence)).where(DataQualityRun.project_id==pr.id,DataQualityRun.run_date==date.today())) or 0)+1;activity=sum((db.scalar(select(func.count()).select_from(m).where(m.project_id==pr.id)) or 0 for m in (SiteDailyReport,ProjectCorrespondence,ComplianceObligation)))
 row=DataQualityRun(company_id=pr.company_id,branch_id=pr.branch_id,site_id=pr.primary_site_id,project_id=pr.id,run_number=issue_reference(db,pr.company_id,"DATA_QUALITY_RUN","DQR"),run_date=date.today(),sequence=sequence,score_pct=round(100*(len(rows)-len(fails))/len(rows)),status="attention" if fails else "ready",checks={x["code"]:x for x in rows},source_activity_count=activity,run_by=p.user.full_name);db.add(row);db.flush()
 for item in fails:db.add(DataQualityFinding(company_id=pr.company_id,branch_id=pr.branch_id,site_id=pr.primary_site_id,project_id=pr.id,run_id=row.id,check_code=item["code"],severity=item["severity"],message=item["message"]))
 audit(db,p,"dataquality.run.created",row,{"finding_count":len(fails)});commit(db);return row_dict(row)
@router.get("/runs")
def runs(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->list[dict[str,Any]]:
 anywhere(p,"dataquality.view");return [row_dict(r) for r in db.scalars(select(DataQualityRun).where(DataQualityRun.company_id==p.user.company_id).order_by(DataQualityRun.created_at.desc())).all() if p.can("dataquality.view",branch_id=r.branch_id,site_id=r.site_id)]
@router.get("/findings")
def findings(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->list[dict[str,Any]]:
 anywhere(p,"dataquality.view");return [row_dict(r) for r in db.scalars(select(DataQualityFinding).where(DataQualityFinding.company_id==p.user.company_id).order_by(DataQualityFinding.created_at.desc())).all() if p.can("dataquality.view",branch_id=r.branch_id,site_id=r.site_id)]
@router.post("/findings/{finding_id:int}/remediate")
def remediate(finding_id:int,payload:RemediateInput,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
 row=owned(db,p,DataQualityFinding,finding_id,"dataquality.remediate","Data quality finding")
 if row.status!="open":raise HTTPException(status_code=409,detail="Only open findings can be remediated")
 ensure_document(db,row.company_id,payload.document_id);row.remediation_document_id,row.remediation_note,row.remediated_by,row.remediated_at,row.status=payload.document_id,payload.note,p.user.full_name,utcnow(),"remediated";audit(db,p,"dataquality.finding.remediated",row);commit(db);return row_dict(row)
@router.post("/findings/{finding_id:int}/verify")
def verify(finding_id:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
 row=owned(db,p,DataQualityFinding,finding_id,"dataquality.verify","Data quality finding")
 if row.status!="remediated":raise HTTPException(status_code=409,detail="Only remediated findings can be verified")
 if row.remediated_by==p.user.full_name and not allow_self_approval(db,row.company_id):raise HTTPException(status_code=422,detail="Self-verification is disabled by company policy")
 row.status,row.verified_by,row.verified_at="verified",p.user.full_name,utcnow();audit(db,p,"dataquality.finding.verified",row);commit(db);return row_dict(row)
@router.get("/dashboard")
def dashboard(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->dict[str,Any]:
 anywhere(p,"dataquality.view");runs=[r for r in db.scalars(select(DataQualityRun).where(DataQualityRun.company_id==p.user.company_id)).all() if p.can("dataquality.view",branch_id=r.branch_id,site_id=r.site_id)];findings=[r for r in db.scalars(select(DataQualityFinding).where(DataQualityFinding.company_id==p.user.company_id)).all() if p.can("dataquality.view",branch_id=r.branch_id,site_id=r.site_id)];return {"runs":len(runs),"ready_runs":sum(r.status=="ready" for r in runs),"average_score":round(sum(r.score_pct for r in runs)/len(runs)) if runs else 0,"open_findings":sum(r.status=="open" for r in findings),"remediated_findings":sum(r.status=="remediated" for r in findings),"critical_open":sum(r.status=="open" and r.severity=="critical" for r in findings)}
@router.get("/exports/findings.csv")
def export(db:Session=Depends(get_db),p:Principal=Depends(current_principal))->StreamingResponse:
 anywhere(p,"dataquality.export");s=io.StringIO();fields=["run_id","project_id","check_code","severity","message","status","remediated_at","verified_at"];w=csv.DictWriter(s,fieldnames=fields);w.writeheader()
 for r in db.scalars(select(DataQualityFinding).where(DataQualityFinding.company_id==p.user.company_id)).all():
  if p.can("dataquality.export",branch_id=r.branch_id,site_id=r.site_id):w.writerow({x:row_dict(r).get(x,"") for x in fields})
 return StreamingResponse(iter([s.getvalue()]),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=data-quality-findings.csv"})
@router.get("/audit")
def events(limit:int=Query(default=250,ge=1,le=1000),db:Session=Depends(get_db),p:Principal=Depends(current_principal))->list[dict[str,Any]]:
 anywhere(p,"dataquality.view");return [row_dict(r) for r in db.scalars(select(DataQualityAuditEvent).where(DataQualityAuditEvent.company_id==p.user.company_id).order_by(DataQualityAuditEvent.occurred_at.desc()).limit(limit)).all() if r.branch_id is None or p.can("dataquality.view",branch_id=r.branch_id,site_id=r.site_id)]
