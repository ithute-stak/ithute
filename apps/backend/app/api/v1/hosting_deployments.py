from __future__ import annotations

import hashlib
import os
import re
import secrets
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_platform_owner, require_tenant_permission
from app.db.session import get_db
from app.models import AuditLog, HostingDeployment, HostingNode, HostingProject, User

router = APIRouter(tags=["hosting-deployments"])

ACTIVE_DEPLOYMENT_STATES = {"queued", "claimed", "deploying"}
AGENT_REPORT_STATES = {"deploying", "healthy", "failed"}
IMAGE_DIGEST_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]*(?:/[a-z0-9._-]+)+@sha256:[0-9a-f]{64}$")
SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{7,64}$")
TRUSTED_IMAGE_PREFIX = os.getenv("HOSTING_IMAGE_PREFIX", "ghcr.io/ithute-stak/hosted-").strip().lower()


class DeploymentCreate(BaseModel):
    image_ref: str = Field(min_length=80, max_length=500)
    source_sha: str | None = Field(default=None, min_length=7, max_length=64)


class AgentClaim(BaseModel):
    agent_version: str = Field(min_length=1, max_length=64)


class AgentReport(BaseModel):
    status: str = Field(pattern=r"^(deploying|healthy|failed)$")
    message: str | None = Field(default=None, max_length=4000)
    error: str | None = Field(default=None, max_length=4000)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(
    db: Session,
    current: User,
    action: str,
    resource_id: str,
    *,
    tenant_id: UUID | None = None,
    metadata: dict | None = None,
) -> None:
    import json

    db.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=current.id,
            action=action,
            resource_type="hosting_deployment",
            resource_id=resource_id,
            metadata_json=json.dumps(metadata or {}, sort_keys=True),
        )
    )


def _image_ref(value: str) -> str:
    image = value.strip().lower()
    if not IMAGE_DIGEST_RE.fullmatch(image):
        raise HTTPException(
            status_code=422,
            detail="Hosting images must be immutable OCI references pinned with @sha256:<64 hex characters>",
        )
    if not TRUSTED_IMAGE_PREFIX or not image.startswith(TRUSTED_IMAGE_PREFIX):
        raise HTTPException(
            status_code=422,
            detail="Hosting image is outside the approved Ithute registry namespace",
        )
    return image


def _source_sha(value: str | None) -> str | None:
    if value is None:
        return None
    sha = value.strip().lower()
    if not SOURCE_SHA_RE.fullmatch(sha):
        raise HTTPException(status_code=422, detail="Source SHA must contain 7 to 64 hexadecimal characters")
    return sha


def _deployment_out(row: HostingDeployment) -> dict:
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "project_id": str(row.project_id),
        "node_id": str(row.node_id) if row.node_id else None,
        "image_ref": row.image_ref,
        "source_sha": row.source_sha,
        "status": row.status,
        "rollback_of_deployment_id": str(row.rollback_of_deployment_id) if row.rollback_of_deployment_id else None,
        "agent_message": row.agent_message,
        "error": row.error,
        "requested_at": row.requested_at.isoformat() if row.requested_at else None,
        "claimed_at": row.claimed_at.isoformat() if row.claimed_at else None,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "health_checked_at": row.health_checked_at.isoformat() if row.health_checked_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }


