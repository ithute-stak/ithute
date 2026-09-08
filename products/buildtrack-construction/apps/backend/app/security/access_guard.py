from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models import Permission, Role, RolePermission, User, UserRoleAssignment
from app.security.access import Principal, build_principal, current_principal

settings = get_settings()
PUBLIC_ACCESS_PATHS = {
    "/api/v1/access/setup-status",
    "/api/v1/access/bootstrap-admin",
    "/api/v1/access/login",
    "/api/v1/access/reset-password",
}
PASSWORD_CHANGE_ALLOWED_SUFFIXES = {
    "/access/me",
    "/access/context",
    "/access/logout",
    "/access/change-password",
    "/access/sessions",
}
SENSITIVE_ROLE_CODES = {"SYSTEM_ADMIN", "ACCESS_ADMIN"}
SITE_MANAGER_DEFAULT_PERMISSIONS = {
    "company.view",
    "branches.view",
    "sites.view",
    "departments.view",
    "cost_centres.view",
    "approvals.view",
    "approvals.request",
    "documents.view",
    "documents.upload",
    "tenders.view",
    "projects.view",
    "projects.manage",
    "people.view",
    "fleet.view",
    "procurement.view",
    "procurement.manage",
    "subcontracts.view",
    "commercial.view",
    "reports.view",
}


def _origin_allowed(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return True
    allowed = {settings.public_app_url.rstrip("/"), *(item.rstrip("/") for item in settings.cors_origin_list)}
    return origin.rstrip("/") in allowed


def _is_mutation(request: Request) -> bool:
    return request.method.upper() not in {"GET", "HEAD", "OPTIONS"}


def _last_system_admin(db: Session, company_id: int, user_id: int) -> bool:
    role = db.scalar(select(Role).where(Role.company_id == company_id, Role.code == "SYSTEM_ADMIN"))
    if not role:
        return False
    target_has_role = bool(db.scalar(select(func.count()).select_from(UserRoleAssignment).where(UserRoleAssignment.user_id == user_id, UserRoleAssignment.role_id == role.id)))
    if not target_has_role:
        return False
    admin_user_ids = select(UserRoleAssignment.user_id).where(UserRoleAssignment.role_id == role.id).subquery()
    active_admins = db.scalar(
        select(func.count()).select_from(User).where(
            User.company_id == company_id,
            User.is_active.is_(True),
            User.status != "suspended",
            User.id.in_(select(admin_user_ids.c.user_id)),
        )
    ) or 0
    return active_admins <= 1


def _ensure_site_manager_defaults(db: Session, company_id: int) -> bool:
    role = db.scalar(select(Role).where(Role.company_id == company_id, Role.code == "SITE_MANAGER"))
    if not role:
        return False
    permissions = db.scalars(select(Permission).where(Permission.code.in_(SITE_MANAGER_DEFAULT_PERMISSIONS))).all()
    existing = set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id == role.id)).all())
    changed = False
    for permission in permissions:
        if permission.id not in existing:
            db.add(RolePermission(role_id=role.id, permission_id=permission.id))
            changed = True
    if changed:
        db.commit()
    return changed


async def require_access_request_security(request: Request, db: Session = Depends(get_db)) -> Principal | None:
    if _is_mutation(request) and not _origin_allowed(request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Request origin is not allowed")

    if request.url.path in PUBLIC_ACCESS_PATHS or request.url.path.startswith("/api/v1/client-portal/public/") or request.url.path.startswith("/api/v1/vendor-portal/public/"):
        return None

    principal = current_principal(request, db)
    if _ensure_site_manager_defaults(db, principal.user.company_id):
        principal = build_principal(db, principal.user, principal.session)
        request.state.principal = principal

    path = request.url.path
    if principal.user.must_change_password and not any(path.endswith(suffix) for suffix in PASSWORD_CHANGE_ALLOWED_SUFFIXES):
        raise HTTPException(status_code=428, detail="Password change required before continuing")

    if request.method in {"POST", "PUT"} and (path.endswith("/access/users") or path.endswith("/assignments")):
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        assignments = payload.get("assignments", []) if isinstance(payload, dict) else []
        role_ids = {int(item.get("role_id")) for item in assignments if isinstance(item, dict) and item.get("role_id")}
        if role_ids:
            roles = db.scalars(select(Role).where(Role.id.in_(role_ids), Role.company_id == principal.user.company_id)).all()
            if any(role.code in SENSITIVE_ROLE_CODES for role in roles) and not principal.has_company_permission("roles.manage"):
                raise HTTPException(status_code=403, detail="Only a role administrator can assign System Administrator or Access Administrator")

        if path.endswith("/assignments"):
            parts = path.rstrip("/").split("/")
            try:
                target_user_id = int(parts[-2])
            except (ValueError, IndexError):
                target_user_id = 0
            if target_user_id and _last_system_admin(db, principal.user.company_id, target_user_id):
                system_role = db.scalar(select(Role).where(Role.company_id == principal.user.company_id, Role.code == "SYSTEM_ADMIN"))
                if system_role and system_role.id not in role_ids:
                    raise HTTPException(status_code=422, detail="The last active System Administrator cannot lose the System Administrator role")

    if request.method == "PATCH" and "/access/users/" in path:
        try:
            target_user_id = int(path.rstrip("/").split("/")[-1])
            payload = await request.json()
        except Exception:
            target_user_id = 0
            payload = {}
        deactivating = isinstance(payload, dict) and (payload.get("is_active") is False or payload.get("status") == "suspended")
        if deactivating:
            if target_user_id == principal.user.id:
                raise HTTPException(status_code=422, detail="You cannot suspend or deactivate your own account")
            if _last_system_admin(db, principal.user.company_id, target_user_id):
                raise HTTPException(status_code=422, detail="The last active System Administrator cannot be suspended or deactivated")

    return principal
