from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.projects import project_policy
from app.api.v1.projects_safe import strict_readiness_state
from app.db.session import get_db
from app.models import Project
from app.security.access import Principal, current_principal

router = APIRouter(prefix="/projects", tags=["Phase 6 - Project Reporting"])


@router.get("/dashboard/alerts")
def project_alerts_safe(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    if not principal.has_permission_anywhere("projects.view"):
        return []
    policy = project_policy(db, principal.user.company_id)
    warning = date.today() + timedelta(days=int(policy.get("mobilisation_warning_days", 7)))
    result: list[dict[str, Any]] = []
    projects = [
        row
        for row in db.scalars(
            select(Project).where(Project.company_id == principal.user.company_id, Project.status != "ready")
        ).all()
        if principal.can("projects.view", branch_id=row.branch_id, site_id=row.primary_site_id)
    ]
    for project in projects:
        if project.mobilisation_date <= warning:
            result.append({
                "project_id": project.id,
                "project_number": project.project_number,
                "severity": "critical" if project.mobilisation_date < date.today() else "warning",
                "type": "mobilisation_date",
                "message": f"Mobilisation date {project.mobilisation_date.isoformat()}",
            })
        state = strict_readiness_state(db, project)
        for blocker in state["blockers"]:
            severity = "critical" if "critical" in blocker.lower() or "serviceable" in blocker.lower() else "warning"
            result.append({
                "project_id": project.id,
                "project_number": project.project_number,
                "severity": severity,
                "type": "readiness",
                "message": blocker,
            })
    return result
