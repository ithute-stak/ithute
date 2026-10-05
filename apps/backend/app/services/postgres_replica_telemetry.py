from __future__ import annotations

import math
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import HostingDatabaseReplica, HostingNode, HostingPostgresReplicationStandby


_LSN_RE = re.compile(r"^[0-9A-F]+/[0-9A-F]+$")


def _nonnegative_int(value):
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _nonnegative_float(value):
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed < 0:
        return None
    return parsed


def persist_postgres_replica_telemetry(
    db: Session,
    *,
    node: HostingNode,
    capabilities: dict,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    raw = capabilities.get("postgres_physical_replication")
    if not isinstance(raw, dict):
        return {"updated": 0, "status": "absent"}

    group_standbys = db.scalars(
        select(HostingPostgresReplicationStandby)
        .where(HostingPostgresReplicationStandby.node_id == node.id)
        .order_by(HostingPostgresReplicationStandby.created_at.asc(), HostingPostgresReplicationStandby.id.asc())
        .with_for_update()
    ).all()

    if group_standbys:
        if len(group_standbys) != 1:
            for standby in group_standbys:
                standby.healthy = False
                standby.telemetry_error = "Physical replication telemetry is ambiguous for multiple replication groups on one dedicated node"
                standby.last_checked_at = now
            db.flush()
            return {"updated": len(group_standbys), "status": "ambiguous_group"}

        standby = group_standbys[0]
        supported = raw.get("supported") is True
        dedicated = raw.get("dedicated_cluster") is True
        in_recovery = raw.get("in_recovery")
        receiver_streaming = raw.get("wal_receiver_streaming") is True
        receive_lsn = raw.get("receive_lsn")
        replay_lsn = raw.get("replay_lsn")
        lag_bytes = _nonnegative_int(raw.get("replay_backlog_bytes"))
        replay_age = _nonnegative_float(raw.get("replay_age_seconds"))
        status_error = str(raw.get("status_error") or "").strip()[:500] or None
        valid_lsn = (
            isinstance(receive_lsn, str)
            and isinstance(replay_lsn, str)
            and _LSN_RE.fullmatch(receive_lsn) is not None
            and _LSN_RE.fullmatch(replay_lsn) is not None
        )

        reasons: list[str] = []
        if not supported or not dedicated:
            reasons.append("dedicated physical replication capability is unavailable")
        if in_recovery is not True:
            reasons.append("node is not in PostgreSQL recovery")
        if not receiver_streaming:
            reasons.append("WAL receiver is not streaming")
        if not valid_lsn:
            reasons.append("WAL receive/replay positions are invalid or missing")
        if lag_bytes is None:
            reasons.append("WAL replay backlog is invalid or missing")
        if status_error:
            reasons.append(status_error)

        standby.receive_lsn = receive_lsn if valid_lsn else None
        standby.replay_lsn = replay_lsn if valid_lsn else None
        standby.in_recovery = in_recovery if isinstance(in_recovery, bool) else None
        standby.replay_backlog_bytes = lag_bytes
        standby.replay_age_seconds = replay_age
        standby.last_checked_at = now
        standby.healthy = not reasons
        standby.status = "streaming" if standby.healthy else standby.status
        standby.telemetry_error = "; ".join(reasons)[:500] if reasons else None
        db.flush()
        return {
            "updated": 1,
            "status": "healthy" if standby.healthy else "unhealthy",
            "replication_group_standby_id": str(standby.id),
            "lag_bytes": standby.replay_backlog_bytes,
            "replay_age_seconds": standby.replay_age_seconds,
        }

    replicas = db.scalars(
        select(HostingDatabaseReplica)
        .where(
            HostingDatabaseReplica.node_id == node.id,
            HostingDatabaseReplica.role == "replica",
        )
        .order_by(HostingDatabaseReplica.created_at.asc(), HostingDatabaseReplica.id.asc())
        .with_for_update()
    ).all()

    if not replicas:
        return {"updated": 0, "status": "no_replica"}

    if len(replicas) != 1:
        for replica in replicas:
            replica.healthy = False
            replica.telemetry_error = "Physical replication telemetry is ambiguous for multiple replica records on one dedicated node"
            replica.last_checked_at = now
        db.flush()
        return {"updated": len(replicas), "status": "ambiguous"}

    replica = replicas[0]
    supported = raw.get("supported") is True
    dedicated = raw.get("dedicated_cluster") is True
    in_recovery = raw.get("in_recovery")
    receiver_streaming = raw.get("wal_receiver_streaming") is True
    receive_lsn = raw.get("receive_lsn")
    replay_lsn = raw.get("replay_lsn")
    lag_bytes = _nonnegative_int(raw.get("replay_backlog_bytes"))
    replay_age = _nonnegative_float(raw.get("replay_age_seconds"))
    status_error = str(raw.get("status_error") or "").strip()[:500] or None

    valid_lsn = (
        isinstance(receive_lsn, str)
        and isinstance(replay_lsn, str)
        and _LSN_RE.fullmatch(receive_lsn) is not None
        and _LSN_RE.fullmatch(replay_lsn) is not None
    )

    reasons: list[str] = []
    if not supported or not dedicated:
        reasons.append("dedicated physical replication capability is unavailable")
    if in_recovery is not True:
        reasons.append("node is not in PostgreSQL recovery")
    if not receiver_streaming:
        reasons.append("WAL receiver is not streaming")
    if not valid_lsn:
        reasons.append("WAL receive/replay positions are invalid or missing")
    if lag_bytes is None:
        reasons.append("WAL replay backlog is invalid or missing")
    if status_error:
        reasons.append(status_error)

    replica.receive_lsn = receive_lsn if valid_lsn else None
    replica.replay_lsn = replay_lsn if valid_lsn else None
    replica.in_recovery = in_recovery if isinstance(in_recovery, bool) else None
    replica.lag_bytes = lag_bytes
    # Replay age is diagnostic. It is not by itself a correctness lag metric on idle systems.
    replica.lag_seconds = replay_age
    replica.last_checked_at = now
    replica.healthy = not reasons
    replica.status = "streaming" if replica.healthy else replica.status
    replica.telemetry_error = "; ".join(reasons)[:500] if reasons else None
    db.flush()
    return {
        "updated": 1,
        "status": "healthy" if replica.healthy else "unhealthy",
        "replica_id": str(replica.id),
        "lag_bytes": replica.lag_bytes,
        "replay_age_seconds": replica.lag_seconds,
    }
