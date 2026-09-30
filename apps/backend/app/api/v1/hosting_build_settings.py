from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_tenant_permission
from app.db.session import get_db
from app.models import HostingProject, User

router = APIRouter(tags=["hosting-build-settings"])


class BuildSettingsUpdate(BaseModel):
    build_command: str | None = Field(default=None, max_length=1000)
    start_command: str | None = Field(default=None, max_length=1000)


def _clean_command(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if "\x00" in cleaned or "\r" in cleaned or "\n" in cleaned:
        raise HTTPException(status_code=422, detail="Build/start commands must be a single line without control characters")
    return cleaned


@router.get("/tenants/{tenant_id}/hosting/projects/{project_id}/build-settings")
def get_build_settings(
    tenant_id: UUID,
    project_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.read", db, current)
    project = db.scalar(select(HostingProject).where(HostingProject.id == project_id, HostingProject.tenant_id == tenant_id))
    if project is None:
        raise HTTPException(status_code=404, detail="Hosted project not found")
    return {
        "project_id": str(project.id),
        "runtime": project.runtime,
        "build_command": project.build_command,
        "start_command": project.start_command,
    }


@router.patch("/tenants/{tenant_id}/hosting/projects/{project_id}/build-settings")
def update_build_settings(
    tenant_id: UUID,
    project_id: UUID,
    payload: BuildSettingsUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    project = db.scalar(select(HostingProject).where(HostingProject.id == project_id, HostingProject.tenant_id == tenant_id).with_for_update())
    if project is None:
        raise HTTPException(status_code=404, detail="Hosted project not found")
    changes = payload.model_dump(exclude_unset=True)
    if "build_command" in changes:
        project.build_command = _clean_command(changes["build_command"])
    if "start_command" in changes:
        project.start_command = _clean_command(changes["start_command"])
    db.commit()
    db.refresh(project)
    return {
        "project_id": str(project.id),
        "runtime": project.runtime,
        "build_command": project.build_command,
        "start_command": project.start_command,
    }
