from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_platform_owner
from app.core.security import hash_token
from app.db.session import get_db
from app.models import (
    AuditLog,
    HostingDatabase,
    HostingNode,
    HostingNodeAgent,
    HostingProject,
    InfrastructureServer,
    InfrastructureServerAgent,
    MailNode,
    Mailbox,
    User,
)

router = APIRouter(prefix="/platform/infrastructure", tags=["infrastructure"])

ALLOWED_ROLES = {"mail", "application", "database", "storage", "build", "backup"}
ALLOWED_STATUSES = {"active", "maintenance", "disabled"}
HEARTBEAT_GRACE_SECONDS = 180


class InfrastructureServerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    hostname: str = Field(min_length=3, max_length=253)
    public_ip: str | None = Field(default=None, max_length=64)
    region: str = Field(default="lesotho", min_length=2, max_length=80)
    provider: str | None = Field(default=None, max_length=80)
    roles: list[str] = Field(default_factory=lambda: ["application"], min_length=1, max_length=6)
    notes: str | None = Field(default=None, max_length=2000)


class InfrastructureAgentHeartbeat(BaseModel):
    version: str = Field(min_length=1, max_length=80)
    os_name: str | None = Field(default=None, max_length=160)
    kernel_version: str | None = Field(default=None, max_length=160)
    uptime_seconds: int | None = Field(default=None, ge=0)
    telemetry: dict = Field(default_factory=dict)
    capabilities: dict = Field(default_factory=dict)


class InfrastructureServerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    public_ip: str | None = Field(default=None, max_length=64)
    region: str | None = Field(default=None, min_length=2, max_length=80)
    provider: str | None = Field(default=None, max_length=80)
    roles: list[str] | None = Field(default=None, min_length=1, max_length=6)
    status: str | None = Field(default=None, pattern=r"^(active|maintenance|disabled)$")
    notes: str | None = Field(default=None, max_length=2000)


def _hostname(value: str) -> str:
    host = value.strip().rstrip(".").lower()
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise HTTPException(status_code=422, detail="Invalid server hostname") from exc
    if len(host) > 253 or not host or any(not part or len(part) > 63 for part in host.split(".")):
        raise HTTPException(status_code=422, detail="Invalid server hostname")
    return host


def _roles(values: list[str]) -> list[str]:
    roles = sorted({str(value).strip().lower() for value in values if str(value).strip()})
    invalid = [value for value in roles if value not in ALLOWED_ROLES]
    if invalid:
        raise HTTPException(status_code=422, detail=f"Unsupported server roles: {', '.join(invalid)}")
    if not roles:
        raise HTTPException(status_code=422, detail="Select at least one server role")
    return roles


def _json_roles(raw: str) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        value = []
    return sorted({str(item) for item in value if str(item) in ALLOWED_ROLES})


def _fresh(value: datetime | None) -> bool:
    if value is None:
        return False
    now = datetime.now(timezone.utc)
    current = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return current >= now - timedelta(seconds=HEARTBEAT_GRACE_SECONDS)


def _audit(db: Session, current: User, action: str, server: InfrastructureServer, metadata: dict | None = None) -> None:
    db.add(
        AuditLog(
            actor_user_id=current.id,
            action=action,
            resource_type="infrastructure_server",
            resource_id=str(server.id),
            metadata_json=json.dumps(metadata or {}, sort_keys=True),
        )
    )


def _hosting_allocated(db: Session, node_id: UUID) -> dict:
    row = db.execute(
        select(
            func.coalesce(func.sum(HostingProject.storage_mb), 0),
            func.coalesce(func.sum(HostingProject.memory_mb), 0),
            func.coalesce(func.sum(HostingProject.cpu_millicores), 0),
            func.count(HostingProject.id),
        ).where(HostingProject.node_id == node_id)
    ).one()
    return {
        "storage_mb": int(row[0]),
        "memory_mb": int(row[1]),
        "cpu_millicores": int(row[2]),
        "projects": int(row[3]),
    }


