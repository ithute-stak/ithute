from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    HostingDatabase,
    HostingNode,
    HostingNodeAgent,
    HostingPostgresReplicationGroup,
    HostingPostgresReplicationMember,
    HostingPostgresReplicationStandby,
    InfrastructureServer,
)
from app.services.replica_anti_affinity import anti_affinity_evaluation, anti_affinity_sort_key


GROUP_HEALTH_GRACE = timedelta(minutes=2)
MAX_GROUP_REPLAY_BACKLOG_BYTES = 64 * 1024 * 1024


def _utc(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _server_for_node(db: Session, node_id):
    return db.scalar(
        select(InfrastructureServer).where(InfrastructureServer.hosting_node_id == node_id)
    )


def _agent_capabilities(db: Session, node_id) -> dict:
    agent = db.get(HostingNodeAgent, node_id)
    if agent is None:
        return {}
    try:
        raw = json.loads(agent.capabilities_json or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def replication_group_for_database(
    db: Session,
    database_id,
) -> HostingPostgresReplicationGroup | None:
    return db.scalar(
        select(HostingPostgresReplicationGroup)
        .join(
            HostingPostgresReplicationMember,
            HostingPostgresReplicationMember.group_id == HostingPostgresReplicationGroup.id,
        )
        .where(HostingPostgresReplicationMember.database_id == database_id)
    )


def standby_evaluation(
    db: Session,
    *,
    group: HostingPostgresReplicationGroup,
    standby: HostingPostgresReplicationStandby,
    now: datetime,
) -> dict:
    reasons: list[str] = []
    checked = _utc(standby.last_checked_at)
    if standby.node_id == group.primary_node_id:
        reasons.append("standby is colocated with the primary node")
    if standby.status not in {"streaming", "ready"}:
        reasons.append(f"standby status is {standby.status}")
    if not standby.healthy:
        reasons.append("standby health is not confirmed")
    if checked is None or checked < now - GROUP_HEALTH_GRACE:
        reasons.append("standby health observation is stale")
    if standby.in_recovery is not True:
        reasons.append("standby is not confirmed to be in PostgreSQL recovery")
    if not standby.receive_lsn or not standby.replay_lsn:
        reasons.append("WAL receive/replay positions are unavailable")
    if standby.replay_backlog_bytes is None:
        reasons.append("WAL replay backlog is unknown")
    elif int(standby.replay_backlog_bytes) > MAX_GROUP_REPLAY_BACKLOG_BYTES:
        reasons.append("WAL replay backlog exceeds promotion threshold")
    if standby.telemetry_error:
        reasons.append(f"standby telemetry error: {standby.telemetry_error}")

    primary_server = _server_for_node(db, group.primary_node_id)
    standby_server = _server_for_node(db, standby.node_id)
    anti_affinity = anti_affinity_evaluation(primary_server, standby_server)
    if not anti_affinity["eligible"]:
        reasons.append(
            "standby shares a critical failure domain with the primary: "
            + ", ".join(anti_affinity["violations"])
        )

    node = db.get(HostingNode, standby.node_id)
    if node is None:
        reasons.append("standby hosting node is unavailable")
    else:
        if node.status != "active":
            reasons.append(f"standby hosting node status is {node.status}")
        if not node.accepts_new_projects:
            reasons.append("standby hosting node is not accepting workloads")

    capabilities = _agent_capabilities(db, standby.node_id)
    postgres = capabilities.get("postgres_physical_replication")
    if not isinstance(postgres, dict) or postgres.get("supported") is not True:
        reasons.append("standby agent does not advertise safe PostgreSQL physical replication")
    elif postgres.get("dedicated_cluster") is not True:
        reasons.append("standby is not configured as a dedicated PostgreSQL cluster")
    elif postgres.get("promotion_requires_source_fencing") is not True:
        reasons.append("standby agent does not require source fencing")

    return {
        "standby_id": str(standby.id),
        "node_id": str(standby.node_id),
        "node_name": node.name if node else None,
        "eligible": not reasons,
        "reasons": reasons,
        "status": standby.status,
        "healthy": standby.healthy,
        "receive_lsn": standby.receive_lsn,
        "replay_lsn": standby.replay_lsn,
        "replay_backlog_bytes": standby.replay_backlog_bytes,
        "replay_age_seconds": standby.replay_age_seconds,
        "in_recovery": standby.in_recovery,
        "last_checked_at": checked.isoformat() if checked else None,
        "anti_affinity": anti_affinity,
    }


def build_postgres_replication_group_plan(
    db: Session,
    *,
    group: HostingPostgresReplicationGroup,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    member_ids = db.scalars(
        select(HostingPostgresReplicationMember.database_id)
        .where(HostingPostgresReplicationMember.group_id == group.id)
        .order_by(HostingPostgresReplicationMember.database_id.asc())
    ).all()
    databases = db.scalars(
        select(HostingDatabase)
        .where(HostingDatabase.id.in_(member_ids))
        .order_by(HostingDatabase.database_name.asc(), HostingDatabase.id.asc())
    ).all() if member_ids else []

    standbys = db.scalars(
        select(HostingPostgresReplicationStandby)
        .where(HostingPostgresReplicationStandby.group_id == group.id)
        .order_by(HostingPostgresReplicationStandby.created_at.asc(), HostingPostgresReplicationStandby.id.asc())
    ).all()
    evaluations = [
        standby_evaluation(db, group=group, standby=row, now=now)
        for row in standbys
    ]
    evaluations.sort(
        key=lambda item: anti_affinity_sort_key(
            item["anti_affinity"],
            score=float(item["replay_backlog_bytes"] or 0),
            name=item["node_name"] or "",
            server_id=item["node_id"],
        )
    )
    eligible = [item for item in evaluations if item["eligible"]]
    blockers: list[str] = []
    if group.status != "active":
        blockers.append(f"replication group status is {group.status}")
    if not databases:
        blockers.append("replication group has no member databases")
    if any(dbrow.engine != "postgresql" for dbrow in databases):
        blockers.append("replication group contains a non-PostgreSQL database")
    if any(dbrow.node_id != group.primary_node_id for dbrow in databases):
        blockers.append("one or more group databases are not assigned to the group primary node")
    if not standbys:
        blockers.append("replication group has no standby")
    elif not eligible:
        blockers.append("no standby currently meets safe promotion criteria")

    recommended = eligible[0] if eligible else None
    return {
        "group": {
            "id": str(group.id),
            "name": group.name,
            "status": group.status,
            "primary_node_id": str(group.primary_node_id),
        },
        "databases": [
            {
                "id": str(row.id),
                "tenant_id": str(row.tenant_id),
                "name": row.database_name,
                "status": row.status,
            }
            for row in databases
        ],
        "standbys": evaluations,
        "recommended_standby": recommended,
        "promotion_ready": not blockers and recommended is not None,
        "blockers": blockers,
        "thresholds": {
            "health_grace_seconds": int(GROUP_HEALTH_GRACE.total_seconds()),
            "max_replay_backlog_bytes": MAX_GROUP_REPLAY_BACKLOG_BYTES,
            "replay_age_seconds_is_diagnostic_only": True,
        },
        "execution_mode": "plan_only",
    }
