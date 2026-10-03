from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_tenant_permission
from app.api.v1.domains import _domain_or_404
from app.db.session import get_db
from app.models import User
from app.services.domain_mail_health import domain_mail_health

router = APIRouter(prefix="/tenants/{tenant_id}/domains/{domain_id}/mail-health", tags=["domain-mail-health"])


@router.get("")
def get_domain_mail_health(
    tenant_id: UUID,
    domain_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "dns.read", db, current)
    domain = _domain_or_404(db, tenant_id, domain_id)
    return domain_mail_health(db, domain)
