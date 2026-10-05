from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    HostingDatabase,
    HostingFailoverAttempt,
    HostingNode,
    HostingNodeAgent,
    HostingProject,
    BillingPlan,
    InfrastructureCommercialProfile,
    InfrastructureSecuritySnapshot,
    InfrastructureServer,
    InfrastructureServerAgent,
    TenantInfrastructureAllocation,
    TenantSubscription,
)

HEARTBEAT_GRACE = timedelta(minutes=3)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fresh(value: datetime | None) -> bool:
    if value is None:
        return False
    current = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return current >= _now() - HEARTBEAT_GRACE


def _json(raw: str | None) -> dict:
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _allocated(db: Session, node_id: UUID) -> dict:
    app_row = db.execute(
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
    reserved = db.execute(
        select(
            func.coalesce(func.sum(HostingProject.storage_mb), 0),
            func.coalesce(func.sum(HostingProject.memory_mb), 0),
            func.coalesce(func.sum(HostingProject.cpu_millicores), 0),
            func.count(HostingProject.id),
        )
        .join(HostingFailoverAttempt, HostingFailoverAttempt.project_id == HostingProject.id)
        .where(
            HostingFailoverAttempt.target_node_id == node_id,
            HostingFailoverAttempt.status.in_(["pending", "deploying", "edge_pending"]),
            HostingProject.node_id != node_id,
        )
    ).one()
    reserved_storage = int(reserved[0])
    reserved_memory = int(reserved[1])
    reserved_cpu = int(reserved[2])
    return {
        "app_storage_mb": int(app_row[0]),
        "database_storage_mb": database_storage,
        "failover_reserved_storage_mb": reserved_storage,
        "storage_mb": int(app_row[0]) + database_storage + reserved_storage,
        "memory_mb": int(app_row[1]) + reserved_memory,
        "cpu_millicores": int(app_row[2]) + reserved_cpu,
        "projects": int(app_row[3]) + int(reserved[3]),
    }


def _infrastructure_for_hosting_node(db: Session, node_id: UUID) -> tuple[InfrastructureServer | None, InfrastructureServerAgent | None]:
    server = db.scalar(select(InfrastructureServer).where(InfrastructureServer.hosting_node_id == node_id))
    if server is None:
        return None, None
    return server, db.get(InfrastructureServerAgent, server.id)


def _percent(telemetry: dict, group: str, field: str) -> float | None:
    section = telemetry.get(group)
    if not isinstance(section, dict):
        return None
    try:
        value = section.get(field)
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _commercial_profile(db: Session, server_id: UUID | None) -> InfrastructureCommercialProfile | None:
    if server_id is None:
        return None
    return db.scalar(
        select(InfrastructureCommercialProfile).where(InfrastructureCommercialProfile.server_id == server_id)
    )


def _latest_security(db: Session, server_id: UUID | None) -> InfrastructureSecuritySnapshot | None:
    if server_id is None:
        return None
    return db.scalar(
        select(InfrastructureSecuritySnapshot)
        .where(InfrastructureSecuritySnapshot.server_id == server_id)
        .order_by(InfrastructureSecuritySnapshot.created_at.desc())
        .limit(1)
    )


def _tenant_monthly_revenue(db: Session, tenant_id: UUID | None) -> int:
    if tenant_id is None:
        return 0
    subscription = db.scalar(select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id))
    if subscription is None:
        return 0
    plan = db.get(BillingPlan, subscription.plan_id)
    return max(0, int(plan.monthly_price_minor or 0)) if plan else 0


def _estimated_incremental_cost(
    profile: InfrastructureCommercialProfile | None,
    *,
    storage_mb: int,
    memory_mb: int,
    cpu_millicores: int,
) -> int:
    if profile is None:
        return 0
    monthly_cost = sum(
        max(0, int(value or 0))
        for value in (
            profile.provider_cost_minor,
            profile.backup_cost_minor,
            profile.bandwidth_cost_minor,
            profile.other_cost_minor,
        )
    )
    if monthly_cost <= 0:
        return 0
    shares = []
    if profile.total_cpu_millicores > 0 and cpu_millicores > 0:
        shares.append((cpu_millicores / profile.total_cpu_millicores) * 0.40)
    if profile.total_memory_mb > 0 and memory_mb > 0:
        shares.append((memory_mb / profile.total_memory_mb) * 0.30)
    if profile.total_storage_mb > 0 and storage_mb > 0:
        shares.append((storage_mb / profile.total_storage_mb) * 0.30)
    weighted_share = min(1.0, sum(shares))
    return max(0, round(monthly_cost * weighted_share))


