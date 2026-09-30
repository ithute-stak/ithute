from __future__ import annotations

import secrets
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_platform_owner, require_tenant_permission
from app.api.v1.hosting_operations import _create_deployment, _last_healthy
from app.core.security import decrypt_secret, hash_token
from app.db.session import get_db
from app.models import (
    HostingBuild,
    HostingBuilderAgent,
    HostingProject,
    HostingSource,
    HostingSourceCredential,
    User,
)
from app.services.hosting_webhooks import queue_pending_webhook_rebuild

router = APIRouter(tags=["hosting-builds"])
APPROVED_IMAGE_PREFIX = "ghcr.io/ithute-stak/hosted-"


class BuilderTokenCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9._ -]+$")


class BuildCreate(BaseModel):
    source_id: UUID


class BuilderHeartbeat(BaseModel):
    version: str = Field(min_length=1, max_length=64)


class BuilderStatus(BaseModel):
    status: str = Field(pattern=r"^(building|succeeded|failed)$")
    image_ref: str | None = Field(default=None, max_length=500)
    image_digest: str | None = Field(default=None, max_length=80)
    source_commit: str | None = Field(default=None, max_length=64)
    message: str | None = Field(default=None, max_length=2000)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _build_out(row: HostingBuild) -> dict:
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "project_id": str(row.project_id),
        "source_id": str(row.source_id),
        "builder_agent_id": str(row.builder_agent_id) if row.builder_agent_id else None,
        "runtime": row.runtime,
        "status": row.status,
        "source_commit": row.source_commit,
        "image_ref": row.image_ref,
        "image_digest": row.image_digest,
        "failure_message": row.failure_message,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "claimed_at": row.claimed_at.isoformat() if row.claimed_at else None,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


def _builder_from_token(db: Session, token: str | None) -> HostingBuilderAgent:
    raw = (token or "").strip()
    if not raw.startswith("ith_build_"):
        raise HTTPException(status_code=401, detail="Hosting builder credential required")
    row = db.scalar(select(HostingBuilderAgent).where(HostingBuilderAgent.token_hash == hash_token(raw)))
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid hosting builder credential")
    if row.status != "active":
        raise HTTPException(status_code=403, detail="Hosting builder is disabled")
    return row


def _validate_build_image(image_ref: str | None, image_digest: str | None) -> tuple[str, str]:
    ref = (image_ref or "").strip().lower()
    digest = (image_digest or "").strip().lower()
    if not ref.startswith(APPROVED_IMAGE_PREFIX) or "@sha256:" not in ref:
        raise HTTPException(status_code=422, detail="Builder must publish a digest-pinned image in the approved Ithute hosting namespace")
    embedded = "sha256:" + ref.rsplit("@sha256:", 1)[1]
    if len(embedded) != 71 or embedded != digest or any(ch not in "0123456789abcdef" for ch in embedded[7:]):
        raise HTTPException(status_code=422, detail="Builder image digest does not match the immutable image reference")
    return ref, digest


