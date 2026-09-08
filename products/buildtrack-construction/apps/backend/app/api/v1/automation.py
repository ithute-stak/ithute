from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models import AutomationAuditEvent,AutomationRule,Branch,Permission,Role,RolePermission
from app.api.v1.procurement import commit,row_dict
from app.security.access import Principal,current_principal
router=APIRouter(prefix="/automation",tags=["Phase 35 - Automation"])
class RuleIn(BaseModel):branch_id:int|None=None;name:str=Field(min_length=2,max_length=160);trigger:str=Field(min_length=2,max_length=80);channel:str=Field(min_length=2,max_length=40)
def allowed(p,c,b=None):
 if p.has_company_permission("company.manage"):return
 if not p.can(c,branch_id=b,site_id=None):raise HTTPException(403,"Automation permission required")
@router.post("/bootstrap")
def boot(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 if not p.has_company_permission("company.manage"):raise HTTPException(403,"Company administration is required")
 q=db.scalar(select(Permission).where(Permission.code=="automation.manage"))
 if not q:db.add(Permission(code="automation.manage",module="automation",action="manage",description="Manage controlled automation"));db.flush()
 commit(db);return {"phase":35,"status":"ready"}
@router.get("")
def rows(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 allowed(p,"automation.manage");return [row_dict(x) for x in db.scalars(select(AutomationRule).where(AutomationRule.company_id==p.user.company_id)).all() if x.branch_id is None or p.can("automation.manage",branch_id=x.branch_id,site_id=None)]
@router.post("",status_code=201)
def add(x:RuleIn,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 allowed(p,"automation.manage",x.branch_id);r=AutomationRule(company_id=p.user.company_id,created_by=p.user.full_name,**x.model_dump());db.add(r);db.flush();db.add(AutomationAuditEvent(company_id=r.company_id,branch_id=r.branch_id,actor=p.user.full_name,action="automation.rule.created",detail={"name":r.name}));commit(db);return row_dict(r)