def _project_for_update(db: Session, tenant_id: UUID, project_id: UUID) -> HostingProject:
    project = db.scalar(
        select(HostingProject)
        .where(HostingProject.id == project_id, HostingProject.tenant_id == tenant_id)
        .with_for_update()
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Hosted project not found")
    return project


def _ensure_deployable(db: Session, project: HostingProject) -> HostingNode:
    if project.status == "suspended":
        raise HTTPException(status_code=409, detail="Suspended projects cannot be deployed")
    if project.node_id is None:
        raise HTTPException(status_code=409, detail="Hosted project is not allocated to a hosting node")
    node = db.get(HostingNode, project.node_id)
    if node is None or node.status != "active":
        raise HTTPException(status_code=409, detail="The assigned hosting node is not active")
    pending = db.scalar(
        select(HostingDeployment.id).where(
            HostingDeployment.project_id == project.id,
            HostingDeployment.status.in_(ACTIVE_DEPLOYMENT_STATES),
        )
    )
    if pending is not None:
        raise HTTPException(status_code=409, detail="This project already has an active deployment attempt")
    return node


def _authenticate_agent(node: HostingNode, token: str | None) -> None:
    if not node.agent_token_hash:
        raise HTTPException(status_code=503, detail="Hosting node agent has not been provisioned")
    if not token:
        raise HTTPException(status_code=401, detail="Missing hosting agent token")
    candidate = hashlib.sha256(token.encode("utf-8")).hexdigest()
    if not secrets.compare_digest(candidate, node.agent_token_hash):
        raise HTTPException(status_code=401, detail="Invalid hosting agent token")


def _touch_agent(node: HostingNode, version: str | None = None) -> None:
    node.agent_last_seen_at = _now()
    if version:
        node.agent_version = version.strip()


@router.post("/platform/hosting/nodes/{node_id}/agent-token")
def rotate_hosting_agent_token(
    node_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    node = db.get(HostingNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Hosting node not found")
    token = secrets.token_urlsafe(48)
    node.agent_token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    node.agent_last_seen_at = None
    node.agent_version = None
    _audit(db, current, "hosting.agent.token.rotate", str(node.id), metadata={"node_id": str(node.id)})
    db.commit()
    return {
        "node_id": str(node.id),
        "token": token,
        "notice": "This token is shown once. Store it only on the hosting node and rotate it if exposed.",
    }


@router.get("/tenants/{tenant_id}/hosting/projects/{project_id}/deployments")
def list_project_deployments(
    tenant_id: UUID,
    project_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.read", db, current)
    project = db.scalar(select(HostingProject.id).where(HostingProject.id == project_id, HostingProject.tenant_id == tenant_id))
    if project is None:
        raise HTTPException(status_code=404, detail="Hosted project not found")
    rows = db.scalars(
        select(HostingDeployment)
        .where(HostingDeployment.project_id == project_id, HostingDeployment.tenant_id == tenant_id)
        .order_by(HostingDeployment.requested_at.desc())
    ).all()
    return {"items": [_deployment_out(row) for row in rows]}


@router.post("/tenants/{tenant_id}/hosting/projects/{project_id}/deployments", status_code=202)
def request_project_deployment(
    tenant_id: UUID,
    project_id: UUID,
    payload: DeploymentCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    project = _project_for_update(db, tenant_id, project_id)
    node = _ensure_deployable(db, project)
    deployment = HostingDeployment(
        tenant_id=tenant_id,
        project_id=project.id,
        node_id=node.id,
        image_ref=_image_ref(payload.image_ref),
        source_sha=_source_sha(payload.source_sha),
        status="queued",
        requested_by_user_id=current.id,
    )
    db.add(deployment)
    db.flush()
    project.status = "deploying"
    _audit(
        db,
        current,
        "hosting.deployment.queue",
        str(deployment.id),
        tenant_id=tenant_id,
        metadata={"project_id": str(project.id), "node_id": str(node.id), "image_ref": deployment.image_ref},
    )
    db.commit()
    db.refresh(deployment)
    return _deployment_out(deployment)


@router.post(
    "/tenants/{tenant_id}/hosting/projects/{project_id}/deployments/{deployment_id}/rollback",
    status_code=202,
)
def rollback_project_deployment(
    tenant_id: UUID,
    project_id: UUID,
    deployment_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    project = _project_for_update(db, tenant_id, project_id)
    node = _ensure_deployable(db, project)
    target = db.scalar(
        select(HostingDeployment).where(
            HostingDeployment.id == deployment_id,
            HostingDeployment.project_id == project.id,
            HostingDeployment.tenant_id == tenant_id,
            HostingDeployment.status == "healthy",
        )
    )
    if target is None:
        raise HTTPException(status_code=404, detail="Healthy deployment target not found")
    deployment = HostingDeployment(
        tenant_id=tenant_id,
        project_id=project.id,
        node_id=node.id,
        image_ref=target.image_ref,
        source_sha=target.source_sha,
        status="queued",
        rollback_of_deployment_id=target.id,
        requested_by_user_id=current.id,
    )
    db.add(deployment)
    db.flush()
    project.status = "deploying"
    _audit(
        db,
        current,
        "hosting.deployment.rollback.queue",
        str(deployment.id),
        tenant_id=tenant_id,
        metadata={"project_id": str(project.id), "rollback_target": str(target.id)},
    )
    db.commit()
    db.refresh(deployment)
    return _deployment_out(deployment)


@router.post("/hosting-agent/nodes/{node_id}/claim")
def claim_hosting_deployment(
    node_id: UUID,
    payload: AgentClaim,
    x_ithute_agent_token: str | None = Header(default=None, alias="X-Ithute-Agent-Token"),
    db: Session = Depends(get_db),
):
    node = db.scalar(select(HostingNode).where(HostingNode.id == node_id).with_for_update())
    if node is None:
        raise HTTPException(status_code=404, detail="Hosting node not found")
    _authenticate_agent(node, x_ithute_agent_token)
    if node.status not in {"active", "draining"}:
        raise HTTPException(status_code=409, detail="Hosting node is offline")
    _touch_agent(node, payload.agent_version)

    deployment = db.scalar(
        select(HostingDeployment)
        .where(HostingDeployment.node_id == node.id, HostingDeployment.status == "queued")
        .order_by(HostingDeployment.requested_at.asc())
        .with_for_update(skip_locked=True)
    )
    if deployment is None:
        db.commit()
        return {"deployment": None}

    project = db.get(HostingProject, deployment.project_id)
    if project is None or project.status == "suspended":
        deployment.status = "failed"
        deployment.error = "Project is unavailable or suspended"
        deployment.finished_at = _now()
        db.commit()
        return {"deployment": None}

    deployment.status = "claimed"
    deployment.claimed_at = _now()
    db.commit()
    return {
        "deployment": {
            **_deployment_out(deployment),
            "runtime": {
                "project_slug": project.slug,
                "container_name": f"ithute-hosted-{project.id.hex}",
                "container_port": project.container_port,
                "health_path": project.health_path,
                "hostname": project.hostname,
                "storage_mb": project.storage_mb,
                "memory_mb": project.memory_mb,
                "cpu_millicores": project.cpu_millicores,
                "pid_limit": project.pid_limit,
                "security": {
                    "run_as_root": False,
                    "privileged": False,
                    "no_new_privileges": True,
                    "cap_drop": ["ALL"],
                    "read_only_rootfs": True,
                    "public_host_ports": False,
                    "persistent_mount": "/data",
                    "tmpfs": ["/tmp"],
                },
            },
        }
    }


@router.post("/hosting-agent/nodes/{node_id}/deployments/{deployment_id}/report")
def report_hosting_deployment(
    node_id: UUID,
    deployment_id: UUID,
    payload: AgentReport,
    x_ithute_agent_token: str | None = Header(default=None, alias="X-Ithute-Agent-Token"),
    db: Session = Depends(get_db),
):
    node = db.scalar(select(HostingNode).where(HostingNode.id == node_id).with_for_update())
    if node is None:
        raise HTTPException(status_code=404, detail="Hosting node not found")
    _authenticate_agent(node, x_ithute_agent_token)
    _touch_agent(node)

    deployment = db.scalar(
        select(HostingDeployment)
        .where(HostingDeployment.id == deployment_id, HostingDeployment.node_id == node.id)
        .with_for_update()
    )
    if deployment is None:
        raise HTTPException(status_code=404, detail="Hosting deployment not found for this node")
    project = db.get(HostingProject, deployment.project_id)
    if project is None:
        raise HTTPException(status_code=409, detail="Hosted project no longer exists")

    now = _now()
    if payload.status == "deploying":
        if deployment.status not in {"claimed", "deploying"}:
            raise HTTPException(status_code=409, detail="Deployment cannot enter deploying state from its current state")
        deployment.status = "deploying"
        deployment.started_at = deployment.started_at or now
    elif payload.status == "healthy":
        if deployment.status not in {"claimed", "deploying", "healthy"}:
            raise HTTPException(status_code=409, detail="Deployment cannot become healthy from its current state")
        deployment.status = "healthy"
        deployment.started_at = deployment.started_at or now
        deployment.health_checked_at = now
        deployment.finished_at = now
        deployment.error = None
        project.image_ref = deployment.image_ref
        project.status = "running"
    elif payload.status == "failed":
        if deployment.status not in {"claimed", "deploying", "failed"}:
            raise HTTPException(status_code=409, detail="Deployment cannot fail from its current state")
        deployment.status = "failed"
        deployment.finished_at = now
        deployment.error = payload.error or payload.message or "Hosting agent reported deployment failure"
        project.status = "running" if project.image_ref else "failed"
    else:
        raise HTTPException(status_code=422, detail="Unsupported deployment report state")

    deployment.agent_message = payload.message
    if payload.error and payload.status != "healthy":
        deployment.error = payload.error
    db.commit()
    db.refresh(deployment)
    return _deployment_out(deployment)
