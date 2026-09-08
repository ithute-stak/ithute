from __future__ import annotations
import hashlib,secrets
from datetime import date
from pathlib import Path
from typing import Literal
from fastapi import APIRouter,Depends,File,Form,HTTPException,UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from app.api.v1.foundation import safe_filename
from app.api.v1.procurement import allow_self_approval,commit,ensure_scope,issue_reference,row_dict,utcnow
from app.core.config import get_settings
from app.db.session import get_db
from app.models import Branch,NumberSequence,Permission,Role,RolePermission,Site,Subcontractor,Supplier,VendorPortalAuditEvent,VendorPortalEvidence,VendorPortalRequest
from app.security.access import Principal,current_principal
router=APIRouter(prefix="/vendor-portal",tags=["Phase 31 - Supplier & Subcontractor Evidence Portal"]);settings=get_settings()
P={"vendorportal.view":("vendor_portal","view","View controlled vendor evidence requests"),"vendorportal.manage":("vendor_portal","manage","Prepare and revoke vendor evidence requests"),"vendorportal.verify":("vendor_portal","verify","Independently verify vendor evidence")}
def any(p,c):
 if not p.has_permission_anywhere(c):raise HTTPException(status_code=403,detail=f"Permission required: {c}")
def scope(p,c,b,s):
 if not p.can(c,branch_id=b,site_id=s):raise HTTPException(status_code=403,detail=f"Permission required in this branch/site: {c}")
def audit(db,p,a,r,detail=None):db.add(VendorPortalAuditEvent(company_id=r.company_id,branch_id=r.branch_id,site_id=r.site_id,actor=p.user.full_name,action=a,entity_type=r.__tablename__,entity_id=str(r.id),detail=detail or {}))
def get(db,p,i,c):
 r=db.get(VendorPortalRequest,i)
 if not r or r.company_id!=p.user.company_id:raise HTTPException(status_code=404,detail="Vendor evidence request not found")
 scope(p,c,r.branch_id,r.site_id);return r
def boot(db,cid):
 ps={}
 for c,(m,a,d) in P.items():
  r=db.scalar(select(Permission).where(Permission.code==c))
  if not r:r=Permission(code=c,module=m,action=a,description=d);db.add(r);db.flush()
  ps[c]=r
 roles={r.code:r for r in db.scalars(select(Role).where(Role.company_id==cid)).all()}
 for c,n,l in (("VENDOR_PORTAL_MANAGER","Vendor Portal Manager","company"),("VENDOR_PORTAL_OFFICER","Vendor Portal Officer","branch"),("VENDOR_PORTAL_REVIEWER","Vendor Portal Reviewer","company")):
  if c not in roles:roles[c]=Role(company_id=cid,code=c,name=n,scope_level=l,description=f"Phase 31 {n}",is_system=True,is_active=True);db.add(roles[c]);db.flush()
 for rc,cs in {"SYSTEM_ADMIN":set(P),"HQ_EXECUTIVE":set(P),"BRANCH_MANAGER":set(P),"PROCUREMENT_MANAGER":{"vendorportal.view","vendorportal.manage"},"PROCUREMENT_OFFICER":{"vendorportal.view","vendorportal.manage"},"SUBCONTRACT_MANAGER":{"vendorportal.view","vendorportal.manage"},"AUDITOR":{"vendorportal.view"},"VENDOR_PORTAL_MANAGER":set(P),"VENDOR_PORTAL_OFFICER":{"vendorportal.view","vendorportal.manage"},"VENDOR_PORTAL_REVIEWER":{"vendorportal.view","vendorportal.verify"}}.items():
  r=roles.get(rc)
  if r:
   old=set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id==r.id)).all())
   for c in cs:
    if ps[c].id not in old:db.add(RolePermission(role_id=r.id,permission_id=ps[c].id));old.add(ps[c].id)
 if not db.scalar(select(NumberSequence).where(NumberSequence.company_id==cid,NumberSequence.code=="VENDOR_EVIDENCE_REQUEST")):db.add(NumberSequence(company_id=cid,code="VENDOR_EVIDENCE_REQUEST",name="Vendor Evidence Request",prefix="VER",next_number=1,padding=5,reset_period="yearly"))
class In(BaseModel):
 model_config=ConfigDict(extra="forbid");branch_id:int;site_id:int|None=None;target_type:Literal["supplier","subcontractor"];vendor_id:int;request_type:Literal["tax_clearance","insurance","registration","bank_details","safety","other"];title:str=Field(min_length=2,max_length=300);instructions:str|None=Field(default=None,max_length=4000);due_date:date
