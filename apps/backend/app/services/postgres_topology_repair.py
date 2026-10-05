from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    HostingDatabase,
    HostingNode,
    HostingNodeAgent,
    HostingPostgresReplicationGroup,
    HostingPostgresReplicationMember,
    HostingPostgresReplicationStandby,
    HostingPostgresTopologyRepair,
)


ACTIVE_REPAIR_STATUSES = ("queued", "claimed")


def _agent_postgres_capabilities(db: Session, node_id) -> dict:
    agent = db.get(HostingNodeAgent, node_id)
    if agent is None:
        return {}
    try:
        raw = json.loads(agent.capabilities_json or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    postgres = raw.get("postgres_physical_replication")
    return postgres if isinstance(postgres, dict) else {}


def choose_topology_repair_method(db: Session, *, node_id) -> str:
    postgres = _agent_postgres_capabilities(db, node_id)
    if (
        postgres.get("supported") is True
        and postgres.get("dedicated_cluster") is True
        and postgres.get("pg_rewind_available") is True
        and postgres.get("data_checksums") is True
    ):
        return "rewind"
    return "basebackup"


def _queue_one(
    db: Session,
    *,
    group_id,
    node_id,
    source_node_id,
) -> HostingPostgresTopologyRepair | None:
    if node_id == source_node_id:
        return None
    active = db.scalar(
        select(HostingPostgresTopologyRepair.id).where(
            HostingPostgresTopologyRepair.group_id == group_id,
            HostingPostgresTopologyRepair.node_id == node_id,
            HostingPostgresTopologyRepair.status.in_(ACTIVE_REPAIR_STATUSES),
        )
    )
    if active is not None:
        return None
    row = HostingPostgresTopologyRepair(
        group_id=group_id,
        node_id=node_id,
        source_node_id=source_node_id,
        method=choose_topology_repair_method(db, node_id=node_id),
        status="queued",
    )
    db.add(row)
    db.flush()
    return row


def queue_post_failover_topology_repairs(
    db: Session,
    *,
    group: HostingPostgresReplicationGroup,
    old_primary_node_id,
    promoted_standby_id,
) -> list[HostingPostgresTopologyRepair]:
    queued: list[HostingPostgresTopologyRepair] = []

    old_primary = _queue_one(
        db,
        group_id=group.id,
        node_id=old_primary_node_id,
        source_node_id=group.primary_node_id,
    )
    if old_primary is not None:
        queued.append(old_primary)

    standbys = db.scalars(
        select(HostingPostgresReplicationStandby).where(
            HostingPostgresReplicationStandby.group_id == group.id,
            HostingPostgresReplicationStandby.id != promoted_standby_id,
        )
    ).all()
    for standby in standbys:
        row = _queue_one(
            db,
            group_id=group.id,
            node_id=standby.node_id,
            source_node_id=group.primary_node_id,
        )
        if row is not None:
            queued.append(row)

    return queued


def topology_repair_source(db: Session, *, repair: HostingPostgresTopologyRepair) -> dict:
    source = db.get(HostingNode, repair.source_node_id)
    if source is None:
        raise RuntimeError("PostgreSQL topology repair source node is unavailable")

    member_id = db.scalar(
        select(HostingPostgresReplicationMember.database_id)
        .where(HostingPostgresReplicationMember.group_id == repair.group_id)
        .order_by(HostingPostgresReplicationMember.database_id.asc())
    )
    database = db.get(HostingDatabase, member_id) if member_id is not None else None
    source_port = int(database.internal_port) if database is not None else 5432
    return {
        "host": source.hostname,
        "port": source_port,
        "node_id": str(source.id),
    }
