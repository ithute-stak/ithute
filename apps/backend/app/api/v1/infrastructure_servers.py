from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_platform_owner
from app.core.security import hash_token
from app.db.session import get_db
from app.services.engine_router import execute_binary, execute_hmac_sha256, execute_network, routing_status
from app.services.cluster_engine import cluster_graph_analysis
from app.services.managed_network import update_peer_telemetry
from app.services.network_topology import persist_topology_observations
from app.models import (
    AuditLog,
    HostingDatabase,
    HostingNode,
    HostingNodeAgent,
    HostingProject,
    InfrastructureAgentCommand,
    InfrastructureContainerSnapshot,
    InfrastructureNetworkGrant,
    InfrastructureSecuritySnapshot,
    InfrastructureServer,
    InfrastructureServerAgent,
    InfrastructureTelemetrySnapshot,
    InfrastructureWireGuardPeer,
    MailNode,
    Mailbox,
    User,
)

router = APIRouter(prefix="/platform/infrastructure", tags=["infrastructure"])

ALLOWED_ROLES = {"mail", "application", "database", "storage", "build", "backup"}
ALLOWED_STATUSES = {"active", "maintenance", "disabled"}
HEARTBEAT_GRACE_SECONDS = 180
AGENT_COMMAND_KINDS = {
    "agent.ping",
    "service.restart",
    "service.start",
    "service.stop",
    "container.restart",
    "container.start",
    "container.stop",
}
AGENT_SERVICE_RE = re.compile(r"^[A-Za-z0-9@_.:-]+(?:\.service)?$")
AGENT_CONTAINER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
AGENT_BLOCKED_SERVICES = {
    "ssh", "sshd", "ssh.service", "sshd.service",
    "networking", "networking.service",
    "systemd-networkd", "systemd-networkd.service",
    "ufw", "ufw.service", "firewalld", "firewalld.service",
}


class InfrastructureServerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    hostname: str = Field(min_length=3, max_length=253)
    public_ip: str | None = Field(default=None, max_length=64)
    region: str = Field(default="lesotho", min_length=2, max_length=80)
    provider: str | None = Field(default=None, max_length=80)
    datacenter: str | None = Field(default=None, max_length=120)
    physical_host: str | None = Field(default=None, max_length=160)
    network_segment: str | None = Field(default=None, max_length=160)
    roles: list[str] = Field(default_factory=lambda: ["application"], min_length=1, max_length=6)
    notes: str | None = Field(default=None, max_length=2000)


class InfrastructureAgentHeartbeat(BaseModel):
    version: str = Field(min_length=1, max_length=80)
    os_name: str | None = Field(default=None, max_length=160)
    kernel_version: str | None = Field(default=None, max_length=160)
    uptime_seconds: int | None = Field(default=None, ge=0)
    telemetry: dict = Field(default_factory=dict)
    capabilities: dict = Field(default_factory=dict)


class InfrastructureAgentCommandCreate(BaseModel):
    kind: str = Field(min_length=1, max_length=64)
    payload: dict = Field(default_factory=dict)


class InfrastructureAgentCommandResult(BaseModel):
    ok: bool
    result: dict = Field(default_factory=dict)
    error: str | None = Field(default=None, max_length=8000)


class InfrastructureServerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    public_ip: str | None = Field(default=None, max_length=64)
    region: str | None = Field(default=None, min_length=2, max_length=80)
    provider: str | None = Field(default=None, max_length=80)
    datacenter: str | None = Field(default=None, max_length=120)
    physical_host: str | None = Field(default=None, max_length=160)
    network_segment: str | None = Field(default=None, max_length=160)
    roles: list[str] | None = Field(default=None, min_length=1, max_length=6)
    status: str | None = Field(default=None, pattern=r"^(active|maintenance|disabled)$")
    notes: str | None = Field(default=None, max_length=2000)
    cpu_alert_percent: int | None = Field(default=None, ge=50, le=100)
    memory_alert_percent: int | None = Field(default=None, ge=50, le=100)
    disk_alert_percent: int | None = Field(default=None, ge=50, le=100)
    offline_alert_minutes: int | None = Field(default=None, ge=2, le=1440)


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


def _validated_agent_command(kind: str, payload: dict) -> tuple[str, dict]:
    normalized_kind = kind.strip().lower()
    if normalized_kind not in AGENT_COMMAND_KINDS:
        raise HTTPException(status_code=422, detail="Unsupported structured infrastructure-agent command")
    if normalized_kind == "agent.ping":
        return normalized_kind, {}
    if normalized_kind.startswith("service."):
        unit = str(payload.get("unit") or "").strip()
        if not AGENT_SERVICE_RE.fullmatch(unit):
            raise HTTPException(status_code=422, detail="Invalid systemd service")
        normalized_unit = unit if unit.endswith(".service") else f"{unit}.service"
        if unit in AGENT_BLOCKED_SERVICES or normalized_unit in AGENT_BLOCKED_SERVICES:
            raise HTTPException(status_code=409, detail="Connectivity-critical services are blocked from agent actions")
        return normalized_kind, {"unit": normalized_unit}
    container = str(payload.get("container") or "").strip()
    if not AGENT_CONTAINER_RE.fullmatch(container):
        raise HTTPException(status_code=422, detail="Invalid Docker container name or id")
    return normalized_kind, {"container": container}


