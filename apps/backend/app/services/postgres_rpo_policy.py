from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    HostingNode,
    HostingNodeAgent,
    HostingPostgresReplicationGroup,
    HostingPostgresReplicationStandby,
    HostingPostgresRpoPolicyOperation,
)


RPO_HEALTH_GRACE = timedelta(minutes=2)
RPO_CLASSES = {"async", "sync_flush", "sync_apply"}


def _agent_postgres_capabilities(agent: HostingNodeAgent | None) -> dict:
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


def validate_rpo_request(
    db: Session,
    *,
    group: HostingPostgresReplicationGroup,
    rpo_class: str,
    required_sync_standbys: int,
    now: datetime | None = None,
) -> list[str]:
    now = now or datetime.now(timezone.utc)
    errors: list[str] = []
    if rpo_class not in RPO_CLASSES:
        return ["unsupported PostgreSQL RPO class"]

    required = int(required_sync_standbys)
    if rpo_class == "async":
        if required != 0:
            errors.append("async RPO class requires zero synchronous standbys")
        return errors

    if required < 1 or required > 8:
        errors.append("synchronous RPO classes require between 1 and 8 synchronous standbys")
        return errors

    standbys = db.scalars(
        select(HostingPostgresReplicationStandby).where(
            HostingPostgresReplicationStandby.group_id == group.id
        )
    ).all()
    healthy = 0
    for standby in standbys:
        checked = standby.last_checked_at
        if checked is not None and checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)
        if (
            standby.status in {"streaming", "ready"}
            and standby.healthy
            and standby.in_recovery is True
            and checked is not None
            and checked >= now - RPO_HEALTH_GRACE
        ):
            healthy += 1
    if healthy < required:
        errors.append(
            f"requested policy requires {required} healthy synchronous standby(s), but only {healthy} are currently healthy"
        )

    primary_agent = db.get(HostingNodeAgent, group.primary_node_id)
    postgres = _agent_postgres_capabilities(primary_agent)
    if postgres.get("supported") is not True or postgres.get("dedicated_cluster") is not True:
        errors.append("primary node does not advertise dedicated PostgreSQL physical replication")
    if postgres.get("in_recovery") is True:
        errors.append("group primary node is unexpectedly in PostgreSQL recovery")

    return errors


def queue_rpo_policy_operation(
    db: Session,
    *,
    group: HostingPostgresReplicationGroup,
    rpo_class: str,
    required_sync_standbys: int,
    created_by_user_id,
) -> HostingPostgresRpoPolicyOperation:
    existing = db.scalar(
        select(HostingPostgresRpoPolicyOperation.id).where(
            HostingPostgresRpoPolicyOperation.group_id == group.id,
            HostingPostgresRpoPolicyOperation.status.in_(["queued", "claimed"]),
        )
    )
    if existing is not None:
        raise ValueError("PostgreSQL replication group already has an RPO policy operation in progress")

    row = HostingPostgresRpoPolicyOperation(
        group_id=group.id,
        node_id=group.primary_node_id,
        rpo_class=rpo_class,
        required_sync_standbys=int(required_sync_standbys),
        status="queued",
        created_by_user_id=created_by_user_id,
    )
    group.rpo_class = rpo_class
    group.required_sync_standbys = int(required_sync_standbys)
    group.rpo_healthy = False
    group.rpo_last_checked_at = None
    db.add(row)
    db.flush()
    return row


def persist_primary_rpo_telemetry(
    db: Session,
    *,
    node: HostingNode,
    capabilities: dict,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    groups = db.scalars(
        select(HostingPostgresReplicationGroup)
        .where(HostingPostgresReplicationGroup.primary_node_id == node.id)
        .with_for_update()
    ).all()
    if not groups:
        return {"updated": 0, "status": "no_group"}

    raw = capabilities.get("postgres_physical_replication")
    postgres = raw if isinstance(raw, dict) else {}

    if len(groups) != 1:
        for group in groups:
            group.rpo_healthy = False
            group.rpo_last_checked_at = now
        db.flush()
        return {"updated": len(groups), "status": "ambiguous_primary"}

    group = groups[0]
    commit_mode = str(postgres.get("primary_synchronous_commit") or "").strip().lower()
    names = str(postgres.get("primary_synchronous_standby_names") or "").strip()
    sync_count_raw = postgres.get("primary_sync_standbys")
    try:
        sync_count = int(sync_count_raw)
    except (TypeError, ValueError):
        sync_count = -1
    if sync_count < 0:
        sync_count = 0

    supported = postgres.get("supported") is True
    dedicated = postgres.get("dedicated_cluster") is True
    primary = postgres.get("in_recovery") is False

    if group.rpo_class == "async":
        healthy = supported and dedicated and primary
    elif group.rpo_class == "sync_flush":
        healthy = (
            supported
            and dedicated
            and primary
            and bool(names)
            and commit_mode in {"on", "remote_apply"}
            and sync_count >= int(group.required_sync_standbys or 0)
        )
    elif group.rpo_class == "sync_apply":
        healthy = (
            supported
            and dedicated
            and primary
            and bool(names)
            and commit_mode == "remote_apply"
            and sync_count >= int(group.required_sync_standbys or 0)
        )
    else:
        healthy = False

    group.observed_synchronous_commit = commit_mode or None
    group.observed_sync_standbys = sync_count
    group.rpo_healthy = bool(healthy)
    group.rpo_last_checked_at = now
    db.flush()
    return {
        "updated": 1,
        "status": "healthy" if healthy else "unhealthy",
        "group_id": str(group.id),
        "rpo_class": group.rpo_class,
        "required_sync_standbys": group.required_sync_standbys,
        "observed_synchronous_commit": group.observed_synchronous_commit,
        "observed_sync_standbys": group.observed_sync_standbys,
    }