@router.post("/platform/hosting/builders/token")
def create_or_rotate_builder_token(
    payload: BuilderTokenCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    name = payload.name.strip()
    raw = "ith_build_" + secrets.token_urlsafe(36)
    row = db.scalar(select(HostingBuilderAgent).where(HostingBuilderAgent.name == name))
    now = _now()
    if row is None:
        row = HostingBuilderAgent(
            name=name,
            token_hash=hash_token(raw),
            token_hint=raw[:20],
            status="active",
            rotated_at=now,
            rotated_by_user_id=current.id,
        )
        db.add(row)
    else:
        row.token_hash = hash_token(raw)
        row.token_hint = raw[:20]
        row.status = "active"
        row.agent_version = None
        row.last_seen_at = None
        row.rotated_at = now
        row.rotated_by_user_id = current.id
    db.commit()
    db.refresh(row)
    return {
        "id": str(row.id),
        "name": row.name,
        "token": raw,
        "token_hint": row.token_hint,
        "warning": "This builder credential is shown once. Store it only on the isolated build worker.",
    }


@router.get("/tenants/{tenant_id}/hosting/projects/{project_id}/builds")
def list_builds(
    tenant_id: UUID,
    project_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.read", db, current)
    project = db.scalar(select(HostingProject).where(HostingProject.id == project_id, HostingProject.tenant_id == tenant_id))
    if project is None:
        raise HTTPException(status_code=404, detail="Hosted project not found")
    rows = db.scalars(select(HostingBuild).where(HostingBuild.project_id == project.id).order_by(HostingBuild.created_at.desc()).limit(100)).all()
    return {"items": [_build_out(row) for row in rows]}


@router.post("/tenants/{tenant_id}/hosting/projects/{project_id}/builds", status_code=201)
def queue_build(
    tenant_id: UUID,
    project_id: UUID,
    payload: BuildCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    project = db.scalar(select(HostingProject).where(HostingProject.id == project_id, HostingProject.tenant_id == tenant_id).with_for_update())
    if project is None:
        raise HTTPException(status_code=404, detail="Hosted project not found")
    source = db.scalar(select(HostingSource).where(HostingSource.id == payload.source_id, HostingSource.project_id == project.id, HostingSource.tenant_id == tenant_id).with_for_update())
    if source is None:
        raise HTTPException(status_code=404, detail="Hosting source not found")
    if source.status != "ready":
        raise HTTPException(status_code=409, detail="Source must be verified and ready before it can be built")
    active = db.scalar(select(HostingBuild.id).where(HostingBuild.project_id == project.id, HostingBuild.status.in_(["queued", "claimed", "building"])))
    if active is not None:
        raise HTTPException(status_code=409, detail="This project already has a build in progress")
    row = HostingBuild(
        tenant_id=tenant_id,
        project_id=project.id,
        source_id=source.id,
        runtime=project.runtime,
        status="queued",
        requested_by_user_id=current.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _build_out(row)


@router.post("/hosting/builder/heartbeat")
def builder_heartbeat(
    payload: BuilderHeartbeat,
    x_ithute_builder: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    builder = _builder_from_token(db, x_ithute_builder)
    builder.agent_version = payload.version.strip()
    builder.last_seen_at = _now()
    db.commit()
    return {"ok": True, "builder_id": str(builder.id), "name": builder.name}


@router.post("/hosting/builder/builds/claim")
def claim_build(
    x_ithute_builder: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    builder = _builder_from_token(db, x_ithute_builder)
    builder.last_seen_at = _now()
    row = db.scalar(select(HostingBuild).where(HostingBuild.status == "queued").order_by(HostingBuild.created_at.asc()).with_for_update(skip_locked=True))
    if row is None:
        db.commit()
        return {"build": None}
    source = db.get(HostingSource, row.source_id)
    project = db.get(HostingProject, row.project_id)
    if source is None or project is None or source.status != "ready":
        row.status = "failed"
        row.failure_message = "Build source or project is unavailable"
        row.completed_at = _now()
        db.commit()
        return {"build": None}

    credential_payload = None
    if source.credential_id:
        credential = db.get(HostingSourceCredential, source.credential_id)
        if credential is None or credential.status != "active":
            row.status = "failed"
            row.failure_message = "Private source credential is unavailable"
            row.completed_at = _now()
            db.commit()
            return {"build": None}
        try:
            secret = decrypt_secret(credential.encrypted_secret)
        except ValueError as exc:
            row.status = "failed"
            row.failure_message = "Private source credential could not be decrypted"
            row.completed_at = _now()
            db.commit()
            raise HTTPException(status_code=500, detail="Source credential could not be prepared") from exc
        credential_payload = {
            "auth_type": credential.auth_type,
            "username": credential.username,
            "secret": secret,
        }

    row.status = "claimed"
    row.builder_agent_id = builder.id
    row.claimed_at = _now()
    source.status = "building"
    db.commit()
    return {
        "build": {
            "id": str(row.id),
            "runtime": row.runtime,
            "build_command": project.build_command,
            "start_command": project.start_command,
            "container_port": project.container_port,
            "image_name": f"ghcr.io/ithute-stak/hosted-{str(row.project_id).replace('-', '')}",
            "source": {
                "type": source.source_type,
                "repository_url": source.repository_url,
                "branch": source.repository_branch,
                "object_key": source.upload_object_key,
                "sha256": source.sha256,
                "size_bytes": source.size_bytes,
                "credential": credential_payload,
            },
        }
    }


@router.post("/hosting/builder/builds/{build_id}/status")
def report_build(
    build_id: UUID,
    payload: BuilderStatus,
    x_ithute_builder: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    builder = _builder_from_token(db, x_ithute_builder)
    builder.last_seen_at = _now()
    row = db.scalar(select(HostingBuild).where(HostingBuild.id == build_id, HostingBuild.builder_agent_id == builder.id).with_for_update())
    if row is None:
        raise HTTPException(status_code=404, detail="Build not found for this builder")
    source = db.get(HostingSource, row.source_id)
    project = db.get(HostingProject, row.project_id)
    if source is None or project is None:
        raise HTTPException(status_code=404, detail="Build source or project no longer exists")
    now = _now()

    if payload.status == "building":
        if row.status not in {"claimed", "building"}:
            raise HTTPException(status_code=409, detail="Build cannot enter building state from its current state")
        row.status = "building"
        row.started_at = row.started_at or now
        db.commit()
        db.refresh(row)
        return _build_out(row)

    if payload.status == "failed":
        if row.status not in {"claimed", "building"}:
            raise HTTPException(status_code=409, detail="Build cannot fail from its current state")
        row.status = "failed"
        row.failure_message = (payload.message or "Builder reported failure").strip()[:2000]
        row.completed_at = now
        source.status = "failed"
        source.failure_message = row.failure_message
        db.commit()
        db.refresh(row)
        return _build_out(row)

    if row.status not in {"claimed", "building"}:
        raise HTTPException(status_code=409, detail="Build cannot succeed from its current state")
    image_ref, digest = _validate_build_image(payload.image_ref, payload.image_digest)
    commit = (payload.source_commit or "").strip().lower() or None
    if commit and (len(commit) < 7 or len(commit) > 64 or any(ch not in "0123456789abcdef" for ch in commit)):
        raise HTTPException(status_code=422, detail="Builder source_commit must be a hexadecimal Git commit id")
    requester = db.get(User, row.requested_by_user_id)
    if requester is None:
        raise HTTPException(status_code=409, detail="Build requester no longer exists")
    previous = _last_healthy(db, project.id)
    deployment = _create_deployment(
        db,
        project=project,
        current=requester,
        image_ref=image_ref,
        image_digest=digest,
        source_commit=commit,
        previous_deployment_id=previous.id if previous else None,
    )
    row.status = "succeeded"
    row.image_ref = image_ref
    row.image_digest = digest
    row.source_commit = commit
    row.failure_message = None
    row.completed_at = now
    source.status = "ready"
    source.failure_message = None
    source.repository_commit = commit or source.repository_commit
    db.flush()
    pending_build = queue_pending_webhook_rebuild(db, source.id)
    db.commit()
    db.refresh(row)
    result = _build_out(row)
    result["deployment_id"] = str(deployment.id)
    result["deployment_status"] = deployment.status
    result["pending_webhook_build_id"] = str(pending_build.id) if pending_build else None
    return result