def _server_out(db: Session, server: InfrastructureServer) -> dict:
    roles = _json_roles(server.roles_json)
    mail = db.get(MailNode, server.mail_node_id) if server.mail_node_id else None
    hosting = db.get(HostingNode, server.hosting_node_id) if server.hosting_node_id else None
    hosting_agent = db.get(HostingNodeAgent, hosting.id) if hosting else None
    server_agent = db.get(InfrastructureServerAgent, server.id)

    mailbox_count = int(db.scalar(select(func.count(Mailbox.id)).where(Mailbox.mail_node_id == mail.id)) or 0) if mail else 0
    project_count = int(db.scalar(select(func.count(HostingProject.id)).where(HostingProject.node_id == hosting.id)) or 0) if hosting else 0
    database_count = int(db.scalar(select(func.count(HostingDatabase.id)).where(HostingDatabase.node_id == hosting.id)) or 0) if hosting else 0

    mail_heartbeat = mail.last_heartbeat_at if mail else None
    hosting_heartbeat = hosting_agent.last_seen_at if hosting_agent else None
    mail_online = bool(mail and _fresh(mail_heartbeat))
    hosting_online = bool(hosting and hosting_agent and _fresh(hosting_heartbeat))
    mail_ready = bool(mail and mail.smtp_ready and mail.imap_ready and mail.tls_ready)

    expected_missing = []
    if "mail" in roles and not mail:
        expected_missing.append("mail")
    if ({"application", "database"} & set(roles)) and not hosting:
        expected_missing.append("hosting")

    linked_health = []
    if mail:
        linked_health.append(mail_online and mail_ready)
    if hosting:
        linked_health.append(hosting_online)

    server_agent_online = bool(server_agent and _fresh(server_agent.last_seen_at))
    if server.status != "active":
        health = server.status
    elif expected_missing:
        health = "configuration_required"
    elif linked_health and all(linked_health):
        health = "healthy"
    elif linked_health and any(linked_health):
        health = "degraded"
    elif linked_health:
        health = "offline"
    else:
        health = "registered"

    hosting_allocated = _hosting_allocated(db, hosting.id) if hosting else {"storage_mb": 0, "memory_mb": 0, "cpu_millicores": 0, "projects": 0}
    hosting_capacity = None
    if hosting:
        hosting_capacity = {
            "allocatable_storage_mb": hosting.allocatable_storage_mb,
            "allocated_storage_mb": hosting_allocated["storage_mb"],
            "available_storage_mb": max(0, hosting.allocatable_storage_mb - hosting_allocated["storage_mb"]),
            "allocatable_memory_mb": hosting.allocatable_memory_mb,
            "allocated_memory_mb": hosting_allocated["memory_mb"],
            "available_memory_mb": max(0, hosting.allocatable_memory_mb - hosting_allocated["memory_mb"]),
            "allocatable_cpu_millicores": hosting.allocatable_cpu_millicores,
            "allocated_cpu_millicores": hosting_allocated["cpu_millicores"],
            "available_cpu_millicores": max(0, hosting.allocatable_cpu_millicores - hosting_allocated["cpu_millicores"]),
        }

    return {
        "id": str(server.id),
        "name": server.name,
        "hostname": server.hostname,
        "public_ip": server.public_ip,
        "region": server.region,
        "provider": server.provider,
        "roles": roles,
        "status": server.status,
        "health": health,
        "notes": server.notes,
        "created_at": server.created_at.isoformat() if server.created_at else None,
        "updated_at": server.updated_at.isoformat() if server.updated_at else None,
        "workloads": {
            "mailboxes": mailbox_count,
            "projects": project_count,
            "databases": database_count,
        },
        "mail": {
            "linked": bool(mail),
            "node_id": str(mail.id) if mail else None,
            "status": mail.status if mail else None,
            "online": mail_online,
            "ready": mail_ready,
            "last_heartbeat_at": mail_heartbeat.isoformat() if mail_heartbeat else None,
            "agent_version": mail.agent_version if mail else None,
            "total_storage_bytes": mail.total_storage_bytes if mail else None,
            "used_storage_bytes": mail.used_storage_bytes if mail else None,
            "free_storage_bytes": max(0, (mail.total_storage_bytes or 0) - (mail.used_storage_bytes or 0)) if mail and mail.total_storage_bytes is not None else None,
            "smtp_ready": bool(mail.smtp_ready) if mail else False,
            "imap_ready": bool(mail.imap_ready) if mail else False,
            "tls_ready": bool(mail.tls_ready) if mail else False,
            "backup_ready": bool(mail.backup_ready) if mail else False,
        },
        "hosting": {
            "linked": bool(hosting),
            "node_id": str(hosting.id) if hosting else None,
            "status": hosting.status if hosting else None,
            "online": hosting_online,
            "accepts_new_projects": bool(hosting.accepts_new_projects) if hosting else False,
            "agent_version": hosting_agent.agent_version if hosting_agent else None,
            "last_heartbeat_at": hosting_heartbeat.isoformat() if hosting_heartbeat else None,
            "capacity": hosting_capacity,
        },
        "configuration_required": expected_missing,
        "agent": {
            "configured": bool(server_agent),
            "online": server_agent_online,
            "token_hint": server_agent.token_hint if server_agent else None,
            "version": server_agent.agent_version if server_agent else None,
            "last_seen_at": server_agent.last_seen_at.isoformat() if server_agent and server_agent.last_seen_at else None,
            "os_name": server_agent.os_name if server_agent else None,
            "kernel_version": server_agent.kernel_version if server_agent else None,
            "uptime_seconds": server_agent.uptime_seconds if server_agent else None,
            "telemetry": json.loads(server_agent.telemetry_json or "{}") if server_agent else {},
            "capabilities": json.loads(server_agent.capabilities_json or "{}") if server_agent else {},
        },
    }


