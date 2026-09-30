from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_tenant_permission
from app.api.v1.hosting_builds import _builder_from_token
from app.db.session import get_db
from app.models import HostingBuild, HostingBuildLog, HostingProject, User

router = APIRouter(tags=["hosting-build-logs"])
MAX_LOG_ENTRIES_PER_BUILD = 500
MAX_LOG_BATCH = 25
MAX_LOG_MESSAGE_CHARS = 2000


class BuildLogEntry(BaseModel):
    stage: str = Field(min_length=2, max_length=48, pattern=r"^[a-z][a-z0-9_-]*$")
    level: str = Field(default="info", pattern=r"^(info|warning|error)$")
    message: str = Field(min_length=1, max_length=MAX_LOG_MESSAGE_CHARS)


class BuildLogBatch(BaseModel):
    entries: list[BuildLogEntry] = Field(min_length=1, max_length=MAX_LOG_BATCH)


def _log_out(row: HostingBuildLog) -> dict:
    return {
        "sequence": row.sequence,
        "stage": row.stage,
        "level": row.level,
        "message": row.message,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/tenants/{tenant_id}/hosting/projects/{project_id}/builds/{build_id}/logs")
def list_build_logs(
    tenant_id: UUID,
    project_id: UUID,
    build_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.read", db, current)
    project = db.scalar(select(HostingProject.id).where(HostingProject.id == project_id, HostingProject.tenant_id == tenant_id))
    if project is None:
        raise HTTPException(status_code=404, detail="Hosted project not found")
    build = db.scalar(select(HostingBuild.id).where(HostingBuild.id == build_id, HostingBuild.project_id == project_id, HostingBuild.tenant_id == tenant_id))
    if build is None:
        raise HTTPException(status_code=404, detail="Hosting build not found")
    rows = db.scalars(
        select(HostingBuildLog)
        .where(HostingBuildLog.build_id == build_id)
        .order_by(HostingBuildLog.sequence.asc())
        .limit(MAX_LOG_ENTRIES_PER_BUILD)
    ).all()
    return {"items": [_log_out(row) for row in rows], "limit": MAX_LOG_ENTRIES_PER_BUILD}


@router.post("/hosting/builder/builds/{build_id}/logs", status_code=201)
def append_build_logs(
    build_id: UUID,
    payload: BuildLogBatch,
    x_ithute_builder: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    builder = _builder_from_token(db, x_ithute_builder)
    build = db.scalar(
        select(HostingBuild)
        .where(HostingBuild.id == build_id, HostingBuild.builder_agent_id == builder.id)
        .with_for_update()
    )
    if build is None:
        raise HTTPException(status_code=404, detail="Build not found for this builder")
    if build.status not in {"claimed", "building"}:
        raise HTTPException(status_code=409, detail="Build logs can be appended only while a build is active")

    current_count = int(db.scalar(select(func.count(HostingBuildLog.id)).where(HostingBuildLog.build_id == build_id)) or 0)
    if current_count + len(payload.entries) > MAX_LOG_ENTRIES_PER_BUILD:
        raise HTTPException(status_code=409, detail="Build log entry limit reached")
    last_sequence = int(db.scalar(select(func.coalesce(func.max(HostingBuildLog.sequence), 0)).where(HostingBuildLog.build_id == build_id)) or 0)

    created: list[HostingBuildLog] = []
    for offset, entry in enumerate(payload.entries, start=1):
        message = entry.message.replace("\x00", "").strip()
        if not message:
            continue
        row = HostingBuildLog(
            build_id=build_id,
            sequence=last_sequence + offset,
            stage=entry.stage,
            level=entry.level,
            message=message[:MAX_LOG_MESSAGE_CHARS],
        )
        db.add(row)
        created.append(row)
    if not created:
        raise HTTPException(status_code=422, detail="Build log batch contained no usable messages")
    db.commit()
    for row in created:
        db.refresh(row)
    return {"items": [_log_out(row) for row in created]}
