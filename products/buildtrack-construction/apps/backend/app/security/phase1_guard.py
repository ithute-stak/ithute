from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models import Company, User
from app.security.access import Principal, current_principal

settings = get_settings()

VIEW_PERMISSION_BY_SECTION = {
    "summary": "company.view",
    "company": "company.view",
    "branches": "branches.view",
    "sites": "sites.view",
    "departments": "departments.view",
    "cost-centres": "cost_centres.view",
    "permissions": "roles.view",
    "roles": "roles.view",
    "approval-workflows": "approvals.view",
    "approval-requests": "approvals.view",
    "documents": "documents.view",
    "master-data": "master_data.view",
    "settings": "company.view",
    "number-sequences": "company.view",
    "audit": "audit.view",
}

MANAGE_PERMISSION_BY_SECTION = {
    "company": "company.manage",
    "branches": "branches.manage",
    "sites": "sites.manage",
    "departments": "departments.manage",
    "cost-centres": "cost_centres.manage",
    "roles": "roles.manage",
    "approval-workflows": "approvals.manage",
    "approval-requests": "approvals.request",
    "documents": "documents.manage",
    "master-data": "master_data.manage",
    "settings": "company.manage",
    "number-sequences": "company.manage",
}


def _section(request: Request) -> str:
    path = request.url.path
    marker = "/foundation/"
    if marker not in path:
        return ""
    remainder = path.split(marker, 1)[1]
    return remainder.split("/", 1)[0]


def _origin_allowed(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return True
    allowed = {settings.public_app_url.rstrip("/"), *(item.rstrip("/") for item in settings.cors_origin_list)}
    return origin.rstrip("/") in allowed


def require_phase1_access(request: Request, db: Session = Depends(get_db)) -> Principal | None:
    if request.method not in {"GET", "HEAD", "OPTIONS"} and not _origin_allowed(request):
        raise HTTPException(status_code=403, detail="Request origin is not allowed")

    # Company bootstrap is the only public Phase 1 mutation and can only succeed once.
    if request.method == "POST" and request.url.path.endswith("/foundation/bootstrap"):
        if not db.scalar(select(func.count()).select_from(Company)):
            return None
        raise HTTPException(status_code=409, detail="BuildTrack company setup is already complete")

    if not db.scalar(select(func.count()).select_from(User)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Create the first Phase 2 administrator before using BuildTrack")

    principal = current_principal(request, db)
    if principal.user.must_change_password:
        raise HTTPException(status_code=428, detail="Password change required before using the operations workspace")

    section = _section(request)
    if not section:
        return principal

    if section == "approval-requests" and request.method == "POST" and request.url.path.endswith("/actions"):
        permission = "approvals.approve"
    elif section == "documents" and request.method == "POST" and "/versions" in request.url.path:
        permission = "documents.upload"
    elif request.method in {"GET", "HEAD", "OPTIONS"}:
        permission = VIEW_PERMISSION_BY_SECTION.get(section)
    else:
        permission = MANAGE_PERMISSION_BY_SECTION.get(section)

    if permission is None:
        if not any(grant.branch_id is None and grant.site_id is None for grant in principal.grants):
            raise HTTPException(status_code=403, detail="Company-level access is required")
        return principal

    if not principal.has_company_permission(permission):
        raise HTTPException(status_code=403, detail=f"Company-level permission required: {permission}")
    return principal


def require_document_download_access(request: Request, db: Session = Depends(get_db)) -> Principal:
    principal = current_principal(request, db)
    if principal.user.must_change_password:
        raise HTTPException(status_code=428, detail="Password change required before downloading controlled documents")
    if not principal.has_company_permission("documents.view"):
        raise HTTPException(status_code=403, detail="Company-level permission required: documents.view")
    return principal
