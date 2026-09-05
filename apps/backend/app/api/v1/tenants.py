from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_platform_owner
from app.db.session import get_db
from app.models import AuditLog, Tenant, User
from app.schemas.tenant import TenantCreate, TenantOut

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.get("", response_model=list[TenantOut])
def list_tenants(db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    rows = db.scalars(select(Tenant).order_by(Tenant.created_at.desc())).all()
    return [TenantOut(id=str(x.id), name=x.name, slug=x.slug, status=x.status.value) for x in rows]


@router.post("", response_model=TenantOut, status_code=201)
def create_tenant(payload: TenantCreate, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    if db.scalar(select(Tenant).where(Tenant.slug == payload.slug)):
        raise HTTPException(status_code=409, detail="Tenant slug already exists")
    tenant = Tenant(name=payload.name, slug=payload.slug)
    db.add(tenant)
    db.flush()
    db.add(AuditLog(actor_user_id=current.id, action="tenant.create", resource_type="tenant", resource_id=str(tenant.id)))
    db.commit()
    db.refresh(tenant)
    return TenantOut(id=str(tenant.id), name=tenant.name, slug=tenant.slug, status=tenant.status.value)