def _command_out(row: InfrastructureAgentCommand) -> dict:
    return {
        "id": str(row.id),
        "server_id": str(row.server_id),
        "kind": row.kind,
        "payload": json.loads(row.payload_json or "{}"),
        "status": row.status,
        "result": json.loads(row.result_json or "{}"),
        "error": row.error,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "claimed_at": row.claimed_at.isoformat() if row.claimed_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


def _container_drift(db: Session, server: InfrastructureServer, telemetry: dict) -> dict:
    docker = telemetry.get("docker") if isinstance(telemetry.get("docker"), dict) else {}
    containers = docker.get("containers") if isinstance(docker.get("containers"), list) else []
    expected_ids: set[str] = set()
    if server.hosting_node_id:
        project_ids = db.scalars(
            select(HostingProject.id).where(
                HostingProject.node_id == server.hosting_node_id,
                HostingProject.status != "suspended",
            )
        ).all()
        expected_ids = {str(value) for value in project_ids}

    reported_ids: set[str] = set()
    running = 0
    clean: list[dict] = []
    for item in containers[:1000]:
        if not isinstance(item, dict):
            continue
        labels = item.get("labels") if isinstance(item.get("labels"), dict) else {}
        project_id = str(labels.get("ithute.project_id") or item.get("project_id") or "").strip()
        if project_id:
            reported_ids.add(project_id)
        state = str(item.get("state") or item.get("status") or "").strip().lower()
        if state in {"running", "up", "healthy"}:
            running += 1
        clean.append({
            "name": str(item.get("name") or "")[:160],
            "image": str(item.get("image") or "")[:500],
            "state": state[:32],
            "project_id": project_id or None,
        })

    missing = sorted(expected_ids - reported_ids)
    unexpected = sorted(reported_ids - expected_ids)
    drift_status = "healthy" if not missing and not unexpected else "attention"
    return {
        "containers": clean,
        "expected_count": len(expected_ids),
        "running_count": running,
        "missing_project_ids": missing,
        "unexpected_project_ids": unexpected,
        "missing_count": len(missing),
        "unexpected_count": len(unexpected),
        "drift_status": drift_status,
    }


def _security_findings(telemetry: dict) -> dict:
    raw_security = telemetry.get("security")
    security = raw_security if isinstance(raw_security, dict) else {}
    if not security:
        canonical = b'[{"key":"agent.security_unavailable","severity":"high"}]'
        digest = execute_binary("crypto.sha256", canonical)
        return {
            "score": 50,
            "posture": "critical",
            "findings": [{
                "key": "agent.security_unavailable",
                "severity": "high",
                "title": "Host security scan is unavailable",
                "evidence": "The connected server agent has not reported v3 host-security telemetry.",
                "recommendation": "Upgrade/restart the Ithute Server Agent so SSH, firewall, update and Docker security signals are reported.",
            }],
            "fingerprint_sha256": str(digest.value),
            "fingerprint_engine": digest.engine,
        }

    sshd = security.get("sshd") if isinstance(security.get("sshd"), dict) else {}
    firewall = security.get("firewall") if isinstance(security.get("firewall"), dict) else {}
    docker = security.get("docker") if isinstance(security.get("docker"), dict) else {}
    risky = security.get("risky_public_listeners") if isinstance(security.get("risky_public_listeners"), list) else []

    findings: list[dict] = []

    def add(key: str, severity: str, title: str, evidence: str, recommendation: str) -> None:
        findings.append({
            "key": key,
            "severity": severity,
            "title": title,
            "evidence": evidence[:500],
            "recommendation": recommendation[:1000],
        })

    root_login = str(sshd.get("permit_root_login") or "").lower()
    if root_login in {"yes", "without-password", "prohibit-password"}:
        add(
            "ssh.root_login",
            "high" if root_login == "yes" else "medium",
            "SSH root login is permitted",
            f"PermitRootLogin={root_login}",
            "Prefer named administrative users with sudo and disable direct root SSH login.",
        )

    password_auth = str(sshd.get("password_authentication") or "").lower()
    if password_auth == "yes":
        add(
            "ssh.password_auth",
            "medium",
            "SSH password authentication is enabled",
            "PasswordAuthentication=yes",
            "Prefer public-key authentication and disable SSH password authentication after access is verified.",
        )

    if firewall.get("active") is False:
        add(
            "firewall.inactive",
            "high",
            "Host firewall is not active",
            f"provider={firewall.get('provider') or 'none'}",
            "Enable and verify a host firewall with only the required Ithute, mail and application ports.",
        )

    if security.get("fail2ban_active") is False:
        add(
            "fail2ban.inactive",
            "medium",
            "Fail2ban is not active",
            "fail2ban service inactive or unavailable",
            "Enable Fail2ban or an equivalent brute-force protection control for exposed authentication services.",
        )

    if security.get("unattended_upgrades_active") is False:
        add(
            "updates.unattended_inactive",
            "low",
            "Automatic security updates are not active",
            "unattended-upgrades service inactive or unavailable",
            "Enable a controlled unattended security-update policy or document an equivalent patch cadence.",
        )

    if docker.get("socket_world_writable"):
        add(
            "docker.socket_world_writable",
            "critical",
            "Docker socket is world-writable",
            f"mode={docker.get('socket_mode')}",
            "Remove world-write permission from /var/run/docker.sock immediately.",
        )

    privileged = int(docker.get("privileged_running_containers") or 0)
    if privileged > 0:
        add(
            "docker.privileged_containers",
            "high",
            "Privileged containers are running",
            f"count={privileged}",
            "Remove privileged mode unless explicitly required and replace it with narrowly scoped capabilities.",
        )

    if risky:
        ports = sorted({str(item.get("port")) for item in risky if isinstance(item, dict) and item.get("port")})
        add(
            "network.risky_public_ports",
            "high",
            "Database/cache services are listening publicly",
            "ports=" + ",".join(ports),
            "Bind database/cache services to private interfaces or the Ithute managed network and enforce firewall rules.",
        )

    penalties = {"low": 5, "medium": 10, "high": 20, "critical": 40}
    score = max(0, 100 - sum(penalties.get(item["severity"], 0) for item in findings))
    posture = "healthy" if score >= 90 else "attention" if score >= 70 else "critical"
    if any(item["severity"] == "critical" for item in findings):
        posture = "critical"

    canonical = json.dumps(findings, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = execute_binary("crypto.sha256", canonical)
    return {
        "score": score,
        "posture": posture,
        "findings": findings,
        "fingerprint_sha256": str(digest.value),
        "fingerprint_engine": digest.engine,
    }


def _network_health_for_server(server: InfrastructureServer) -> dict:
    targets = _network_probe_targets(server)
    if not targets:
        return {"engine": "go", "checked": 0, "reachable": True, "checks": []}
    execution = execute_network(targets, concurrency=min(8, len(targets)))
    checks = list(execution.value.get("results", [])) if isinstance(execution.value, dict) else []
    return {
        "engine": execution.engine,
        "checked": len(checks),
        "reachable": all(bool(item.get("reachable")) for item in checks) if checks else False,
        "checks": checks,
    }


def _readiness_for_server(db: Session, server: InfrastructureServer) -> dict:
    agent = db.get(InfrastructureServerAgent, server.id)
    latest_security = db.scalar(
        select(InfrastructureSecuritySnapshot)
        .where(InfrastructureSecuritySnapshot.server_id == server.id)
        .order_by(InfrastructureSecuritySnapshot.created_at.desc())
    )
    latest_containers = db.scalar(
        select(InfrastructureContainerSnapshot)
        .where(InfrastructureContainerSnapshot.server_id == server.id)
        .order_by(InfrastructureContainerSnapshot.created_at.desc())
    )
    server_view = _server_out(db, server)
    network = _network_health_for_server(server)

    capabilities = {}
    if agent:
        try:
            capabilities = json.loads(agent.capabilities_json or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            capabilities = {}

    checks = [
        {
            "key": "agent",
            "weight": 20,
            "passed": bool(agent and _fresh(agent.last_seen_at)),
            "detail": "Physical server agent heartbeat is fresh.",
        },
        {
            "key": "workload_health",
            "weight": 20,
            "passed": server_view["health"] in {"healthy", "registered"},
            "detail": f"Derived server health is {server_view['health']}.",
        },
        {
            "key": "container_drift",
            "weight": 15,
            "passed": bool(latest_containers and latest_containers.drift_status == "healthy"),
            "detail": (
                "Managed container inventory matches Ithute assignments."
                if latest_containers and latest_containers.drift_status == "healthy"
                else "Container inventory is missing or has drift."
            ),
        },
        {
            "key": "network",
            "weight": 15,
            "passed": bool(network["reachable"]),
            "detail": f"{network['checked']} role-aware network probes checked by {network['engine']}.",
        },
        {
            "key": "security",
            "weight": 20,
            "passed": bool(latest_security and latest_security.score >= 80),
            "detail": (
                f"Host security score {latest_security.score}/100 ({latest_security.posture})."
                if latest_security
                else "No host security snapshot has been reported yet."
            ),
        },
        {
            "key": "backup_recovery",
            "weight": 10,
            "passed": bool(server_view["mail"]["backup_ready"] or capabilities.get("backup_tools")),
            "detail": (
                "Backup tooling/readiness detected."
                if server_view["mail"]["backup_ready"] or capabilities.get("backup_tools")
                else "No host backup tooling or workload backup readiness has been reported."
            ),
        },
    ]
    score = sum(item["weight"] for item in checks if item["passed"])
    status = "ready" if score >= 90 else "attention" if score >= 70 else "not_ready"
    return {
        "server_id": str(server.id),
        "score": score,
        "status": status,
        "checks": checks,
        "network": network,
        "security": {
            "score": latest_security.score if latest_security else None,
            "posture": latest_security.posture if latest_security else "unknown",
            "fingerprint_sha256": latest_security.fingerprint_sha256 if latest_security else None,
            "checked_at": latest_security.created_at.isoformat() if latest_security and latest_security.created_at else None,
        },
        "engine_contributions": routing_status(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


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


def _number(value) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _telemetry_values(payload: dict) -> dict:
    cpu = payload.get("cpu") if isinstance(payload.get("cpu"), dict) else {}
    memory = payload.get("memory") if isinstance(payload.get("memory"), dict) else {}
    docker = payload.get("docker") if isinstance(payload.get("docker"), dict) else {}
    disks = payload.get("disks") if isinstance(payload.get("disks"), list) else []
    disk_values = [
        _number(item.get("used_percent"))
        for item in disks
        if isinstance(item, dict) and _number(item.get("used_percent")) is not None
    ]
    return {
        "cpu_percent": _number(cpu.get("used_percent")),
        "memory_percent": _number(memory.get("used_percent")),
        "disk_percent": max(disk_values) if disk_values else None,
        "load_1m": _number(cpu.get("load_1m")),
        "docker_running": int(docker.get("containers_running") or 0) if docker else None,
        "docker_total": int(docker.get("containers_total") or 0) if docker else None,
    }


def _current_alerts(server: InfrastructureServer, agent: InfrastructureServerAgent | None) -> list[dict]:
    alerts: list[dict] = []
    now = datetime.now(timezone.utc)
    if agent is None:
        return [{"code": "agent_missing", "severity": "warning", "message": "Server agent is not configured."}]
    seen = agent.last_seen_at if agent.last_seen_at and agent.last_seen_at.tzinfo else (agent.last_seen_at.replace(tzinfo=timezone.utc) if agent.last_seen_at else None)
    if seen is None or now - seen > timedelta(minutes=max(2, server.offline_alert_minutes)):
        alerts.append({"code": "agent_offline", "severity": "critical", "message": f"No server heartbeat within {server.offline_alert_minutes} minutes."})
    try:
        telemetry = json.loads(agent.telemetry_json or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        telemetry = {}
    values = _telemetry_values(telemetry)
    if values["cpu_percent"] is not None and values["cpu_percent"] >= server.cpu_alert_percent:
        alerts.append({"code": "cpu_high", "severity": "warning", "message": f"CPU usage is {values['cpu_percent']:.1f}% (threshold {server.cpu_alert_percent}%)."})
    if values["memory_percent"] is not None and values["memory_percent"] >= server.memory_alert_percent:
        alerts.append({"code": "memory_high", "severity": "warning", "message": f"RAM usage is {values['memory_percent']:.1f}% (threshold {server.memory_alert_percent}%)."})
    if values["disk_percent"] is not None and values["disk_percent"] >= server.disk_alert_percent:
        alerts.append({"code": "disk_pressure", "severity": "critical", "message": f"Disk usage reached {values['disk_percent']:.1f}% (threshold {server.disk_alert_percent}%)."})
    docker = telemetry.get("docker") if isinstance(telemetry.get("docker"), dict) else {}
    if "application" in _json_roles(server.roles_json) and docker.get("installed") and not docker.get("reachable"):
        alerts.append({"code": "docker_unavailable", "severity": "critical", "message": "Docker is installed but the daemon is not reachable."})
    return alerts


def _hosting_allocated(db: Session, node_id: UUID) -> dict:
    row = db.execute(
        select(
            func.coalesce(func.sum(HostingProject.storage_mb), 0),
            func.coalesce(func.sum(HostingProject.memory_mb), 0),
            func.coalesce(func.sum(HostingProject.cpu_millicores), 0),
            func.count(HostingProject.id),
        ).where(HostingProject.node_id == node_id)
    ).one()
    database_storage = int(
        db.scalar(
            select(func.coalesce(func.sum(HostingDatabase.storage_mb), 0)).where(
                HostingDatabase.node_id == node_id,
                HostingDatabase.status != "deleting",
            )
        )
        or 0
    )
    return {
        "storage_mb": int(row[0]) + database_storage,
        "application_storage_mb": int(row[0]),
        "database_storage_mb": database_storage,
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
        "thresholds": {
            "cpu_percent": server.cpu_alert_percent,
            "memory_percent": server.memory_alert_percent,
            "disk_percent": server.disk_alert_percent,
            "offline_minutes": server.offline_alert_minutes,
        },
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
        "alerts": _current_alerts(server, server_agent),
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


def _network_probe_targets(server: InfrastructureServer) -> list[dict]:
    host = (server.public_ip or server.hostname or "").strip()
    if not host or server.status == "disabled":
        return []
    roles = set(_json_roles(server.roles_json))
    targets: list[dict] = []
    if "mail" in roles:
        targets.extend([
            {"id": f"{server.id}:smtp", "host": host, "port": 25, "timeout_ms": 1500},
            {"id": f"{server.id}:imaps", "host": host, "port": 993, "timeout_ms": 1500},
        ])
    if "application" in roles:
        targets.append(
            {"id": f"{server.id}:https", "host": host, "port": 443, "timeout_ms": 1500}
        )
    return targets


@router.get("/servers")
def list_servers(db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    rows = db.scalars(select(InfrastructureServer).order_by(InfrastructureServer.name.asc())).all()
    return {
        "items": [_server_out(db, row) for row in rows],
        "roles": sorted(ALLOWED_ROLES),
        "heartbeat_grace_seconds": HEARTBEAT_GRACE_SECONDS,
    }


@router.get("/servers/network-health")
def server_network_health(
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    servers = db.scalars(
        select(InfrastructureServer)
        .where(InfrastructureServer.status != "disabled")
        .order_by(InfrastructureServer.name.asc())
    ).all()
    targets: list[dict] = []
    labels: dict[str, tuple[str, str]] = {}
    for server in servers:
        for target in _network_probe_targets(server):
            targets.append(target)
            service = target["id"].rsplit(":", 1)[-1]
            labels[target["id"]] = (str(server.id), service)

    if not targets:
        return {"engine": "python", "checked": 0, "servers": []}

    execution = execute_network(targets, concurrency=24)
    grouped: dict[str, dict] = {}
    by_id = {str(server.id): server for server in servers}
    for result in execution.value.get("results", []):
        target_id = str(result.get("id") or "")
        mapping = labels.get(target_id)
        if mapping is None:
            continue
        server_id, service = mapping
        server = by_id.get(server_id)
        if server is None:
            continue
        row = grouped.setdefault(
            server_id,
            {
                "server_id": server_id,
                "name": server.name,
                "hostname": server.hostname,
                "public_ip": server.public_ip,
                "checks": [],
            },
        )
        row["checks"].append(
            {
                "service": service,
                "port": result.get("port"),
                "reachable": bool(result.get("reachable")),
                "latency_ms": result.get("latency_ms"),
                "error": result.get("error"),
            }
        )

    rows = list(grouped.values())
    for row in rows:
        row["reachable"] = all(check["reachable"] for check in row["checks"])
    return {
        "engine": execution.engine,
        "checked": int(execution.value.get("checked") or 0),
        "servers": rows,
        "advisory_only": True,
    }


@router.get("/servers/{server_id}")
def get_server(server_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    server = db.get(InfrastructureServer, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Infrastructure server not found")
    return _server_out(db, server)


@router.get("/servers/{server_id}/history")
def get_server_history(
    server_id: UUID,
    hours: int = 24,
    limit: int = 288,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    server = db.get(InfrastructureServer, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Infrastructure server not found")
    hours = max(1, min(hours, 168))
    limit = max(12, min(limit, 2000))
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = db.scalars(
        select(InfrastructureTelemetrySnapshot)
        .where(
            InfrastructureTelemetrySnapshot.server_id == server.id,
            InfrastructureTelemetrySnapshot.created_at >= since,
        )
        .order_by(InfrastructureTelemetrySnapshot.created_at.asc())
        .limit(limit)
    ).all()
    return {
        "server_id": str(server.id),
        "hours": hours,
        "items": [
            {
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "cpu_percent": row.cpu_percent,
                "memory_percent": row.memory_percent,
                "disk_percent": row.disk_percent,
                "load_1m": row.load_1m,
                "docker_running": row.docker_running,
                "docker_total": row.docker_total,
            }
            for row in rows
        ],
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


def _cluster_node_out(db: Session, server: InfrastructureServer, *, self_server_id: UUID) -> dict:
    """Return the sanitized node view shared with trusted Ithute server agents.

    Cluster awareness deliberately contains operational discovery data only.
    It never exposes agent credentials, environment variables, private keys,
    command queues, audit history, or customer secrets.
    """
    view = _server_out(db, server)
    peer = db.scalar(
        select(InfrastructureWireGuardPeer).where(
            InfrastructureWireGuardPeer.server_id == server.id,
            InfrastructureWireGuardPeer.status == "active",
        )
    )
    telemetry = view["agent"]["telemetry"] if isinstance(view["agent"].get("telemetry"), dict) else {}
    docker = telemetry.get("docker") if isinstance(telemetry.get("docker"), dict) else {}
    raw_containers = docker.get("containers") if isinstance(docker.get("containers"), list) else []
    containers: list[dict] = []
    for item in raw_containers[:250]:
        if not isinstance(item, dict):
            continue
        labels = item.get("labels") if isinstance(item.get("labels"), dict) else {}
        containers.append({
            "name": str(item.get("name") or "")[:160],
            "image": str(item.get("image") or "")[:500],
            "state": str(item.get("state") or "")[:32],
            "project_id": str(labels.get("ithute.project_id") or "")[:80] or None,
        })

    resource_usage = _telemetry_values(telemetry)
    capabilities = view["agent"]["capabilities"] if isinstance(view["agent"].get("capabilities"), dict) else {}
    safe_capabilities = {
        str(key)[:80]: value
        for key, value in capabilities.items()
        if isinstance(value, (bool, int, float, str)) and len(str(key)) <= 80
    }

    return {
        "server_id": view["id"],
        "self": server.id == self_server_id,
        "name": view["name"],
        "hostname": view["hostname"],
        "region": view["region"],
        "provider": view["provider"],
        "roles": view["roles"],
        "status": view["status"],
        "health": view["health"],
        "online": bool(view["agent"]["online"]),
        "last_seen_at": view["agent"]["last_seen_at"],
        "private_network": {
            "interface": "ithute0",
            "ipv4": peer.assigned_ipv4 if peer else None,
            "connected": bool(
                peer
                and peer.last_handshake_at
                and _fresh(peer.last_handshake_at)
            ),
            "last_handshake_at": peer.last_handshake_at.isoformat() if peer and peer.last_handshake_at else None,
        },
        "workloads": view["workloads"],
        "hosting": {
            "linked": view["hosting"]["linked"],
            "status": view["hosting"]["status"],
            "online": view["hosting"]["online"],
            "accepts_new_projects": view["hosting"]["accepts_new_projects"],
            "capacity": view["hosting"]["capacity"],
        },
        "mail": {
            "linked": view["mail"]["linked"],
            "status": view["mail"]["status"],
            "online": view["mail"]["online"],
            "ready": view["mail"]["ready"],
        },
        "resource_usage": resource_usage,
        "capabilities": safe_capabilities,
        "docker": {
            "installed": bool(docker.get("installed")),
            "reachable": bool(docker.get("reachable")),
            "version": str(docker.get("version") or "")[:80] or None,
            "containers_running": int(docker.get("containers_running") or 0),
            "containers_total": int(docker.get("containers_total") or 0),
            "containers": containers,
        },
    }


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


def _cluster_reachability(servers: list[InfrastructureServer]) -> tuple[str, dict[str, dict]]:
    targets: list[dict] = []
    labels: dict[str, tuple[str, str]] = {}
    for server in servers:
        for target in _network_probe_targets(server):
            if len(targets) >= 64:
                break
            targets.append(target)
            labels[str(target["id"])] = (str(server.id), str(target["id"]).rsplit(":", 1)[-1])
        if len(targets) >= 64:
            break

    if not targets:
        return "python", {}

    execution = execute_network(targets, concurrency=min(24, len(targets)))
    grouped: dict[str, dict] = {}
    results = execution.value.get("results", []) if isinstance(execution.value, dict) else []
    for item in results:
        if not isinstance(item, dict):
            continue
        mapping = labels.get(str(item.get("id") or ""))
        if mapping is None:
            continue
        server_id, service = mapping
        node = grouped.setdefault(server_id, {"services": {}, "reachable": True, "checked": 0})
        reachable = bool(item.get("reachable"))
        node["services"][service] = {
            "reachable": reachable,
            "latency_ms": item.get("latency_ms"),
        }
        node["reachable"] = bool(node["reachable"] and reachable)
        node["checked"] += 1
    return execution.engine, grouped


@router.get("/agent/cluster-state")
def infrastructure_agent_cluster_state(
    x_ithute_server_agent: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    _agent, current_server = _server_agent_from_token(db, x_ithute_server_agent)
    rows = db.scalars(
        select(InfrastructureServer)
        .where(InfrastructureServer.status != "disabled")
        .order_by(InfrastructureServer.name.asc())
    ).all()
    reachability_engine, reachability = _cluster_reachability(list(rows))
    nodes = [_cluster_node_out(db, row, self_server_id=current_server.id) for row in rows]
    node_by_id = {str(node["server_id"]): node for node in nodes}
    for node in nodes:
        live = reachability.get(str(node["server_id"]), {"services": {}, "reachable": None, "checked": 0})
        node["reachability"] = {
            "engine": reachability_engine,
            "reachable": live["reachable"],
            "checked": live["checked"],
            "services": live["services"],
        }
        node["communication"] = {
            "mode": "full_mesh",
            "default": "allow",
            "peers": [],
            "service_metadata": {"outbound": [], "inbound": []},
        }

    enrolled_nodes = [
        node for node in nodes
        if isinstance(node.get("private_network"), dict) and node["private_network"].get("ipv4")
    ]
    for node in enrolled_nodes:
        node["communication"]["peers"] = [
            {
                "server_id": peer["server_id"],
                "name": peer["name"],
                "ipv4": peer["private_network"]["ipv4"],
            }
            for peer in enrolled_nodes
            if peer["server_id"] != node["server_id"]
        ]

    grants = db.scalars(
        select(InfrastructureNetworkGrant)
        .where(InfrastructureNetworkGrant.enabled.is_(True))
        .order_by(InfrastructureNetworkGrant.created_at.asc())
    ).all()
    for grant in grants:
        source_id = str(grant.source_server_id)
        target_id = str(grant.target_server_id)
        source_node = node_by_id.get(source_id)
        target_node = node_by_id.get(target_id)
        if source_node is None or target_node is None:
            continue
        flow = {
            "peer_server_id": target_id,
            "peer_name": target_node["name"],
            "protocol": grant.protocol,
            "port": grant.port,
            "service": grant.service,
        }
        source_node["communication"]["service_metadata"]["outbound"].append(flow)
        target_node["communication"]["service_metadata"]["inbound"].append({
            **flow,
            "peer_server_id": source_id,
            "peer_name": source_node["name"],
        })
    generated_at = datetime.now(timezone.utc).isoformat()
    unsigned = {
        "version": 1,
        "generated_at": generated_at,
        "self_server_id": str(current_server.id),
        "node_count": len(nodes),
        "reachability_engine": reachability_engine,
        "nodes": nodes,
    }
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = execute_binary("crypto.sha256", canonical)
    signature = execute_hmac_sha256((x_ithute_server_agent or "").encode("utf-8"), canonical)
    return {
        **unsigned,
        "fingerprint_sha256": str(digest.value),
        "fingerprint_engine": digest.engine,
        "signature_hmac_sha256": str(signature.value),
        "signature_engine": signature.engine,
    }


@router.get("/cluster-graph/summary")
def cluster_graph_summary(
    source_server_id: UUID | None = None,
    target_server_id: UUID | None = None,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    if (source_server_id is None) != (target_server_id is None):
        raise HTTPException(status_code=422, detail="Provide both source_server_id and target_server_id for a reachability query")

    rows = db.scalars(
        select(InfrastructureServer)
        .where(InfrastructureServer.status != "disabled")
        .order_by(InfrastructureServer.name.asc())
    ).all()

    nodes: list[dict] = []
    for server in rows:
        agent = db.get(InfrastructureServerAgent, server.id)
        try:
            telemetry = json.loads(agent.telemetry_json or "{}") if agent else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            telemetry = {}
        cpu = telemetry.get("cpu") if isinstance(telemetry.get("cpu"), dict) else {}
        memory = telemetry.get("memory") if isinstance(telemetry.get("memory"), dict) else {}
        disks = telemetry.get("disks") if isinstance(telemetry.get("disks"), list) else []
        storage_total = 0
        storage_used = 0
        for disk in disks[:128]:
            if not isinstance(disk, dict):
                continue
            try:
                storage_total += max(0, int(disk.get("total_bytes") or 0))
                storage_used += max(0, int(disk.get("used_bytes") or 0))
            except (TypeError, ValueError, OverflowError):
                continue
        peer = db.scalar(
            select(InfrastructureWireGuardPeer).where(
                InfrastructureWireGuardPeer.server_id == server.id,
                InfrastructureWireGuardPeer.status == "active",
            )
        )
        online = bool(agent and agent.last_seen_at and _fresh(agent.last_seen_at))
        nodes.append({
            "id": str(server.id),
            "name": server.name,
            "private_ip": peer.assigned_ipv4 if peer else "",
            "status": server.status,
            "online": online,
            "healthy": bool(online and server.status == "active"),
            "cpu_used_percent": cpu.get("used_percent"),
            "memory_total_bytes": memory.get("total_bytes"),
            "memory_used_bytes": memory.get("used_bytes"),
            "storage_total_bytes": storage_total,
            "storage_used_bytes": storage_used,
        })

    grants = db.scalars(
        select(InfrastructureNetworkGrant)
        .where(InfrastructureNetworkGrant.enabled.is_(True))
        .order_by(InfrastructureNetworkGrant.created_at.asc())
    ).all()
    edges = [
        {
            "source": str(grant.source_server_id),
            "target": str(grant.target_server_id),
            "relation": "communicates_with",
            "service": grant.service,
            "protocol": grant.protocol,
            "port": grant.port,
        }
        for grant in grants
    ]

    analysis = cluster_graph_analysis(
        nodes,
        edges,
        source=str(source_server_id) if source_server_id else None,
        target=str(target_server_id) if target_server_id else None,
    )
    return {
        "topology": "sanitized-operational",
        "network_policy": "full_mesh",
        "relationship_edges": "service_metadata",
        **analysis,
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

    wireguard = payload.telemetry.get("wireguard") if isinstance(payload.telemetry.get("wireguard"), dict) else {}
    handshake = wireguard.get("latest_handshake_unix")
    handshake_at = None
    try:
        if handshake:
            handshake_at = datetime.fromtimestamp(int(handshake), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        handshake_at = None
    update_peer_telemetry(
        db,
        server.id,
        latest_handshake_at=handshake_at,
        rx_bytes=int(wireguard["rx_bytes"]) if wireguard.get("rx_bytes") is not None else None,
        tx_bytes=int(wireguard["tx_bytes"]) if wireguard.get("tx_bytes") is not None else None,
    )

    now = agent.last_seen_at
    topology_saved = persist_topology_observations(
        db,
        source_server=server,
        payload=payload.telemetry.get("network_topology"),
        now=now,
    )
    latest = db.scalar(
        select(InfrastructureTelemetrySnapshot)
        .where(InfrastructureTelemetrySnapshot.server_id == server.id)
        .order_by(InfrastructureTelemetrySnapshot.created_at.desc())
    )
    container_drift = _container_drift(db, server, payload.telemetry)
    security = _security_findings(payload.telemetry)
    if latest is None or not latest.created_at or now - (latest.created_at if latest.created_at.tzinfo else latest.created_at.replace(tzinfo=timezone.utc)) >= timedelta(minutes=5):
        values = _telemetry_values(payload.telemetry)
        db.add(InfrastructureTelemetrySnapshot(server_id=server.id, **values))
        db.add(
            InfrastructureContainerSnapshot(
                server_id=server.id,
                containers_json=json.dumps(container_drift["containers"], sort_keys=True, separators=(",", ":")),
                expected_count=container_drift["expected_count"],
                running_count=container_drift["running_count"],
                missing_count=container_drift["missing_count"],
                unexpected_count=container_drift["unexpected_count"],
                drift_status=container_drift["drift_status"],
            )
        )
        db.add(
            InfrastructureSecuritySnapshot(
                server_id=server.id,
                score=security["score"],
                posture=security["posture"],
                findings_json=json.dumps(security["findings"], sort_keys=True, separators=(",", ":")),
                fingerprint_sha256=security["fingerprint_sha256"],
            )
        )
        db.execute(
            delete(InfrastructureTelemetrySnapshot).where(
                InfrastructureTelemetrySnapshot.server_id == server.id,
                InfrastructureTelemetrySnapshot.created_at < now - timedelta(days=7),
            )
        )
        db.execute(
            delete(InfrastructureContainerSnapshot).where(
                InfrastructureContainerSnapshot.server_id == server.id,
                InfrastructureContainerSnapshot.created_at < now - timedelta(days=7),
            )
        )
        db.execute(
            delete(InfrastructureSecuritySnapshot).where(
                InfrastructureSecuritySnapshot.server_id == server.id,
                InfrastructureSecuritySnapshot.created_at < now - timedelta(days=30),
            )
        )
    db.commit()
    return {
        "ok": True,
        "server_id": str(server.id),
        "status": server.status,
        "container_drift": {
            key: value for key, value in container_drift.items() if key != "containers"
        },
        "security": {
            "score": security["score"],
            "posture": security["posture"],
            "findings": len(security["findings"]),
            "fingerprint_engine": security["fingerprint_engine"],
        },
        "network_topology_observations_saved": topology_saved,
    }


@router.get("/servers/{server_id}/security")
def server_security_posture(
    server_id: UUID,
    limit: int = 20,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    server = db.get(InfrastructureServer, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Infrastructure server not found")
    rows = db.scalars(
        select(InfrastructureSecuritySnapshot)
        .where(InfrastructureSecuritySnapshot.server_id == server.id)
        .order_by(InfrastructureSecuritySnapshot.created_at.desc())
        .limit(max(1, min(limit, 100)))
    ).all()
    return {
        "server_id": str(server.id),
        "items": [
            {
                "score": row.score,
                "posture": row.posture,
                "findings": json.loads(row.findings_json or "[]"),
                "fingerprint_sha256": row.fingerprint_sha256,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
    }


@router.get("/servers/{server_id}/readiness")
def server_readiness(
    server_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    server = db.get(InfrastructureServer, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Infrastructure server not found")
    return _readiness_for_server(db, server)


@router.get("/servers/{server_id}/commands")
def list_server_commands(
    server_id: UUID,
    limit: int = 50,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    server = db.get(InfrastructureServer, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Infrastructure server not found")
    rows = db.scalars(
        select(InfrastructureAgentCommand)
        .where(InfrastructureAgentCommand.server_id == server.id)
        .order_by(InfrastructureAgentCommand.created_at.desc())
        .limit(max(1, min(limit, 200)))
    ).all()
    return {"items": [_command_out(row) for row in rows], "allowed_kinds": sorted(AGENT_COMMAND_KINDS)}


@router.post("/servers/{server_id}/commands", status_code=201)
def queue_server_command(
    server_id: UUID,
    payload: InfrastructureAgentCommandCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    server = db.get(InfrastructureServer, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Infrastructure server not found")
    agent = db.get(InfrastructureServerAgent, server.id)
    if agent is None:
        raise HTTPException(status_code=409, detail="Infrastructure server agent is not configured")
    kind, clean_payload = _validated_agent_command(payload.kind, payload.payload)
    row = InfrastructureAgentCommand(
        server_id=server.id,
        kind=kind,
        payload_json=json.dumps(clean_payload, sort_keys=True, separators=(",", ":")),
        requested_by_user_id=current.id,
    )
    db.add(row)
    db.flush()
    _audit(db, current, "infrastructure.server_agent.command.queue", server, {"command_id": str(row.id), "kind": kind})
    db.commit()
    db.refresh(row)
    return _command_out(row)


@router.post("/agent/commands/next")
def claim_infrastructure_agent_command(
    x_ithute_server_agent: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    agent, server = _server_agent_from_token(db, x_ithute_server_agent)
    row = db.scalar(
        select(InfrastructureAgentCommand)
        .where(
            InfrastructureAgentCommand.server_id == server.id,
            InfrastructureAgentCommand.status == "queued",
        )
        .order_by(InfrastructureAgentCommand.created_at.asc())
        .with_for_update(skip_locked=True)
    )
    if row is None:
        return {"command": None}
    row.status = "claimed"
    row.claimed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return {"command": _command_out(row)}


@router.post("/agent/commands/{command_id}/result")
def complete_infrastructure_agent_command(
    command_id: UUID,
    payload: InfrastructureAgentCommandResult,
    x_ithute_server_agent: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    agent, server = _server_agent_from_token(db, x_ithute_server_agent)
    row = db.scalar(
        select(InfrastructureAgentCommand)
        .where(
            InfrastructureAgentCommand.id == command_id,
            InfrastructureAgentCommand.server_id == server.id,
        )
        .with_for_update()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Infrastructure agent command not found")
    if row.status not in {"claimed", "queued"}:
        raise HTTPException(status_code=409, detail="Infrastructure agent command is already complete")
    row.status = "succeeded" if payload.ok else "failed"
    row.result_json = json.dumps(payload.result, sort_keys=True, separators=(",", ":"))
    row.error = payload.error.strip()[:8000] if payload.error else None
    row.completed_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "command": _command_out(row)}


@router.get("/servers/{server_id}/container-inventory")
def server_container_inventory(
    server_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    server = db.get(InfrastructureServer, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Infrastructure server not found")
    latest = db.scalar(
        select(InfrastructureContainerSnapshot)
        .where(InfrastructureContainerSnapshot.server_id == server.id)
        .order_by(InfrastructureContainerSnapshot.created_at.desc())
    )
    if latest is None:
        return {"server_id": str(server.id), "status": "awaiting_agent", "containers": []}
    return {
        "server_id": str(server.id),
        "status": latest.drift_status,
        "expected_count": latest.expected_count,
        "running_count": latest.running_count,
        "missing_count": latest.missing_count,
        "unexpected_count": latest.unexpected_count,
        "containers": json.loads(latest.containers_json or "[]"),
        "checked_at": latest.created_at.isoformat() if latest.created_at else None,
    }


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
