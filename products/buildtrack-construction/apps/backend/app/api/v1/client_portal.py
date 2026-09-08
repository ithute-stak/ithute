from __future__ import annotations
import hashlib,secrets
from datetime import date
from pathlib import Path
from fastapi import APIRouter,Depends,HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.v1.procurement import allow_self_approval,commit,ensure_document,issue_reference,row_dict,utcnow
from app.core.config import get_settings
from app.db.session import get_db
from app.models import ClientPortalAuditEvent,ClientSharePack,Document,DocumentVersion,NumberSequence,Permission,Project,Role,RolePermission
from app.security.access import Principal,current_principal
router=APIRouter(prefix="/client-portal",tags=["Phase 30 - Client Portal & Controlled External Sharing"]);settings=get_settings()
P={"clientportal.view":("client_portal","view","View controlled client share packs"),"clientportal.manage":("client_portal","manage","Prepare and revoke client share packs"),"clientportal.approve":("client_portal","approve","Independently publish client share packs")}
def any(p,c):
 if not p.has_permission_anywhere(c):raise HTTPException(status_code=403,detail=f"Permission required: {c}")
def scope(p,c,b,s):
 if not p.can(c,branch_id=b,site_id=s):raise HTTPException(status_code=403,detail=f"Permission required in this branch/site: {c}")
def audit(db,p,a,r,detail=None):db.add(ClientPortalAuditEvent(company_id=p.user.company_id,branch_id=r.branch_id,site_id=r.site_id,actor=p.user.full_name,action=a,entity_type=r.__tablename__,entity_id=str(r.id),detail=detail or {}))
def get(db,p,i,c):
 r=db.get(ClientSharePack,i)
 if not r or r.company_id!=p.user.company_id:raise HTTPException(status_code=404,detail="Client share pack not found")
 scope(p,c,r.branch_id,r.site_id);return r
def boot(db,cid):
 ps={}
 for c,(m,a,d) in P.items():
  r=db.scalar(select(Permission).where(Permission.code==c))
  if not r:r=Permission(code=c,module=m,action=a,description=d);db.add(r);db.flush()
  ps[c]=r
 roles={r.code:r for r in db.scalars(select(Role).where(Role.company_id==cid)).all()}
 for c,n,l in (("CLIENT_PORTAL_MANAGER","Client Portal Manager","company"),("CLIENT_PORTAL_OFFICER","Client Portal Officer","branch"),("CLIENT_PORTAL_REVIEWER","Client Portal Reviewer","company")):
  if c not in roles:roles[c]=Role(company_id=cid,code=c,name=n,scope_level=l,description=f"Phase 30 {n}",is_system=True,is_active=True);db.add(roles[c]);db.flush()
 for rc,cs in {"SYSTEM_ADMIN":set(P),"HQ_EXECUTIVE":set(P),"BRANCH_MANAGER":set(P),"PROJECT_MANAGER":{"clientportal.view","clientportal.manage"},"AUDITOR":{"clientportal.view"},"CLIENT_PORTAL_MANAGER":set(P),"CLIENT_PORTAL_OFFICER":{"clientportal.view","clientportal.manage"},"CLIENT_PORTAL_REVIEWER":{"clientportal.view","clientportal.approve"}}.items():
  r=roles.get(rc)
  if r:
   old=set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id==r.id)).all())
   for c in cs:
    if ps[c].id not in old:db.add(RolePermission(role_id=r.id,permission_id=ps[c].id));old.add(ps[c].id)
 if not db.scalar(select(NumberSequence).where(NumberSequence.company_id==cid,NumberSequence.code=="CLIENT_SHARE_PACK")):db.add(NumberSequence(company_id=cid,code="CLIENT_SHARE_PACK",name="Client Share Pack",prefix="CSP",next_number=1,padding=5,reset_period="yearly"))
