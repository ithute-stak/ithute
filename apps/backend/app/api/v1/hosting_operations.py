from __future__ import annotations

import ipaddress
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_platform_owner, require_tenant_permission
from app.core.security import decrypt_secret, encrypt_secret, hash_token
from app.db.session import get_db
from app.services.resource_manager import node_resource_snapshot, release_reservation, reserve_capacity
from app.services.postgres_replica_telemetry import persist_postgres_replica_telemetry
from app.services.postgres_rpo_policy import persist_primary_rpo_telemetry
from app.models import (
    AuditLog,
    HostingDeployment,
    HostingEnvironmentVariable,
    HostingFailoverAttempt,
    HostingNode,
    HostingNodeAgent,
    HostingNodeBootstrap,
    HostingNodeHealthState,
    HostingProject,
    HostingResourceReservation,
    InfrastructureServer,
    InfrastructureServerAgent,
    InfrastructureWireGuardPeer,
    User,
)

router = APIRouter(tags=["hosting-operations"])

_ENV_KEY_RE = re.compile(r"^[A-Z_][A-Z0-9_]{0,127}$")
_DIGEST_REF_RE = re.compile(r"^.+@sha256:([0-9a-f]{64})$")
_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")
_APPROVED_IMAGE_PREFIX = "ghcr.io/ithute-stak/hosted-"
ACTIVE_DEPLOYMENT_STATUSES = {"queued", "claimed", "running"}


class EnvironmentValue(BaseModel):
    value: str = Field(min_length=1, max_length=16384)
    is_secret: bool = True


class DeploymentCreate(BaseModel):
    image_ref: str = Field(min_length=20, max_length=500)
    source_commit: str | None = Field(default=None, max_length=64)


class AgentHeartbeat(BaseModel):
    version: str = Field(min_length=1, max_length=64)
    origin_bind_ip: str | None = Field(default=None, max_length=64)
    capabilities: dict[str, object] = Field(default_factory=dict)


class HostingNodeBootstrapCreate(BaseModel):
    managed_private_network: bool = True
    origin_bind_ip: str | None = Field(default=None, max_length=64)
    edge_origin_cidrs: str = Field(default="", max_length=1000)
    backup_remote: str | None = Field(default=None, max_length=1000)


class HostingNodeAutomationUpdate(BaseModel):
    enabled: bool


class HostingResourceReservationCreate(BaseModel):
    cpu_millicores: int = Field(default=0, ge=0)
    memory_mb: int = Field(default=0, ge=0)
    storage_mb: int = Field(default=0, ge=0)
    expires_minutes: int = Field(default=15, ge=1, le=1440)
    purpose: str = Field(default="placement", min_length=1, max_length=80)
    project_id: UUID | None = None


class AgentStatusUpdate(BaseModel):
    status: str = Field(pattern=r"^(running|healthy|failed)$")
    message: str | None = Field(default=None, max_length=2000)
    origin_url: str | None = Field(default=None, max_length=1000)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _private_ipv4(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Origin bind IP must be a literal private IPv4 address") from exc
    if not isinstance(address, ipaddress.IPv4Address) or not address.is_private or address.is_loopback or address.is_link_local or address.is_unspecified or address.is_multicast:
        raise HTTPException(status_code=422, detail="Origin bind IP must be a private/VPN IPv4 address")
    return str(address)


def _cidr_list(value: str) -> str:
    rows = [item.strip() for item in value.split(",") if item.strip()]
    for item in rows:
        try:
            network = ipaddress.ip_network(item, strict=False)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid edge origin CIDR: {item}") from exc
        if not network.is_private:
            raise HTTPException(status_code=422, detail="Edge origin CIDRs must be private/VPN networks")
    return ",".join(rows)


def _audit(
    db: Session,
    current: User | None,
    action: str,
    resource_type: str,
    resource_id: str,
    *,
    tenant_id: UUID | None = None,
    metadata: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=current.id if current else None,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata_json=json.dumps(metadata or {}, sort_keys=True),
        )
    )


def _project(db: Session, tenant_id: UUID, project_id: UUID, *, lock: bool = False) -> HostingProject:
    query = select(HostingProject).where(HostingProject.id == project_id, HostingProject.tenant_id == tenant_id)
    if lock:
        query = query.with_for_update()
    project = db.scalar(query)
    if project is None:
        raise HTTPException(status_code=404, detail="Hosted project not found")
    return project


