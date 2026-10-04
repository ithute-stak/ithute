from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    HostingNode,
    HostingNodeAgent,
    HostingNodeHealthState,
    HostingProjectOperation,
    InfrastructureServer,
    InfrastructureServerAgent,
    InfrastructureWireGuardPeer,
)

HEARTBEAT_GRACE_SECONDS = int(os.getenv("ITHUTE_HOSTING_HEALTH_HEARTBEAT_SECONDS", "180"))
AUTO_ACTIVATE_SECONDS = int(os.getenv("ITHUTE_HOSTING_AUTO_ACTIVATE_SECONDS", "120"))
AUTO_DRAIN_SECONDS = int(os.getenv("ITHUTE_HOSTING_AUTO_DRAIN_SECONDS", "60"))
AUTO_RECOVER_SECONDS = int(os.getenv("ITHUTE_HOSTING_AUTO_RECOVER_SECONDS", "180"))


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _fresh(value: datetime | None, now: datetime) -> bool:
    current = _utc(value)
    return bool(current and current >= now - timedelta(seconds=HEARTBEAT_GRACE_SECONDS))


def _telemetry(agent: InfrastructureServerAgent | None) -> dict:
    if agent is None:
        return {}
    try:
        value = json.loads(agent.telemetry_json or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _max_disk_percent(telemetry: dict) -> float | None:
    disks = telemetry.get("disks") if isinstance(telemetry.get("disks"), list) else []
    values: list[float] = []
    for item in disks:
        if not isinstance(item, dict):
            continue
        try:
            if item.get("used_percent") is not None:
                values.append(float(item["used_percent"]))
        except (TypeError, ValueError):
            continue
    return max(values) if values else None


def ensure_health_state(db: Session, node: HostingNode, *, enable: bool | None = None, reset: bool = False) -> HostingNodeHealthState:
    state = db.get(HostingNodeHealthState, node.id)
    if state is None:
        state = HostingNodeHealthState(node_id=node.id, automation_enabled=True if enable is None else enable)
        db.add(state)
        db.flush()
    elif enable is not None:
        state.automation_enabled = enable
    if reset:
        state.health_status = "unknown"
        state.healthy_since = None
        state.unhealthy_since = None
        state.last_evaluated_at = None
        state.last_reason = None
    return state


def evaluate_node_health(db: Session, node: HostingNode, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    hosting_agent = db.get(HostingNodeAgent, node.id)
    server = db.scalar(select(InfrastructureServer).where(InfrastructureServer.hosting_node_id == node.id))
    server_agent = db.get(InfrastructureServerAgent, server.id) if server else None
    peer = db.scalar(select(InfrastructureWireGuardPeer).where(InfrastructureWireGuardPeer.server_id == server.id)) if server else None
    telemetry = _telemetry(server_agent)
    wireguard = telemetry.get("wireguard") if isinstance(telemetry.get("wireguard"), dict) else {}
    docker = telemetry.get("docker") if isinstance(telemetry.get("docker"), dict) else {}

    hosting_agent_online = bool(hosting_agent and _fresh(hosting_agent.last_seen_at, now))
    server_agent_online = bool(server_agent and _fresh(server_agent.last_seen_at, now))
    infrastructure_active = bool(server and server.status == "active")
    origin_ready = bool(hosting_agent and hosting_agent.origin_bind_ip)

    if peer is None:
        managed_network_connected = True
        handshake_fresh = True
        address_matches = True
    else:
        address_matches = wireguard.get("address") == peer.assigned_ipv4
        handshake_fresh = _fresh(peer.last_handshake_at, now)
        managed_network_connected = bool(wireguard.get("connected") and address_matches and handshake_fresh)

    docker_ready = bool(docker.get("installed") and docker.get("reachable"))
    disk_percent = _max_disk_percent(telemetry)
    disk_safe = bool(server and (disk_percent is None or disk_percent < float(server.disk_alert_percent)))
    stale_retirements = int(
        db.scalar(
            select(func.count(HostingProjectOperation.id)).where(
                HostingProjectOperation.node_id == node.id,
                HostingProjectOperation.operation == "retire",
                HostingProjectOperation.status.in_(["queued", "claimed"]),
            )
        )
        or 0
    )
    stale_retirements_cleared = stale_retirements == 0

    checks = {
        "hosting_agent_online": hosting_agent_online,
        "server_agent_online": server_agent_online,
        "infrastructure_linked": server is not None,
        "infrastructure_active": infrastructure_active,
        "private_origin_configured": origin_ready,
        "managed_network_connected": managed_network_connected,
        "docker_ready": docker_ready,
        "disk_safe": disk_safe,
        "stale_retirements_cleared": stale_retirements_cleared,
    }
    reasons = [name for name, passed in checks.items() if not passed]
    return {
        "healthy": all(checks.values()),
        "checks": checks,
        "reasons": reasons,
        "server_id": str(server.id) if server else None,
        "managed_network_ip": peer.assigned_ipv4 if peer else None,
        "last_handshake_at": _utc(peer.last_handshake_at).isoformat() if peer and peer.last_handshake_at else None,
        "disk_percent": disk_percent,
    }


def _audit(db: Session, node: HostingNode, action: str, metadata: dict) -> None:
    db.add(
        AuditLog(
            actor_user_id=None,
            action=action,
            resource_type="hosting_node",
            resource_id=str(node.id),
            metadata_json=json.dumps(metadata, sort_keys=True),
        )
    )


def node_health_snapshot(db: Session, node: HostingNode, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    state = db.get(HostingNodeHealthState, node.id)
    health = evaluate_node_health(db, node, now=now)
    return {
        "node_id": str(node.id),
        "automation_enabled": bool(state.automation_enabled) if state else False,
        "health_status": state.health_status if state else ("healthy" if health["healthy"] else "unhealthy"),
        "healthy": health["healthy"],
        "checks": health["checks"],
        "reasons": health["reasons"],
        "node_status": node.status,
        "accepts_new_projects": node.accepts_new_projects,
        "healthy_since": _utc(state.healthy_since).isoformat() if state and state.healthy_since else None,
        "unhealthy_since": _utc(state.unhealthy_since).isoformat() if state and state.unhealthy_since else None,
        "last_evaluated_at": _utc(state.last_evaluated_at).isoformat() if state and state.last_evaluated_at else None,
        "last_transition": state.last_transition if state else None,
        "last_transition_at": _utc(state.last_transition_at).isoformat() if state and state.last_transition_at else None,
        "last_reason": state.last_reason if state else None,
        "thresholds": {
            "heartbeat_grace_seconds": HEARTBEAT_GRACE_SECONDS,
            "auto_activate_seconds": AUTO_ACTIVATE_SECONDS,
            "auto_drain_seconds": AUTO_DRAIN_SECONDS,
            "auto_recover_seconds": AUTO_RECOVER_SECONDS,
        },
        **{key: health[key] for key in ("server_id", "managed_network_ip", "last_handshake_at", "disk_percent")},
    }


def reconcile_node_health(db: Session, node: HostingNode, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    state = ensure_health_state(db, node)
    health = evaluate_node_health(db, node, now=now)
    state.last_evaluated_at = now

    if health["healthy"]:
        state.health_status = "healthy"
        state.unhealthy_since = None
        state.last_reason = None
        if state.healthy_since is None:
            state.healthy_since = now

        if state.automation_enabled and (node.status != "active" or not node.accepts_new_projects):
            threshold = AUTO_RECOVER_SECONDS if state.last_transition == "auto_drained" else AUTO_ACTIVATE_SECONDS
            healthy_since = _utc(state.healthy_since) or now
            if (now - healthy_since).total_seconds() >= threshold:
                transition = "auto_recovered" if state.last_transition == "auto_drained" else "auto_activated"
                node.status = "active"
                node.accepts_new_projects = True
                state.last_transition = transition
                state.last_transition_at = now
                _audit(db, node, f"hosting.node_health.{transition}", {
                    "healthy_for_seconds": int((now - healthy_since).total_seconds()),
                    "checks": health["checks"],
                })
    else:
        state.health_status = "unhealthy"
        state.healthy_since = None
        state.last_reason = ", ".join(health["reasons"])
        if state.unhealthy_since is None:
            state.unhealthy_since = now

        if state.automation_enabled and node.status == "active" and node.accepts_new_projects:
            unhealthy_since = _utc(state.unhealthy_since) or now
            if (now - unhealthy_since).total_seconds() >= AUTO_DRAIN_SECONDS:
                node.status = "draining"
                node.accepts_new_projects = False
                state.last_transition = "auto_drained"
                state.last_transition_at = now
                _audit(db, node, "hosting.node_health.auto_drained", {
                    "unhealthy_for_seconds": int((now - unhealthy_since).total_seconds()),
                    "reasons": health["reasons"],
                    "checks": health["checks"],
                })

    return {
        "node_id": str(node.id),
        "automation_enabled": state.automation_enabled,
        "health_status": state.health_status,
        "healthy": health["healthy"],
        "checks": health["checks"],
        "reasons": health["reasons"],
        "node_status": node.status,
        "accepts_new_projects": node.accepts_new_projects,
        "healthy_since": _utc(state.healthy_since).isoformat() if state.healthy_since else None,
        "unhealthy_since": _utc(state.unhealthy_since).isoformat() if state.unhealthy_since else None,
        "last_evaluated_at": _utc(state.last_evaluated_at).isoformat() if state.last_evaluated_at else None,
        "last_transition": state.last_transition,
        "last_transition_at": _utc(state.last_transition_at).isoformat() if state.last_transition_at else None,
        "last_reason": state.last_reason,
        "thresholds": {
            "heartbeat_grace_seconds": HEARTBEAT_GRACE_SECONDS,
            "auto_activate_seconds": AUTO_ACTIVATE_SECONDS,
            "auto_drain_seconds": AUTO_DRAIN_SECONDS,
            "auto_recover_seconds": AUTO_RECOVER_SECONDS,
        },
        **{key: health[key] for key in ("server_id", "managed_network_ip", "last_handshake_at", "disk_percent")},
    }


def run_hosting_node_health_reconcile(db: Session, limit: int = 500) -> dict:
    states = db.scalars(
        select(HostingNodeHealthState)
        .where(HostingNodeHealthState.automation_enabled.is_(True))
        .limit(max(1, min(limit, 2000)))
    ).all()
    activated = drained = recovered = healthy = unhealthy = 0
    items = []
    for state in states:
        node = db.get(HostingNode, state.node_id)
        if node is None:
            continue
        before = state.last_transition
        result = reconcile_node_health(db, node)
        items.append(result)
        healthy += int(result["healthy"])
        unhealthy += int(not result["healthy"])
        if state.last_transition != before:
            if state.last_transition == "auto_activated":
                activated += 1
            elif state.last_transition == "auto_drained":
                drained += 1
            elif state.last_transition == "auto_recovered":
                recovered += 1
    db.commit()
    return {
        "checked": len(items),
        "healthy": healthy,
        "unhealthy": unhealthy,
        "activated": activated,
        "drained": drained,
        "recovered": recovered,
    }