def sync_tenant_infrastructure_allocation(
    db: Session,
    *,
    tenant_id: UUID,
    server_id: UUID | None,
    actor_user_id: UUID,
) -> TenantInfrastructureAllocation | None:
    """Synchronize the commercial ledger from actual placed hosting resources.

    Manual owner allocations are never overwritten. Placement-owned allocations
    are recalculated from database truth so retries, deletes and reprovisioning
    do not inflate cost shares.
    """
    if server_id is None:
        return None
    server = db.get(InfrastructureServer, server_id)
    if server is None or server.hosting_node_id is None:
        return None

    row = db.scalar(
        select(TenantInfrastructureAllocation).where(
            TenantInfrastructureAllocation.tenant_id == tenant_id,
            TenantInfrastructureAllocation.server_id == server_id,
        )
    )
    if row is not None and row.source == "manual":
        return row

    project_totals = db.execute(
        select(
            func.coalesce(func.sum(HostingProject.cpu_millicores), 0),
            func.coalesce(func.sum(HostingProject.memory_mb), 0),
            func.coalesce(func.sum(HostingProject.storage_mb), 0),
            func.count(HostingProject.id),
        ).where(
            HostingProject.tenant_id == tenant_id,
            HostingProject.node_id == server.hosting_node_id,
            HostingProject.status != "suspended",
        )
    ).one()
    database_totals = db.execute(
        select(
            func.coalesce(func.sum(HostingDatabase.storage_mb), 0),
            func.count(HostingDatabase.id),
        ).where(
            HostingDatabase.tenant_id == tenant_id,
            HostingDatabase.node_id == server.hosting_node_id,
            HostingDatabase.status != "deleting",
        )
    ).one()

    cpu = int(project_totals[0] or 0)
    memory = int(project_totals[1] or 0)
    storage = int(project_totals[2] or 0) + int(database_totals[0] or 0)
    workload_count = int(project_totals[3] or 0) + int(database_totals[1] or 0)

    profile = _commercial_profile(db, server_id)
    weight_components: list[float] = []
    if profile:
        if profile.total_cpu_millicores > 0:
            weight_components.append((cpu / profile.total_cpu_millicores) * 4000)
        if profile.total_memory_mb > 0:
            weight_components.append((memory / profile.total_memory_mb) * 3000)
        if profile.total_storage_mb > 0:
            weight_components.append((storage / profile.total_storage_mb) * 3000)
    allocation_weight = max(1, round(sum(weight_components))) if weight_components else max(1, workload_count)

    if row is None:
        row = TenantInfrastructureAllocation(
            tenant_id=tenant_id,
            server_id=server_id,
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
            source="placement",
        )
        db.add(row)
    row.cpu_millicores = cpu
    row.memory_mb = memory
    row.storage_mb = storage
    row.bandwidth_gb = max(0, int(row.bandwidth_gb or 0))
    row.allocation_weight = allocation_weight
    row.active = workload_count > 0
    row.source = "placement"
    row.updated_by_user_id = actor_user_id
    db.flush()
    return row


def _disk_percent(telemetry: dict) -> float | None:
    rows = telemetry.get("disks")
    if not isinstance(rows, list):
        return None
    values: list[float] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            value = row.get("used_percent")
            if value is not None:
                values.append(float(value))
        except (TypeError, ValueError):
            continue
    return max(values) if values else None


