from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.projects import row_dict
from app.db.session import get_db
from app.models import Project, ProjectReadinessSnapshot
from app.security.access import Principal, current_principal

router = APIRouter(prefix="/projects", tags=["Phase 6 - Site Operations Handoff"])


@router.get("/{project_id:int}/site-operations-handoff")
def site_operations_handoff_active_safe(project_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    project = db.get(Project, project_id)
    if not project or project.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Project not found")
    if not principal.can("projects.view", branch_id=project.branch_id, site_id=project.primary_site_id):
        raise HTTPException(status_code=403, detail="Permission required in this project/site: projects.view")
    if project.status not in {"ready", "active"} or project.readiness_status != "ready":
        raise HTTPException(status_code=409, detail="Project mobilisation must be approved before Phase 7 Site Operations handoff")
    snapshot = db.scalar(select(ProjectReadinessSnapshot).where(ProjectReadinessSnapshot.project_id == project.id).order_by(ProjectReadinessSnapshot.version.desc()).limit(1))
    if not snapshot:
        raise HTTPException(status_code=409, detail="Approved project readiness snapshot is missing")
    return {
        "handoff_version": 1,
        "source_phase": 6,
        "target_phase": 7,
        "project_id": project.id,
        "project_number": project.project_number,
        "project_status": project.status,
        "readiness_snapshot_id": snapshot.id,
        "snapshot": snapshot.snapshot,
        "ready": True,
    }
