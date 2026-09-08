from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.site_operations import row_dict
from app.db.session import get_db
from app.models import ApprovalRequest, SiteDailyReport, SiteIncident, SiteOperationsActivation, SiteQualityCheck
from app.security.access import Principal, current_principal

router = APIRouter(prefix="/site-ops", tags=["Phase 7 - Site Operations Control"])


def require_anywhere(principal: Principal, permission: str) -> None:
    if not principal.has_permission_anywhere(permission):
        raise HTTPException(status_code=403, detail=f"Permission required: {permission}")


@router.get("/control/queue")
def control_queue(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_anywhere(principal, "siteops.view")
    reports = [row for row in db.scalars(select(SiteDailyReport).where(SiteDailyReport.company_id == principal.user.company_id, SiteDailyReport.status == "submitted").order_by(SiteDailyReport.submitted_at)).all() if principal.can("siteops.view", branch_id=row.branch_id, site_id=row.site_id)]
    report_queue = []
    for row in reports:
        request = db.get(ApprovalRequest, row.approval_request_id) if row.approval_request_id else None
        report_queue.append({**row_dict(row), "approval": row_dict(request) if request else None})
    incidents = [row for row in db.scalars(select(SiteIncident).where(SiteIncident.company_id == principal.user.company_id, SiteIncident.status != "closed").order_by(SiteIncident.severity.desc(), SiteIncident.occurred_at.desc())).all() if principal.can("siteops.view", branch_id=row.branch_id, site_id=row.site_id)]
    quality = [row for row in db.scalars(select(SiteQualityCheck).where(SiteQualityCheck.company_id == principal.user.company_id, SiteQualityCheck.status.not_in(["accepted", "closed"])).order_by(SiteQualityCheck.inspected_at.desc())).all() if principal.can("siteops.view", branch_id=row.branch_id, site_id=row.site_id)]
    activations = [row for row in db.scalars(select(SiteOperationsActivation).where(SiteOperationsActivation.company_id == principal.user.company_id).order_by(SiteOperationsActivation.id.desc())).all() if principal.can("siteops.view", branch_id=row.branch_id, site_id=row.site_id)]
    return {
        "daily_report_approvals": report_queue,
        "open_incidents": [row_dict(row) for row in incidents],
        "open_quality_actions": [row_dict(row) for row in quality],
        "activations": [row_dict(row) for row in activations],
    }


@router.get("/incidents")
def list_incidents(db: Session = Depends(get_db), principal: Principal = Depends(current_principal), status_filter: str | None = Query(default=None, alias="status"), limit: int = Query(default=300, ge=1, le=1000)) -> list[dict[str, Any]]:
    require_anywhere(principal, "siteops.view")
    query = select(SiteIncident).where(SiteIncident.company_id == principal.user.company_id)
    if status_filter: query = query.where(SiteIncident.status == status_filter)
    rows = db.scalars(query.order_by(SiteIncident.occurred_at.desc()).limit(limit)).all()
    return [row_dict(row) for row in rows if principal.can("siteops.view", branch_id=row.branch_id, site_id=row.site_id)]


@router.get("/quality")
def list_quality(db: Session = Depends(get_db), principal: Principal = Depends(current_principal), status_filter: str | None = Query(default=None, alias="status"), limit: int = Query(default=300, ge=1, le=1000)) -> list[dict[str, Any]]:
    require_anywhere(principal, "siteops.view")
    query = select(SiteQualityCheck).where(SiteQualityCheck.company_id == principal.user.company_id)
    if status_filter: query = query.where(SiteQualityCheck.status == status_filter)
    rows = db.scalars(query.order_by(SiteQualityCheck.inspected_at.desc()).limit(limit)).all()
    return [row_dict(row) for row in rows if principal.can("siteops.view", branch_id=row.branch_id, site_id=row.site_id)]