def score_node(
    db: Session,
    node: HostingNode,
    *,
    workload: str,
    storage_mb: int,
    memory_mb: int = 0,
    cpu_millicores: int = 0,
    database_engine: str | None = None,
    preferred_region: str | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    allocated = _allocated(db, node.id)
    available = {
        "storage_mb": max(0, node.allocatable_storage_mb - allocated["storage_mb"]),
        "memory_mb": max(0, node.allocatable_memory_mb - allocated["memory_mb"]),
        "cpu_millicores": max(0, node.allocatable_cpu_millicores - allocated["cpu_millicores"]),
    }

    reasons: list[str] = []
    eligible = True

    agent = db.get(HostingNodeAgent, node.id)
    server, server_agent = _infrastructure_for_hosting_node(db, node.id)
    if node.status != "active":
        eligible = False
        reasons.append(f"hosting node status is {node.status}")
    if not node.accepts_new_projects:
        eligible = False
        reasons.append("node is not accepting new workloads")

    # Application allocations historically existed before a runtime agent was
    # installed. Preserve that bootstrap path only for legacy nodes that have
    # not yet joined the unified infrastructure registry. Once linked, both
    # workload and physical-server health are mandatory. Databases always need
    # a live hosting agent because provisioning is an immediate agent operation.
    if workload == "database" and (agent is None or not _fresh(agent.last_seen_at)):
        eligible = False
        reasons.append("hosting agent is offline")
    elif server is not None and (agent is None or not _fresh(agent.last_seen_at)):
        eligible = False
        reasons.append("hosting agent is offline")

    if storage_mb > available["storage_mb"]:
        eligible = False
        reasons.append("insufficient storage")
    if memory_mb > available["memory_mb"]:
        eligible = False
        reasons.append("insufficient memory")
    if cpu_millicores > available["cpu_millicores"]:
        eligible = False
        reasons.append("insufficient CPU")

    telemetry: dict = {}
    capabilities: dict = {}
    if server is not None:
        roles = set(json.loads(server.roles_json or "[]"))
        required_role = "database" if workload == "database" else "application"
        if required_role not in roles:
            eligible = False
            reasons.append(f"physical server lacks {required_role} role")
        if server.status != "active":
            eligible = False
            reasons.append(f"physical server status is {server.status}")
        if server_agent is None or not _fresh(server_agent.last_seen_at):
            eligible = False
            reasons.append("physical server telemetry agent is offline")
        else:
            telemetry = _json(server_agent.telemetry_json)
            capabilities = _json(server_agent.capabilities_json)

            cpu = _percent(telemetry, "cpu", "used_percent")
            memory = _percent(telemetry, "memory", "used_percent")
            disk = _disk_percent(telemetry)
            if cpu is not None and cpu >= server.cpu_alert_percent:
                eligible = False
                reasons.append(f"CPU pressure {cpu:.1f}%")
            if memory is not None and memory >= server.memory_alert_percent:
                eligible = False
                reasons.append(f"memory pressure {memory:.1f}%")
            if disk is not None and disk >= server.disk_alert_percent:
                eligible = False
                reasons.append(f"disk pressure {disk:.1f}%")

            if workload == "application":
                docker = telemetry.get("docker") if isinstance(telemetry.get("docker"), dict) else {}
                if not docker.get("reachable"):
                    eligible = False
                    reasons.append("Docker is unavailable")
            elif workload == "database" and database_engine:
                capability_name = "postgresql" if database_engine == "postgresql" else "mysql"
                if not capabilities.get(capability_name, False):
                    eligible = False
                    reasons.append(f"{database_engine} capability is unavailable")

    profile = _commercial_profile(db, server.id if server else None)
    security = _latest_security(db, server.id if server else None)
    commercial_penalty = 0.0
    estimated_incremental_cost_minor = 0
    estimated_margin_bps = None
    target_margin_bps = int(profile.target_margin_bps or 3000) if profile else 3000

    if server is not None:
        if security is None:
            commercial_penalty += 12.0
            reasons.append("security posture has not been measured")
        else:
            if security.posture == "critical" or security.score < 70:
                eligible = False
                reasons.append(f"security posture is {security.posture} ({security.score}/100)")
            elif security.score < 85:
                commercial_penalty += max(0.0, (85 - security.score) * 0.6)

        if profile is None:
            commercial_penalty += 10.0
        else:
            estimated_incremental_cost_minor = _estimated_incremental_cost(
                profile,
                storage_mb=storage_mb,
                memory_mb=memory_mb,
                cpu_millicores=cpu_millicores,
            )
            monthly_revenue_minor = _tenant_monthly_revenue(db, tenant_id)
            if monthly_revenue_minor > 0:
                estimated_margin_bps = round(
                    ((monthly_revenue_minor - estimated_incremental_cost_minor) / monthly_revenue_minor) * 10000
                )
                if estimated_margin_bps < target_margin_bps:
                    commercial_penalty += min(
                        35.0,
                        max(5.0, (target_margin_bps - estimated_margin_bps) / 100.0),
                    )

    # Older hosting nodes without a linked infrastructure record remain eligible
    # while migration is in progress, but receive a conservative scoring penalty.
    telemetry_penalty = 25.0 if server is None else 0.0
    if server is None and agent is None:
        telemetry_penalty += 10.0

    requested_region = (preferred_region or "").strip().lower()
    server_region = (server.region if server else "").strip().lower()
    region_match = bool(requested_region and server_region and requested_region == server_region)
    # Region is a preference rather than a hard constraint. A healthy node in the
    # requested region gets a meaningful advantage, while Ithute can still fall
    # back to another region when local capacity or health is insufficient.
    region_penalty = 0.0
    if requested_region:
        if server is None or not server_region:
            region_penalty = 12.0
        elif not region_match:
            region_penalty = 18.0

    cpu_pct = _percent(telemetry, "cpu", "used_percent") or 0.0
    memory_pct = _percent(telemetry, "memory", "used_percent") or 0.0
    disk_pct = _disk_percent(telemetry) or 0.0
    storage_util = (allocated["storage_mb"] / node.allocatable_storage_mb * 100.0) if node.allocatable_storage_mb else 100.0
    memory_util = (allocated["memory_mb"] / node.allocatable_memory_mb * 100.0) if node.allocatable_memory_mb else 100.0
    cpu_alloc_util = (allocated["cpu_millicores"] / node.allocatable_cpu_millicores * 100.0) if node.allocatable_cpu_millicores else 100.0

    # Lower is better. Runtime pressure has more weight than sellable allocation,
    # while allocation ratios keep future capacity balanced across nodes.
    score = (
        cpu_pct * 0.25
        + memory_pct * 0.25
        + disk_pct * 0.15
        + storage_util * 0.15
        + memory_util * 0.10
        + cpu_alloc_util * 0.10
        + telemetry_penalty
        + region_penalty
        + commercial_penalty
    )

    return {
        "node": node,
        "node_id": str(node.id),
        "name": node.name,
        "eligible": eligible,
        "score": round(score, 2),
        "reasons": reasons,
        "available": available,
        "allocated": allocated,
        "telemetry": {
            "cpu_percent": _percent(telemetry, "cpu", "used_percent"),
            "memory_percent": _percent(telemetry, "memory", "used_percent"),
            "disk_percent": _disk_percent(telemetry),
        },
        "location": {
            "requested_region": preferred_region,
            "server_region": server.region if server else None,
            "region_match": region_match,
            "region_penalty": region_penalty,
        },
        "infrastructure": {
            "server_id": str(server.id) if server else None,
            "server_name": server.name if server else None,
            "hostname": server.hostname if server else node.hostname,
            "provider": server.provider if server else None,
            "region": server.region if server else None,
        },
        "infrastructure_server_id": str(server.id) if server else None,
        "security": {
            "score": security.score if security else None,
            "posture": security.posture if security else "unknown",
        },
        "commercial": {
            "profile_configured": profile is not None,
            "estimated_incremental_cost_minor": estimated_incremental_cost_minor,
            "estimated_margin_bps": estimated_margin_bps,
            "target_margin_bps": target_margin_bps,
            "penalty": round(commercial_penalty, 2),
        },
    }


def rank_nodes(
    db: Session,
    *,
    workload: str,
    storage_mb: int,
    memory_mb: int = 0,
    cpu_millicores: int = 0,
    database_engine: str | None = None,
    preferred_region: str | None = None,
    tenant_id: UUID | None = None,
    lock: bool = False,
) -> list[dict]:
    query = select(HostingNode).order_by(HostingNode.name.asc())
    if lock:
        query = query.with_for_update()
    nodes = db.scalars(query).all()
    ranked = [
        score_node(
            db,
            node,
            workload=workload,
            storage_mb=storage_mb,
            memory_mb=memory_mb,
            cpu_millicores=cpu_millicores,
            database_engine=database_engine,
            preferred_region=preferred_region,
            tenant_id=tenant_id,
        )
        for node in nodes
    ]
    return sorted(ranked, key=lambda row: (not row["eligible"], row["score"], row["name"].lower()))


def select_node(
    db: Session,
    *,
    workload: str,
    storage_mb: int,
    memory_mb: int = 0,
    cpu_millicores: int = 0,
    database_engine: str | None = None,
    preferred_node_id: UUID | None = None,
    preferred_region: str | None = None,
    tenant_id: UUID | None = None,
) -> tuple[HostingNode, dict]:
    ranked = rank_nodes(
        db,
        workload=workload,
        storage_mb=storage_mb,
        memory_mb=memory_mb,
        cpu_millicores=cpu_millicores,
        database_engine=database_engine,
        preferred_region=preferred_region,
        tenant_id=tenant_id,
        lock=True,
    )

    if preferred_node_id is not None:
        match = next((row for row in ranked if row["node"].id == preferred_node_id), None)
        if match is None:
            raise HTTPException(status_code=404, detail="Selected hosting node not found")
        if not match["eligible"]:
            raise HTTPException(status_code=409, detail="Selected hosting node is not safe for this workload: " + "; ".join(match["reasons"]))
        return match["node"], match

    best = next((row for row in ranked if row["eligible"]), None)
    if best is None:
        details = []
        for row in ranked[:5]:
            details.append(f"{row['name']}: {', '.join(row['reasons']) or 'not eligible'}")
        suffix = f" Checked nodes: {' | '.join(details)}" if details else ""
        raise HTTPException(status_code=409, detail="No healthy hosting node can safely accept this workload." + suffix)
    return best["node"], best
