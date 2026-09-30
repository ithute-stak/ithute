from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_tenant_permission
from app.db.session import get_db
from app.models import User
from app.services.hosting_metering import hosting_resource_meter

router = APIRouter(tags=["hosting-metering"])


@router.get("/tenants/{tenant_id}/hosting/resource-meter")
def get_hosting_resource_meter(
    tenant_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.read", db, current)
    return hosting_resource_meter(db, tenant_id)