def _deployment_out(row: HostingDeployment) -> dict:
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "project_id": str(row.project_id),
        "node_id": str(row.node_id) if row.node_id else None,
        "previous_deployment_id": str(row.previous_deployment_id) if row.previous_deployment_id else None,
        "release_number": row.release_number,
        "image_ref": row.image_ref,
        "image_digest": row.image_digest,
        "source_commit": row.source_commit,
        "reset_data_volume": row.reset_data_volume,
        "runtime_manifest_version": row.runtime_manifest_version,
        "status": row.status,
        "failure_message": row.failure_message,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "claimed_at": row.claimed_at.isoformat() if row.claimed_at else None,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "last_health_at": row.last_health_at.isoformat() if row.last_health_at else None,
        "origin_url": row.origin_url,
        "origin_reported_at": row.origin_reported_at.isoformat() if row.origin_reported_at else None,
    }


def _validate_image_ref(value: str) -> tuple[str, str]:
    image_ref = value.strip()
    match = _DIGEST_REF_RE.fullmatch(image_ref)
    if not match:
        raise HTTPException(
            status_code=422,
            detail="Deployments require an immutable image reference ending in @sha256:<64 hex characters>",
        )
    if not image_ref.lower().startswith(_APPROVED_IMAGE_PREFIX):
        raise HTTPException(
            status_code=422,
            detail="Deployments require an image from the approved Ithute hosting namespace",
        )
    return image_ref, f"sha256:{match.group(1)}"


