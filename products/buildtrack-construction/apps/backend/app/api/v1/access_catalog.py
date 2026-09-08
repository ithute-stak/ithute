from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Branch, Role, Site
from app.security.access import Principal, require_permission

router = APIRouter(prefix="/access", tags=["Phase 2 - User Access & Security"])
SENSITIVE_ROLE_CODES = {"SYSTEM_ADMIN", "ACCESS_ADMIN"}


@router.get("/assignment-catalog")
def assignment_catalog(principal: Principal = Depends(require_permission("users.view", company_scope=True)), db: Session = Depends(get_db)) -> dict[str, list[dict[str, object]]]:
    roles = db.scalars(select(Role).where(Role.company_id == principal.user.company_id, Role.is_active.is_(True)).order_by(Role.name)).all()
    if not principal.has_company_permission("roles.manage"):
        roles = [role for role in roles if role.code not in SENSITIVE_ROLE_CODES]
    branches = db.scalars(select(Branch).where(Branch.company_id == principal.user.company_id, Branch.is_active.is_(True)).order_by(Branch.name)).all()
    sites = db.scalars(select(Site).where(Site.company_id == principal.user.company_id, Site.is_active.is_(True)).order_by(Site.name)).all()
    return {
        "roles": [{"id": row.id, "code": row.code, "name": row.name, "scope_level": row.scope_level, "description": row.description} for row in roles],
        "branches": [{"id": row.id, "code": row.code, "name": row.name, "district": row.district} for row in branches],
        "sites": [{"id": row.id, "branch_id": row.branch_id, "code": row.code, "name": row.name} for row in sites],
    }