class In(BaseModel):model_config=ConfigDict(extra="forbid");project_id:int;title:str=Field(min_length=2,max_length=300);client_name:str=Field(min_length=2,max_length=240);message:str|None=None;document_id:int=Field(gt=0);expiry_date:date
@router.post("/bootstrap")
def bootstrap(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 if not p.has_company_permission("company.manage") and not p.has_company_permission("clientportal.manage"):raise HTTPException(status_code=403,detail="Company administration is required")
 boot(db,p.user.company_id);commit(db);return {"phase":30,"status":"ready"}
@router.get("/catalog")
def catalog(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 any(p,"clientportal.view");return {"projects":[row_dict(r) for r in db.scalars(select(Project).where(Project.company_id==p.user.company_id,Project.status.in_(("ready","active")))).all() if p.can("clientportal.view",branch_id=r.branch_id,site_id=r.primary_site_id)],"documents":[row_dict(r) for r in db.scalars(select(Document).where(Document.company_id==p.user.company_id,Document.status=="active",Document.confidentiality=="public").order_by(Document.created_at.desc())).all() if p.can("clientportal.view",branch_id=r.branch_id,site_id=r.site_id)]}
@router.get("")
def rows(db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 any(p,"clientportal.view");return [row_dict(r) for r in db.scalars(select(ClientSharePack).where(ClientSharePack.company_id==p.user.company_id).order_by(ClientSharePack.created_at.desc())).all() if p.can("clientportal.view",branch_id=r.branch_id,site_id=r.site_id)]
@router.post("",status_code=201)
def create(x:In,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 pr=db.get(Project,x.project_id)
 if not pr or pr.company_id!=p.user.company_id:raise HTTPException(status_code=422,detail="Client share project is invalid")
 scope(p,"clientportal.manage",pr.branch_id,pr.primary_site_id);doc=ensure_document(db,p.user.company_id,x.document_id)
 if doc.confidentiality!="public" or doc.branch_id!=pr.branch_id or doc.site_id!=pr.primary_site_id:raise HTTPException(status_code=422,detail="Only an active public controlled document from this project site may be shared")
 if x.expiry_date<date.today():raise HTTPException(status_code=422,detail="Client link expiry date must be today or later")
 r=ClientSharePack(company_id=p.user.company_id,project_id=pr.id,branch_id=pr.branch_id,site_id=pr.primary_site_id,pack_number=issue_reference(db,p.user.company_id,"CLIENT_SHARE_PACK","CSP"),title=x.title.strip(),client_name=x.client_name.strip(),message=x.message,document_id=x.document_id,expiry_date=x.expiry_date,prepared_by=p.user.full_name);db.add(r);db.flush();audit(db,p,"clientportal.pack.created",r);commit(db);return row_dict(r)
@router.post("/{i}/submit")
def submit(i:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=get(db,p,i,"clientportal.manage")
 if r.status not in {"draft","rejected"}:raise HTTPException(status_code=409,detail="Only a draft client share pack can be submitted")
 r.status,r.submitted_at="submitted",utcnow();audit(db,p,"clientportal.pack.submitted",r);commit(db);return row_dict(r)
@router.post("/{i}/publish")
def publish(i:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=get(db,p,i,"clientportal.approve")
 if r.status!="submitted" or r.expiry_date<date.today():raise HTTPException(status_code=409,detail="Share pack is not eligible for publication")
 if r.prepared_by==p.user.full_name and not allow_self_approval(db,r.company_id):raise HTTPException(status_code=422,detail="Self-publication is disabled by company policy")
 token=secrets.token_urlsafe(32);r.status,r.token_hash,r.published_by,r.published_at="published",hashlib.sha256(token.encode()).hexdigest(),p.user.full_name,utcnow();audit(db,p,"clientportal.pack.published",r);commit(db);return {**row_dict(r),"access_token":token,"public_url":f"/api/v1/client-portal/public/{token}"}
@router.post("/{i}/revoke")
def revoke(i:int,db:Session=Depends(get_db),p:Principal=Depends(current_principal)):
 r=get(db,p,i,"clientportal.manage")
 if r.status!="published":raise HTTPException(status_code=409,detail="Only published client share packs can be revoked")
 r.status,r.token_hash,r.revoked_by,r.revoked_at="revoked",None,p.user.full_name,utcnow();audit(db,p,"clientportal.pack.revoked",r);commit(db);return row_dict(r)
def public_pack(db,token):
 r=db.scalar(select(ClientSharePack).where(ClientSharePack.token_hash==hashlib.sha256(token.encode()).hexdigest()));doc=db.get(Document,r.document_id) if r else None
 if not r or r.status!="published" or r.expiry_date<date.today() or not doc or doc.status!="active" or doc.confidentiality!="public":raise HTTPException(status_code=404,detail="Client share link is unavailable")
 return r
@router.get("/public/{token}")
def public_view(token:str,db:Session=Depends(get_db)):
 r=public_pack(db,token);doc=db.get(Document,r.document_id);db.add(ClientPortalAuditEvent(company_id=r.company_id,branch_id=r.branch_id,site_id=r.site_id,actor="external",action="clientportal.pack.viewed",entity_type=r.__tablename__,entity_id=str(r.id),detail={}));commit(db);return {"title":r.title,"client_name":r.client_name,"message":r.message,"expiry_date":r.expiry_date.isoformat(),"document_number":doc.document_number if doc else None,"document_title":doc.title if doc else None,"download_url":f"/api/v1/client-portal/public/{token}/document"}
@router.get("/public/{token}/document")
def public_document(token:str,db:Session=Depends(get_db)):
 r=public_pack(db,token);v=db.scalar(select(DocumentVersion).where(DocumentVersion.document_id==r.document_id).order_by(DocumentVersion.version_number.desc()));db.add(ClientPortalAuditEvent(company_id=r.company_id,branch_id=r.branch_id,site_id=r.site_id,actor="external",action="clientportal.pack.document_downloaded",entity_type=r.__tablename__,entity_id=str(r.id),detail={}));commit(db)
 if not v:raise HTTPException(status_code=404,detail="Shared document has no uploaded version")
 root=Path(settings.media_root).resolve();path=(root/v.stored_path).resolve()
 try:path.relative_to(root)
 except ValueError as e:raise HTTPException(status_code=400,detail="Invalid document storage path") from e
 if not path.is_file():raise HTTPException(status_code=404,detail="Shared document file is missing")
 return FileResponse(path,media_type=v.content_type or "application/octet-stream",filename=v.original_filename)