def _validate_source_commit(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    commit = value.strip()
    if not _COMMIT_RE.fullmatch(commit):
        raise HTTPException(status_code=422, detail="source_commit must be a hexadecimal Git commit id")
    return commit.lower()


def _active_deployment(db: Session, project_id: UUID) -> HostingDeployment | None:
    return db.scalar(
        select(HostingDeployment)
        .where(HostingDeployment.project_id == project_id, HostingDeployment.status.in_(ACTIVE_DEPLOYMENT_STATUSES))
        .order_by(HostingDeployment.created_at.desc())
    )


def _last_healthy(db: Session, project_id: UUID) -> HostingDeployment | None:
    return db.scalar(
        select(HostingDeployment)
        .where(HostingDeployment.project_id == project_id, HostingDeployment.status == "healthy")
        .order_by(HostingDeployment.release_number.desc())
    )


def _next_release_number(db: Session, project_id: UUID) -> int:
    current = db.scalar(select(func.coalesce(func.max(HostingDeployment.release_number), 0)).where(HostingDeployment.project_id == project_id)) or 0
    return int(current) + 1


def _create_deployment(
    db: Session,
    *,
    project: HostingProject,
    current: User,
    image_ref: str,
    image_digest: str,
    source_commit: str | None,
    previous_deployment_id: UUID | None,
) -> HostingDeployment:
    if project.node_id is None:
        raise HTTPException(status_code=409, detail="Project is not assigned to a hosting node")
    if project.status == "suspended":
        raise HTTPException(status_code=409, detail="Resume the project before requesting a deployment")
    if _active_deployment(db, project.id) is not None:
        raise HTTPException(status_code=409, detail="This project already has a deployment in progress")
    if db.get(HostingNodeAgent, project.node_id) is None:
        raise HTTPException(status_code=409, detail="The assigned hosting node does not have an agent credential yet")

    deployment = HostingDeployment(
        tenant_id=project.tenant_id,
        project_id=project.id,
        node_id=project.node_id,
        previous_deployment_id=previous_deployment_id,
        release_number=_next_release_number(db, project.id),
        image_ref=image_ref,
        image_digest=image_digest,
        source_commit=source_commit,
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
        "hosting_deployment",
        str(deployment.id),
        tenant_id=project.tenant_id,
        metadata={"project_id": str(project.id), "release_number": deployment.release_number, "image_digest": image_digest},
    )
    return deployment


def _agent_from_token(db: Session, token: str | None) -> tuple[HostingNodeAgent, HostingNode]:
    raw = (token or "").strip()
    if not raw or not raw.startswith("ith_host_"):
        raise HTTPException(status_code=401, detail="Hosting node agent credential required")
    agent = db.scalar(select(HostingNodeAgent).where(HostingNodeAgent.token_hash == hash_token(raw)))
    if agent is None:
        raise HTTPException(status_code=401, detail="Invalid hosting node agent credential")
    node = db.get(HostingNode, agent.node_id)
    if node is None or node.status == "offline":
        raise HTTPException(status_code=403, detail="Hosting node is unavailable")
    return agent, node


@router.get("/platform/hosting/nodes/{node_id}/resources")
def hosting_node_resources(
    node_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    node = db.get(HostingNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Hosting node not found")
    snapshot = node_resource_snapshot(db, node)
    db.commit()
    return snapshot


@router.post("/platform/hosting/nodes/{node_id}/resource-reservations", status_code=201)
def create_resource_reservation(
    node_id: UUID,
    payload: HostingResourceReservationCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    project = None
    if payload.project_id is not None:
        project = db.get(HostingProject, payload.project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Hosted project not found")
        if project.node_id is not None:
            raise HTTPException(status_code=409, detail="Project is already assigned and its resources are counted as allocated")

    try:
        reservation = reserve_capacity(
            db,
            node_id=node_id,
            cpu_millicores=payload.cpu_millicores,
            memory_mb=payload.memory_mb,
            storage_mb=payload.storage_mb,
            expires_at=_now() + timedelta(minutes=payload.expires_minutes),
            created_by_user_id=current.id,
            project_id=payload.project_id,
            purpose=payload.purpose,
        )
    except ValueError as exc:
        message = str(exc)
        if message == "hosting node not found":
            raise HTTPException(status_code=404, detail="Hosting node not found") from exc
        raise HTTPException(status_code=409, detail=message) from exc

    _audit(
        db,
        current,
        "hosting.resource_reservation.create",
        "hosting_resource_reservation",
        str(reservation.id),
        metadata={
            "node_id": str(node_id),
            "project_id": str(payload.project_id) if payload.project_id else None,
            "cpu_millicores": reservation.cpu_millicores,
            "memory_mb": reservation.memory_mb,
            "storage_mb": reservation.storage_mb,
            "expires_at": reservation.expires_at.isoformat(),
            "purpose": reservation.purpose,
        },
    )
    db.commit()
    return {
        "id": str(reservation.id),
        "node_id": str(reservation.node_id),
        "project_id": str(reservation.project_id) if reservation.project_id else None,
        "purpose": reservation.purpose,
        "cpu_millicores": reservation.cpu_millicores,
        "memory_mb": reservation.memory_mb,
        "storage_mb": reservation.storage_mb,
        "status": reservation.status,
        "expires_at": reservation.expires_at.isoformat(),
    }


@router.post("/platform/hosting/resource-reservations/{reservation_id}/release")
def release_resource_reservation(
    reservation_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    reservation = release_reservation(db, reservation_id)
    if reservation is None:
        raise HTTPException(status_code=404, detail="Resource reservation not found")
    _audit(
        db,
        current,
        "hosting.resource_reservation.release",
        "hosting_resource_reservation",
        str(reservation.id),
        metadata={"node_id": str(reservation.node_id), "status": reservation.status},
    )
    db.commit()
    return {
        "id": str(reservation.id),
        "status": reservation.status,
        "released_at": reservation.released_at.isoformat() if reservation.released_at else None,
    }


@router.post("/platform/hosting/nodes/{node_id}/bootstrap")
def create_node_bootstrap(
    node_id: UUID,
    payload: HostingNodeBootstrapCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    node = db.get(HostingNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Hosting node not found")

    if payload.managed_private_network:
        origin_bind_ip = None
        edge_cidrs = ""
    else:
        origin_bind_ip = _private_ipv4(payload.origin_bind_ip)
        edge_cidrs = _cidr_list(payload.edge_origin_cidrs)
        if not origin_bind_ip or not edge_cidrs:
            raise HTTPException(status_code=422, detail="Manual private networking requires both an origin IP and edge CIDRs")

    raw = "ith_boot_" + secrets.token_urlsafe(36)
    now = _now()
    db.query(HostingNodeBootstrap).filter(
        HostingNodeBootstrap.node_id == node.id,
        HostingNodeBootstrap.used_at.is_(None),
    ).delete(synchronize_session=False)
    bootstrap = HostingNodeBootstrap(
        node_id=node.id,
        token_hash=hash_token(raw),
        token_hint=raw[:18],
        managed_private_network=payload.managed_private_network,
        origin_bind_ip=origin_bind_ip,
        edge_origin_cidrs=edge_cidrs,
        backup_remote=payload.backup_remote.strip() if payload.backup_remote else None,
        expires_at=now + timedelta(minutes=15),
        created_by_user_id=current.id,
    )
    db.add(bootstrap)
    state = ensure_health_state(db, node, enable=True, reset=True)
    state.last_transition = "bootstrap_started"
    state.last_transition_at = now
    node.status = "draining"
    node.accepts_new_projects = False
    _audit(db, current, "hosting.node_bootstrap.create", "hosting_node", str(node.id), metadata={
        "managed_private_network": payload.managed_private_network,
        "origin_bind_ip": origin_bind_ip,
        "edge_origin_cidrs": edge_cidrs,
        "expires_minutes": 15,
    })
    db.commit()
    return {
        "node_id": str(node.id),
        "token": raw,
        "token_hint": raw[:18],
        "expires_at": bootstrap.expires_at.isoformat(),
        "script_path": f"/hosting/bootstrap/{node.id}/script",
        "warning": "This bootstrap token is valid for 15 minutes and can be exchanged only once.",
    }


@router.get("/hosting/bootstrap/{node_id}/script", response_class=PlainTextResponse)
def exchange_node_bootstrap(
    node_id: UUID,
    x_ithute_node_bootstrap: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    raw = (x_ithute_node_bootstrap or "").strip()
    if not raw.startswith("ith_boot_"):
        raise HTTPException(status_code=401, detail="Bootstrap credential required")
    bootstrap = db.scalar(
        select(HostingNodeBootstrap)
        .where(
            HostingNodeBootstrap.node_id == node_id,
            HostingNodeBootstrap.token_hash == hash_token(raw),
        )
        .with_for_update()
    )
    now = _now()
    if bootstrap is None:
        raise HTTPException(status_code=401, detail="Invalid bootstrap credential")
    if bootstrap.used_at is not None:
        raise HTTPException(status_code=410, detail="Bootstrap credential has already been used")
    expires = bootstrap.expires_at if bootstrap.expires_at.tzinfo else bootstrap.expires_at.replace(tzinfo=timezone.utc)
    if expires <= now:
        raise HTTPException(status_code=410, detail="Bootstrap credential has expired")

    node = db.get(HostingNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Hosting node not found")

    hosting_raw = "ith_host_" + secrets.token_urlsafe(36)
    agent = db.get(HostingNodeAgent, node.id)
    if agent is None:
        agent = HostingNodeAgent(
            node_id=node.id,
            token_hash=hash_token(hosting_raw),
            token_hint=hosting_raw[:18],
            rotated_at=now,
            rotated_by_user_id=bootstrap.created_by_user_id,
        )
        db.add(agent)
    else:
        agent.token_hash = hash_token(hosting_raw)
        agent.token_hint = hosting_raw[:18]
        agent.rotated_at = now
        agent.rotated_by_user_id = bootstrap.created_by_user_id
        agent.last_seen_at = None
        agent.agent_version = None
        agent.origin_bind_ip = None

    server = db.scalar(select(InfrastructureServer).where(InfrastructureServer.hosting_node_id == node.id))
    if server is None:
        server = db.scalar(select(InfrastructureServer).where(func.lower(InfrastructureServer.hostname) == node.hostname.lower()))
        if server is not None and server.hosting_node_id not in {None, node.id}:
            raise HTTPException(status_code=409, detail="Infrastructure server hostname is already linked to another hosting node")
    if server is None:
        server = InfrastructureServer(
            name=node.name,
            hostname=node.hostname,
            public_ip=node.public_ip,
            region="lesotho",
            roles_json=json.dumps(["application", "database", "storage"]),
            status="active",
            hosting_node_id=node.id,
            created_by_user_id=bootstrap.created_by_user_id,
        )
        db.add(server)
        db.flush()
    else:
        server.hosting_node_id = node.id
        roles = set(json.loads(server.roles_json or "[]"))
        roles.update({"application", "database", "storage"})
        server.roles_json = json.dumps(sorted(roles))
        if not server.public_ip and node.public_ip:
            server.public_ip = node.public_ip

    server_raw = "ith_srv_" + secrets.token_urlsafe(36)
    server_agent = db.get(InfrastructureServerAgent, server.id)
    if server_agent is None:
        server_agent = InfrastructureServerAgent(
            server_id=server.id,
            token_hash=hash_token(server_raw),
            token_hint=server_raw[:18],
            rotated_at=now,
            rotated_by_user_id=bootstrap.created_by_user_id,
        )
        db.add(server_agent)
    else:
        server_agent.token_hash = hash_token(server_raw)
        server_agent.token_hint = server_raw[:18]
        server_agent.rotated_at = now
        server_agent.rotated_by_user_id = bootstrap.created_by_user_id
        server_agent.last_seen_at = None
        server_agent.agent_version = None
        server_agent.telemetry_json = "{}"
        server_agent.capabilities_json = "{}"

    bootstrap.used_at = now
    state = ensure_health_state(db, node, enable=True, reset=True)
    state.last_transition = "bootstrap_exchanged"
    state.last_transition_at = now
    node.status = "draining"
    node.accepts_new_projects = False
    script = render_hosting_node_bootstrap(
        api_base_url="https://ithute.co.ls",
        hosting_token=hosting_raw,
        server_token=server_raw,
        origin_bind_ip=bootstrap.origin_bind_ip,
        edge_origin_cidrs=bootstrap.edge_origin_cidrs,
        backup_remote=bootstrap.backup_remote,
        managed_private_network=bootstrap.managed_private_network,
    )
    db.commit()
    return PlainTextResponse(script, media_type="text/x-shellscript", headers={"Cache-Control": "no-store"})


@router.get("/platform/hosting/nodes/{node_id}/onboarding")
def node_onboarding_status(
    node_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    node = db.get(HostingNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Hosting node not found")
    health = node_health_snapshot(db, node)
    return {
        "node_id": str(node.id),
        "ready": health["healthy"],
        "active": node.status == "active" and node.accepts_new_projects,
        "checks": health["checks"],
        "origin_bind_ip": db.get(HostingNodeAgent, node.id).origin_bind_ip if db.get(HostingNodeAgent, node.id) else None,
        "managed_network_ip": health["managed_network_ip"],
        "managed_network_last_handshake_at": health["last_handshake_at"],
        "automation_enabled": health["automation_enabled"],
        "health_status": health["health_status"],
        "healthy_since": health["healthy_since"],
        "unhealthy_since": health["unhealthy_since"],
        "last_transition": health["last_transition"],
        "last_transition_at": health["last_transition_at"],
        "last_reason": health["last_reason"],
        "thresholds": health["thresholds"],
    }


@router.get("/platform/hosting/nodes/{node_id}/health")
def hosting_node_health(
    node_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    node = db.get(HostingNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Hosting node not found")
    return node_health_snapshot(db, node)


@router.post("/platform/hosting/nodes/{node_id}/automation")
def set_hosting_node_automation(
    node_id: UUID,
    payload: HostingNodeAutomationUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    node = db.get(HostingNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Hosting node not found")
    state = ensure_health_state(db, node, enable=payload.enabled, reset=payload.enabled)
    now = _now()
    state.last_transition = "automation_enabled" if payload.enabled else "manual_hold"
    state.last_transition_at = now
    if not payload.enabled:
        state.last_reason = "Automation disabled by platform owner"
    _audit(
        db,
        current,
        "hosting.node_health.automation_enabled" if payload.enabled else "hosting.node_health.manual_hold",
        "hosting_node",
        str(node.id),
        metadata={"enabled": payload.enabled},
    )
    result = reconcile_node_health(db, node)
    db.commit()
    return result


@router.post("/platform/hosting/nodes/{node_id}/activate")
def activate_onboarded_node(
    node_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    node = db.get(HostingNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Hosting node not found")
    health = evaluate_node_health(db, node)
    if not health["healthy"]:
        missing = [key for key, value in health["checks"].items() if not value]
        raise HTTPException(status_code=409, detail="Node onboarding is not complete: " + ", ".join(missing))
    node.status = "active"
    node.accepts_new_projects = True
    state = ensure_health_state(db, node, enable=True)
    state.health_status = "healthy"
    state.healthy_since = _now()
    state.unhealthy_since = None
    state.last_transition = "manual_activated"
    state.last_transition_at = _now()
    state.last_reason = None
    _audit(db, current, "hosting.node_bootstrap.activate", "hosting_node", str(node.id), metadata=health["checks"])
    db.commit()
    return {"ok": True, "node_id": str(node.id), "status": node.status, "accepts_new_projects": node.accepts_new_projects, "automation_enabled": True}


@router.post("/platform/hosting/nodes/{node_id}/agent-token")
def rotate_node_agent_token(
    node_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    node = db.get(HostingNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Hosting node not found")
    raw = "ith_host_" + secrets.token_urlsafe(36)
    now = _now()
    agent = db.get(HostingNodeAgent, node_id)
    if agent is None:
        agent = HostingNodeAgent(
            node_id=node_id,
            token_hash=hash_token(raw),
            token_hint=raw[:18],
            rotated_at=now,
            rotated_by_user_id=current.id,
        )
        db.add(agent)
    else:
        agent.token_hash = hash_token(raw)
        agent.token_hint = raw[:18]
        agent.rotated_at = now
        agent.rotated_by_user_id = current.id
        agent.last_seen_at = None
        agent.agent_version = None
    _audit(db, current, "hosting.node_agent.rotate", "hosting_node", str(node_id), metadata={"node": node.name})
    db.commit()
    return {
        "node_id": str(node_id),
        "token": raw,
        "token_hint": raw[:18],
        "warning": "This credential is shown once. Store it only on the host-side Ithute hosting agent.",
    }


@router.get("/platform/hosting/nodes/{node_id}/agent")
def node_agent_status(
    node_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    node = db.get(HostingNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Hosting node not found")
    agent = db.get(HostingNodeAgent, node_id)
    return {
        "node_id": str(node_id),
        "configured": agent is not None,
        "token_hint": agent.token_hint if agent else None,
        "agent_version": agent.agent_version if agent else None,
        "last_seen_at": agent.last_seen_at.isoformat() if agent and agent.last_seen_at else None,
        "origin_bind_ip": agent.origin_bind_ip if agent else None,
        "rotated_at": agent.rotated_at.isoformat() if agent else None,
    }


@router.get("/tenants/{tenant_id}/hosting/projects/{project_id}/environment")
def list_environment(
    tenant_id: UUID,
    project_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.read", db, current)
    project = _project(db, tenant_id, project_id)
    rows = db.scalars(
        select(HostingEnvironmentVariable)
        .where(HostingEnvironmentVariable.project_id == project.id)
        .order_by(HostingEnvironmentVariable.key)
    ).all()
    return {
        "items": [
            {
                "key": row.key,
                "is_secret": row.is_secret,
                "has_value": True,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ]
    }


@router.put("/tenants/{tenant_id}/hosting/projects/{project_id}/environment/{key}")
def put_environment(
    tenant_id: UUID,
    project_id: UUID,
    key: str,
    payload: EnvironmentValue,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    project = _project(db, tenant_id, project_id)
    normalized_key = key.strip().upper()
    if not _ENV_KEY_RE.fullmatch(normalized_key):
        raise HTTPException(status_code=422, detail="Environment key must use A-Z, 0-9 and underscores and cannot start with a number")
    row = db.scalar(
        select(HostingEnvironmentVariable).where(
            HostingEnvironmentVariable.project_id == project.id,
            HostingEnvironmentVariable.key == normalized_key,
        )
    )
    encrypted = encrypt_secret(payload.value)
    if row is None:
        row = HostingEnvironmentVariable(
            project_id=project.id,
            key=normalized_key,
            encrypted_value=encrypted,
            is_secret=payload.is_secret,
            created_by_user_id=current.id,
            updated_by_user_id=current.id,
        )
        db.add(row)
    else:
        row.encrypted_value = encrypted
        row.is_secret = payload.is_secret
        row.updated_by_user_id = current.id
    _audit(db, current, "hosting.environment.put", "hosting_project", str(project.id), tenant_id=tenant_id, metadata={"key": normalized_key, "secret": payload.is_secret})
    db.commit()
    return {"key": normalized_key, "is_secret": payload.is_secret, "has_value": True}


@router.delete("/tenants/{tenant_id}/hosting/projects/{project_id}/environment/{key}", status_code=204)
def delete_environment(
    tenant_id: UUID,
    project_id: UUID,
    key: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    project = _project(db, tenant_id, project_id)
    normalized_key = key.strip().upper()
    row = db.scalar(
        select(HostingEnvironmentVariable).where(
            HostingEnvironmentVariable.project_id == project.id,
            HostingEnvironmentVariable.key == normalized_key,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Environment variable not found")
    db.delete(row)
    _audit(db, current, "hosting.environment.delete", "hosting_project", str(project.id), tenant_id=tenant_id, metadata={"key": normalized_key})
    db.commit()


@router.get("/tenants/{tenant_id}/hosting/projects/{project_id}/deployments")
def list_deployments(
    tenant_id: UUID,
    project_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.read", db, current)
    project = _project(db, tenant_id, project_id)
    rows = db.scalars(
        select(HostingDeployment)
        .where(HostingDeployment.project_id == project.id)
        .order_by(HostingDeployment.release_number.desc())
        .limit(100)
    ).all()
    return {"items": [_deployment_out(row) for row in rows]}


@router.post("/tenants/{tenant_id}/hosting/projects/{project_id}/deployments", status_code=201)
def queue_deployment(
    tenant_id: UUID,
    project_id: UUID,
    payload: DeploymentCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    project = _project(db, tenant_id, project_id, lock=True)
    image_ref, digest = _validate_image_ref(payload.image_ref)
    source_commit = _validate_source_commit(payload.source_commit)
    previous = _last_healthy(db, project.id)
    deployment = _create_deployment(
        db,
        project=project,
        current=current,
        image_ref=image_ref,
        image_digest=digest,
        source_commit=source_commit,
        previous_deployment_id=previous.id if previous else None,
    )
    db.commit()
    db.refresh(deployment)
    return _deployment_out(deployment)


@router.post("/tenants/{tenant_id}/hosting/projects/{project_id}/deployments/{deployment_id}/rollback", status_code=201)
def rollback_deployment(
    tenant_id: UUID,
    project_id: UUID,
    deployment_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    project = _project(db, tenant_id, project_id, lock=True)
    target = db.scalar(
        select(HostingDeployment).where(
            HostingDeployment.id == deployment_id,
            HostingDeployment.project_id == project.id,
            HostingDeployment.status == "healthy",
        )
    )
    if target is None:
        raise HTTPException(status_code=409, detail="Rollback target must be a healthy deployment from this project")
    current_healthy = _last_healthy(db, project.id)
    deployment = _create_deployment(
        db,
        project=project,
        current=current,
        image_ref=target.image_ref,
        image_digest=target.image_digest,
        source_commit=target.source_commit,
        previous_deployment_id=current_healthy.id if current_healthy else None,
    )
    _audit(db, current, "hosting.deployment.rollback", "hosting_deployment", str(deployment.id), tenant_id=tenant_id, metadata={"rollback_target": str(target.id)})
    db.commit()
    db.refresh(deployment)
    return _deployment_out(deployment)


@router.post("/hosting/agent/heartbeat")
def agent_heartbeat(
    payload: AgentHeartbeat,
    x_ithute_hosting_agent: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    agent, node = _agent_from_token(db, x_ithute_hosting_agent)
    agent.agent_version = payload.version.strip()
    agent.last_seen_at = _now()
    agent.origin_bind_ip = _private_ipv4(payload.origin_bind_ip)
    encoded_capabilities = json.dumps(payload.capabilities, sort_keys=True, separators=(",", ":"))
    if len(encoded_capabilities) > 8000:
        raise HTTPException(status_code=422, detail="Hosting agent capability payload is too large")
    agent.capabilities_json = encoded_capabilities
    replication = persist_postgres_replica_telemetry(
        db,
        node=node,
        capabilities=payload.capabilities,
        now=agent.last_seen_at,
    )
    rpo = persist_primary_rpo_telemetry(
        db,
        node=node,
        capabilities=payload.capabilities,
        now=agent.last_seen_at,
    )
    db.commit()
    return {
        "ok": True,
        "node_id": str(node.id),
        "node": node.name,
        "status": node.status,
        "postgres_replica_telemetry": replication,
        "postgres_rpo_telemetry": rpo,
    }


@router.post("/hosting/agent/deployments/claim")
def claim_deployment(
    x_ithute_hosting_agent: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    agent, node = _agent_from_token(db, x_ithute_hosting_agent)
    agent.last_seen_at = _now()
    deployment = db.scalar(
        select(HostingDeployment)
        .where(HostingDeployment.node_id == node.id, HostingDeployment.status == "queued")
        .order_by(HostingDeployment.created_at.asc())
        .with_for_update(skip_locked=True)
    )
    if deployment is None:
        db.commit()
        return {"deployment": None}
    project = db.get(HostingProject, deployment.project_id)
    if project is None or project.status == "suspended":
        deployment.status = "failed"
        deployment.failure_message = "Project is unavailable or suspended"
        deployment.completed_at = _now()
        db.commit()
        return {"deployment": None}

    environment_rows = db.scalars(
        select(HostingEnvironmentVariable)
        .where(HostingEnvironmentVariable.project_id == project.id)
        .order_by(HostingEnvironmentVariable.key)
    ).all()
    try:
        environment = {row.key: decrypt_secret(row.encrypted_value) for row in environment_rows}
    except ValueError as exc:
        deployment.status = "failed"
        deployment.failure_message = "Project environment could not be decrypted"
        deployment.completed_at = _now()
        project.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail="Project environment could not be prepared") from exc

    deployment.status = "claimed"
    deployment.claimed_at = _now()
    project.status = "deploying"
    db.commit()
    return {
        "deployment": {
            "id": str(deployment.id),
            "release_number": deployment.release_number,
            "image_ref": deployment.image_ref,
            "image_digest": deployment.image_digest,
            "source_commit": deployment.source_commit,
            "reset_data_volume": deployment.reset_data_volume,
            "manifest_version": deployment.runtime_manifest_version,
            "project": {
                "id": str(project.id),
                "tenant_id": str(project.tenant_id),
                "slug": project.slug,
                "runtime": project.runtime,
                "hostname": project.hostname,
                "container_port": project.container_port,
                "health_path": project.health_path,
                "resources": {
                    "storage_mb": project.storage_mb,
                    "memory_mb": project.memory_mb,
                    "cpu_millicores": project.cpu_millicores,
                    "pid_limit": project.pid_limit,
                },
                "environment": environment,
                "security": {
                    "privileged": False,
                    "host_ports": [],
                    "docker_socket": False,
                    "cap_drop": ["ALL"],
                    "no_new_privileges": True,
                    "read_only_root": True,
                    "persistent_mount": "/data",
                    "public_ingress": "ithute-edge-only",
                },
            },
        }
    }


@router.post("/hosting/agent/deployments/{deployment_id}/status")
def report_deployment_status(
    deployment_id: UUID,
    payload: AgentStatusUpdate,
    x_ithute_hosting_agent: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    agent, node = _agent_from_token(db, x_ithute_hosting_agent)
    agent.last_seen_at = _now()
    deployment = db.scalar(
        select(HostingDeployment)
        .where(HostingDeployment.id == deployment_id, HostingDeployment.node_id == node.id)
        .with_for_update()
    )
    if deployment is None:
        raise HTTPException(status_code=404, detail="Deployment not found for this hosting node")
    project = db.scalar(select(HostingProject).where(HostingProject.id == deployment.project_id).with_for_update())
    if project is None:
        raise HTTPException(status_code=404, detail="Hosted project not found")
    now = _now()

    if project.status == "suspended":
        if deployment.status in {"claimed", "running"}:
            deployment.status = "failed"
            deployment.completed_at = now
            deployment.failure_message = "Project was suspended before deployment completed"
            db.commit()
            db.refresh(deployment)
        if payload.status == "failed":
            return _deployment_out(deployment)
        raise HTTPException(status_code=409, detail="Suspended project cannot accept deployment promotion")

    if payload.status == "running":
        if deployment.status not in {"claimed", "running"}:
            raise HTTPException(status_code=409, detail="Deployment cannot enter running state from its current state")
        deployment.status = "running"
        deployment.started_at = deployment.started_at or now
        project.status = "deploying"
    elif payload.status == "healthy":
        if deployment.status not in {"claimed", "running", "healthy"}:
            raise HTTPException(status_code=409, detail="Deployment cannot become healthy from its current state")
        deployment.status = "healthy"
        deployment.started_at = deployment.started_at or now
        deployment.completed_at = deployment.completed_at or now
        deployment.last_health_at = now
        deployment.failure_message = None
        if payload.origin_url:
            from app.services.hosting_edge_handoff import HostingOriginError, validate_trusted_origin
            try:
                deployment.origin_url = validate_trusted_origin(payload.origin_url)
            except HostingOriginError as exc:
                deployment.status = "failed"
                deployment.completed_at = now
                deployment.failure_message = f"Hosting origin handoff rejected: {exc}"
                failover = db.scalar(select(HostingFailoverAttempt).where(
                    HostingFailoverAttempt.deployment_id == deployment.id,
                    HostingFailoverAttempt.status.in_(["pending", "deploying", "edge_pending"]),
                ))
                source = db.get(HostingNode, failover.source_node_id) if failover else None
                project.status = "running" if source and source.status == "active" else "failed"
                db.commit()
                db.refresh(deployment)
                return _deployment_out(deployment)
            deployment.origin_reported_at = now
        project.image_ref = deployment.image_ref
        failover = db.scalar(select(HostingFailoverAttempt).where(
            HostingFailoverAttempt.deployment_id == deployment.id,
            HostingFailoverAttempt.status.in_(["pending", "deploying", "edge_pending"]),
        ))
        project.status = "deploying" if failover is not None else "running"
    else:
        if deployment.status not in {"claimed", "running"}:
            raise HTTPException(status_code=409, detail="Deployment cannot fail from its current state")
        deployment.status = "failed"
        deployment.completed_at = now
        deployment.failure_message = (payload.message or "Node agent reported deployment failure").strip()[:2000]
        failover = db.scalar(select(HostingFailoverAttempt).where(
            HostingFailoverAttempt.deployment_id == deployment.id,
            HostingFailoverAttempt.status.in_(["pending", "deploying", "edge_pending"]),
        ))
        if failover is not None:
            source = db.get(HostingNode, failover.source_node_id)
            project.status = "running" if source and source.status == "active" else "failed"
        else:
            previous = _last_healthy(db, project.id)
            project.status = "running" if previous is not None else "failed"

    db.commit()
    db.refresh(deployment)
    return _deployment_out(deployment)
