import json
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_platform_owner, require_tenant_permission
from app.db.session import get_db
from app.models import AuditLog, User
from app.schemas.audit import AuditOut

router = APIRouter(tags=["audit"])


def _out(row: AuditLog) -> AuditOut:
    metadata = None
    if row.metadata_json:
        try:
            metadata = json.loads(row.metadata_json)
        except json.JSONDecodeError:
            metadata = {"raw": row.metadata_json}
    return AuditOut(
        id=str(row.id),
        tenant_id=str(row.tenant_id) if row.tenant_id else None,
        actor_user_id=str(row.actor_user_id) if row.actor_user_id else None,
        action=row.action,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        metadata=metadata,
        created_at=row.created_at.isoformat(),
    )


@router.get("/tenants/{tenant_id}/audit", response_model=list[AuditOut])
def tenant_audit(
    tenant_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "audit.read", db, current)
    rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    ).all()
    return [_out(row) for row in rows]


@router.get("/audit/platform", response_model=list[AuditOut])
def platform_audit(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).all()
    return [_out(row) for row in rows]