@router.get("/servers")
def list_servers(db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    rows = db.scalars(select(InfrastructureServer).order_by(InfrastructureServer.name.asc())).all()
    return {
        "items": [_server_out(db, row) for row in rows],
        "roles": sorted(ALLOWED_ROLES),
        "heartbeat_grace_seconds": HEARTBEAT_GRACE_SECONDS,
    }


@router.post("/servers", status_code=201)
def create_server(payload: InfrastructureServerCreate, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    host = _hostname(payload.hostname)
    if db.scalar(select(InfrastructureServer.id).where(InfrastructureServer.hostname == host)) is not None:
        raise HTTPException(status_code=409, detail="This server hostname is already registered")
    server = InfrastructureServer(
        name=payload.name.strip(),
        hostname=host,
        public_ip=payload.public_ip.strip() if payload.public_ip else None,
        region=payload.region.strip().lower(),
        provider=payload.provider.strip() if payload.provider else None,
        roles_json=json.dumps(_roles(payload.roles), separators=(",", ":")),
        notes=payload.notes.strip() if payload.notes else None,
        created_by_user_id=current.id,
    )
    db.add(server)
    db.flush()
    _audit(db, current, "infrastructure.server.create", server, {"roles": _json_roles(server.roles_json)})
    db.commit()
    db.refresh(server)
    return _server_out(db, server)


@router.patch("/servers/{server_id}")
def update_server(server_id: UUID, payload: InfrastructureServerUpdate, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    server = db.get(InfrastructureServer, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Infrastructure server not found")
    changes = payload.model_dump(exclude_unset=True)
    if "roles" in changes:
        server.roles_json = json.dumps(_roles(changes.pop("roles")), separators=(",", ":"))
    for key, value in changes.items():
        if key in {"name", "region", "provider", "public_ip", "notes"} and isinstance(value, str):
            value = value.strip()
        setattr(server, key, value)
    _audit(db, current, "infrastructure.server.update", server, {"changed_fields": sorted(payload.model_dump(exclude_unset=True))})
    db.commit()
    db.refresh(server)
    return _server_out(db, server)


def _server_agent_from_token(db: Session, token: str | None) -> tuple[InfrastructureServerAgent, InfrastructureServer]:
    raw = (token or "").strip()
    if not raw or not raw.startswith("ith_srv_"):
        raise HTTPException(status_code=401, detail="Infrastructure server agent credential required")
    agent = db.scalar(select(InfrastructureServerAgent).where(InfrastructureServerAgent.token_hash == hash_token(raw)))
    if agent is None:
        raise HTTPException(status_code=401, detail="Invalid infrastructure server agent credential")
    server = db.get(InfrastructureServer, agent.server_id)
    if server is None or server.status == "disabled":
        raise HTTPException(status_code=403, detail="Infrastructure server is unavailable")
    return agent, server


@router.post("/servers/{server_id}/agent-token")
def rotate_server_agent_token(server_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    server = db.get(InfrastructureServer, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Infrastructure server not found")
    raw = "ith_srv_" + secrets.token_urlsafe(36)
    now = datetime.now(timezone.utc)
    agent = db.get(InfrastructureServerAgent, server.id)
    if agent is None:
        agent = InfrastructureServerAgent(
            server_id=server.id,
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
        agent.agent_version = None
        agent.last_seen_at = None
        agent.telemetry_json = "{}"
        agent.capabilities_json = "{}"
    _audit(db, current, "infrastructure.server_agent.rotate", server)
    db.commit()
    return {
        "server_id": str(server.id),
        "token": raw,
        "token_hint": raw[:18],
        "warning": "This credential is shown once. Store it only on the Ithute Server Agent host.",
    }


@router.post("/agent/heartbeat")
def infrastructure_agent_heartbeat(
    payload: InfrastructureAgentHeartbeat,
    x_ithute_server_agent: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    agent, server = _server_agent_from_token(db, x_ithute_server_agent)
    agent.agent_version = payload.version.strip()
    agent.last_seen_at = datetime.now(timezone.utc)
    agent.os_name = payload.os_name.strip() if payload.os_name else None
    agent.kernel_version = payload.kernel_version.strip() if payload.kernel_version else None
    agent.uptime_seconds = payload.uptime_seconds
    agent.telemetry_json = json.dumps(payload.telemetry, separators=(",", ":"), sort_keys=True)
    agent.capabilities_json = json.dumps(payload.capabilities, separators=(",", ":"), sort_keys=True)
    db.commit()
    return {"ok": True, "server_id": str(server.id), "status": server.status}


@router.post("/servers/import-existing")
def import_existing_servers(db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    existing = db.scalars(select(InfrastructureServer)).all()
    by_host = {row.hostname.lower(): row for row in existing}
    by_ip = {row.public_ip: row for row in existing if row.public_ip}
    created = 0
    linked = 0

    def find_server(hostname: str, public_ip: str | None):
        return by_host.get(hostname.lower()) or (by_ip.get(public_ip) if public_ip else None)

    mail_nodes = db.scalars(select(MailNode).order_by(MailNode.created_at.asc())).all()
    for node in mail_nodes:
        if db.scalar(select(InfrastructureServer.id).where(InfrastructureServer.mail_node_id == node.id)) is not None:
            continue
        server = find_server(node.hostname, node.public_ip)
        if server is None:
            roles = sorted({"mail", "storage"} | set(json.loads(node.capabilities_json or "[]")))
            roles = [role for role in roles if role in ALLOWED_ROLES] or ["mail", "storage"]
            server = InfrastructureServer(
                name=node.name,
                hostname=_hostname(node.hostname),
                public_ip=node.public_ip,
                region=node.region,
                provider=node.provider,
                roles_json=json.dumps(roles, separators=(",", ":")),
                mail_node_id=node.id,
                created_by_user_id=current.id,
            )
            db.add(server)
            db.flush()
            by_host[server.hostname] = server
            if server.public_ip:
                by_ip[server.public_ip] = server
            created += 1
        else:
            roles = set(_json_roles(server.roles_json)) | {"mail", "storage"}
            server.roles_json = json.dumps(sorted(roles), separators=(",", ":"))
            server.mail_node_id = node.id
            linked += 1

    hosting_nodes = db.scalars(select(HostingNode).order_by(HostingNode.created_at.asc())).all()
    for node in hosting_nodes:
        if db.scalar(select(InfrastructureServer.id).where(InfrastructureServer.hosting_node_id == node.id)) is not None:
            continue
        server = find_server(node.hostname, node.public_ip)
        if server is None:
            server = InfrastructureServer(
                name=node.name,
                hostname=_hostname(node.hostname),
                public_ip=node.public_ip,
                roles_json='["application","database"]',
                hosting_node_id=node.id,
                created_by_user_id=current.id,
            )
            db.add(server)
            db.flush()
            by_host[server.hostname] = server
            if server.public_ip:
                by_ip[server.public_ip] = server
            created += 1
        else:
            roles = set(_json_roles(server.roles_json)) | {"application", "database"}
            server.roles_json = json.dumps(sorted(roles), separators=(",", ":"))
            server.hosting_node_id = node.id
            linked += 1

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Existing node import found conflicting physical-server identities") from exc

    for server in db.scalars(select(InfrastructureServer)).all():
        if server.created_by_user_id == current.id:
            pass
    db.commit()
    return {"imported": created, "linked": linked, "total": int(db.scalar(select(func.count(InfrastructureServer.id))) or 0)}