@router.post("/bootstrap")
def bootstrap(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 if not p.has_company_permission("company.manage") and not p.has_company_permission("vendorportal.manage"):raise HTTPException(status_code=403,detail="Company administration is required")
 boot(db,p.user.company_id);commit(db);return {"phase":31,"status":"ready"}
@router.get("/catalog")
def catalog(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 any(p,"vendorportal.view");return {"branches":[row_dict(r) for r in db.scalars(select(Branch).where(Branch.company_id==p.user.company_id)).all() if p.can("vendorportal.view",branch_id=r.id,site_id=None)],"sites":[row_dict(r) for r in db.scalars(select(Site).where(Site.company_id==p.user.company_id)).all() if p.can("vendorportal.view",branch_id=r.branch_id,site_id=r.id)],"suppliers":[row_dict(r) for r in db.scalars(select(Supplier).where(Supplier.company_id==p.user.company_id,Supplier.status=="active").order_by(Supplier.name)).all()],"subcontractors":[row_dict(r) for r in db.scalars(select(Subcontractor).where(Subcontractor.company_id==p.user.company_id,Subcontractor.status=="active").order_by(Subcontractor.legal_name)).all()]}
@router.get("")
def rows(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 any(p,"vendorportal.view");out=[]
 for r in db.scalars(select(VendorPortalRequest).where(VendorPortalRequest.company_id==p.user.company_id).order_by(VendorPortalRequest.created_at.desc())).all():
  if p.can("vendorportal.view",branch_id=r.branch_id,site_id=r.site_id):out.append({**row_dict(r),"evidence_count":db.scalar(select(func.count()).select_from(VendorPortalEvidence).where(VendorPortalEvidence.request_id==r.id)) or 0})
 return out
@router.get("/{i}")
def detail(i:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=get(db,p,i,"vendorportal.view");return {**row_dict(r),"evidence":[row_dict(x) for x in db.scalars(select(VendorPortalEvidence).where(VendorPortalEvidence.request_id==r.id).order_by(VendorPortalEvidence.uploaded_at.desc())).all()]}
@router.post("",status_code=201)
def create(x:In,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 ensure_scope(db,p.user.company_id,x.branch_id,x.site_id);scope(p,"vendorportal.manage",x.branch_id,x.site_id)
 v=db.get(Supplier,x.vendor_id) if x.target_type=="supplier" else db.get(Subcontractor,x.vendor_id)
 if not v or v.company_id!=p.user.company_id or v.status!="active":raise HTTPException(status_code=422,detail="Selected supplier or subcontractor is not active")
 if x.due_date<date.today():raise HTTPException(status_code=422,detail="Evidence due date must be today or later")
 name=v.name if x.target_type=="supplier" else v.legal_name;r=VendorPortalRequest(company_id=p.user.company_id,branch_id=x.branch_id,site_id=x.site_id,target_type=x.target_type,vendor_id=x.vendor_id,vendor_name=name,request_number=issue_reference(db,p.user.company_id,"VENDOR_EVIDENCE_REQUEST","VER"),request_type=x.request_type,title=x.title.strip(),instructions=x.instructions,due_date=x.due_date,prepared_by=p.user.full_name);db.add(r);db.flush();audit(db,p,"vendorportal.request.created",r);commit(db);return row_dict(r)
@router.post("/{i}/submit")
def submit(i:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=get(db,p,i,"vendorportal.manage")
 if r.status not in {"draft","rejected"}:raise HTTPException(status_code=409,detail="Only a draft or rejected request can be submitted")
 r.status,r.submitted_at="submitted",utcnow();audit(db,p,"vendorportal.request.submitted",r);commit(db);return row_dict(r)
@router.post("/{i}/publish")
def publish(i:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=get(db,p,i,"vendorportal.verify")
 if r.status!="submitted" or r.due_date<date.today():raise HTTPException(status_code=409,detail="Vendor request is not eligible for publication")
 if r.prepared_by==p.user.full_name and not allow_self_approval(db,r.company_id):raise HTTPException(status_code=422,detail="Self-publication is disabled by company policy")
 token=secrets.token_urlsafe(32);r.status,r.token_hash,r.published_by,r.published_at="published",hashlib.sha256(token.encode()).hexdigest(),p.user.full_name,utcnow();audit(db,p,"vendorportal.request.published",r);commit(db);return {**row_dict(r),"access_token":token,"public_url":f"/vendor-submissions/{token}"}
@router.post("/{i}/revoke")
def revoke(i:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=get(db,p,i,"vendorportal.manage")
 if r.status!="published":raise HTTPException(status_code=409,detail="Only a published vendor request can be revoked")
 r.status,r.token_hash,r.revoked_by,r.revoked_at="revoked",None,p.user.full_name,utcnow();audit(db,p,"vendorportal.request.revoked",r);commit(db);return row_dict(r)
@router.post("/{i}/verify")
def verify(i:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=get(db,p,i,"vendorportal.verify")
 if r.status!="received" or not db.scalar(select(VendorPortalEvidence.id).where(VendorPortalEvidence.request_id==r.id)):raise HTTPException(status_code=409,detail="Only a received request with evidence can be verified")
 r.status,r.verified_by,r.verified_at="verified",p.user.full_name,utcnow();audit(db,p,"vendorportal.request.verified",r);commit(db);return row_dict(r)
def public_request(db,token):
 r=db.scalar(select(VendorPortalRequest).where(VendorPortalRequest.token_hash==hashlib.sha256(token.encode()).hexdigest()))
 if not r or r.status!="published" or r.due_date<date.today():raise HTTPException(status_code=404,detail="Vendor evidence link is unavailable")
 return r
@router.get("/public/{token}")
def public_view(token:str,db:Session=Depends(get_db)):
 r=public_request(db,token);db.add(VendorPortalAuditEvent(company_id=r.company_id,branch_id=r.branch_id,site_id=r.site_id,actor="external",action="vendorportal.request.viewed",entity_type=r.__tablename__,entity_id=str(r.id),detail={}));commit(db);return {"request_number":r.request_number,"vendor_name":r.vendor_name,"request_type":r.request_type,"title":r.title,"instructions":r.instructions,"due_date":r.due_date.isoformat(),"upload_url":f"/api/v1/vendor-portal/public/{token}/respond"}
@router.post("/public/{token}/respond",status_code=201)
async def respond(token:str,contact_name:str=Form(...),contact_email:str=Form(...),note:str|None=Form(default=None),file:UploadFile=File(...),db:Session=Depends(get_db)):
 r=public_request(db,token);content=await file.read()
 if not content:raise HTTPException(status_code=422,detail="Uploaded evidence is empty")
 if len(content)>25*1024*1024:raise HTTPException(status_code=413,detail="Evidence exceeds the 25 MB upload limit")
 filename=safe_filename(file.filename or "vendor-evidence.bin");digest=hashlib.sha256(content).hexdigest();root=Path(settings.media_root).resolve();target_dir=root/f"company-{r.company_id}"/"vendor-portal"/str(r.id);target_dir.mkdir(parents=True,exist_ok=True);target=target_dir/f"{digest[:16]}-{filename}";target.write_bytes(content)
 e=VendorPortalEvidence(company_id=r.company_id,request_id=r.id,contact_name=contact_name.strip(),contact_email=contact_email.strip(),note=note,original_filename=filename,stored_path=str(target.relative_to(root)),content_type=file.content_type,file_size=len(content),sha256=digest);db.add(e);r.status,r.received_at="received",utcnow();db.add(VendorPortalAuditEvent(company_id=r.company_id,branch_id=r.branch_id,site_id=r.site_id,actor="external",action="vendorportal.request.evidence_received",entity_type=r.__tablename__,entity_id=str(r.id),detail={"sha256":digest,"file_size":len(content)}));commit(db);return {"status":"received","request_number":r.request_number}
@router.get("/{i}/evidence/{e}/download")
def download(i:int,e:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=get(db,p,i,"vendorportal.view");x=db.get(VendorPortalEvidence,e)
 if not x or x.request_id!=r.id:raise HTTPException(status_code=404,detail="Vendor evidence not found")
 root=Path(settings.media_root).resolve();path=(root/x.stored_path).resolve()
 try:path.relative_to(root)
 except ValueError as z:raise HTTPException(status_code=400,detail="Invalid vendor evidence path") from z
 if not path.is_file():raise HTTPException(status_code=404,detail="Vendor evidence file is missing")
 return FileResponse(path,media_type=x.content_type or "application/octet-stream",filename=x.original_filename)
