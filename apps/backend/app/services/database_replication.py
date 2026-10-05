from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    HostingDatabase,
    HostingDatabaseReplica,
    HostingNode,
    InfrastructureServer,
)
from app.services.replica_anti_affinity import anti_affinity_evaluation, anti_affinity_sort_key


REPLICA_HEALTH_GRACE = timedelta(minutes=2)
MAX_PROMOTION_LAG_SECONDS = 30.0
MAX_PROMOTION_LAG_BYTES = 64 * 1024 * 1024


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _server_for_node(db: Session, node_id) -> InfrastructureServer | None:
    if node_id is None:
        return None
    return db.scalar(
        select(InfrastructureServer).where(InfrastructureServer.hosting_node_id == node_id)
    )


def replica_promotion_evaluation(
    db: Session,
    *,
    database: HostingDatabase,
    replica: HostingDatabaseReplica,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    reasons: list[str] = []

    if replica.node_id is None:
        reasons.append("replica is not assigned to a hosting node")
    elif database.node_id == replica.node_id:
        reasons.append("replica is colocated with the primary hosting node")

    if replica.status not in {"streaming", "ready"}:
        reasons.append(f"replica status is {replica.status}")
    if not replica.healthy:
        reasons.append("replica health is not confirmed")

    checked = _utc(replica.last_checked_at)
    if checked is None or checked < now - REPLICA_HEALTH_GRACE:
        reasons.append("replica health observation is stale")

    if replica.lag_seconds is None:
        reasons.append("replication lag seconds is unknown")
    elif float(replica.lag_seconds) > MAX_PROMOTION_LAG_SECONDS:
        reasons.append(
            f"replication lag {float(replica.lag_seconds):.1f}s exceeds {MAX_PROMOTION_LAG_SECONDS:.0f}s promotion threshold"
        )

    if replica.lag_bytes is None:
        reasons.append("replication lag bytes is unknown")
    elif int(replica.lag_bytes) > MAX_PROMOTION_LAG_BYTES:
        reasons.append("replication byte lag exceeds promotion threshold")

    source_server = _server_for_node(db, database.node_id)
    target_server = _server_for_node(db, replica.node_id)
    anti_affinity = anti_affinity_evaluation(source_server, target_server)
    if not anti_affinity["eligible"]:
        reasons.append(
            "replica shares a critical failure domain with the primary: "
            + ", ".join(anti_affinity["violations"])
        )

    node = db.get(HostingNode, replica.node_id) if replica.node_id else None
    if node is None:
        reasons.append("replica hosting node is unavailable")
    else:
        if node.status != "active":
            reasons.append(f"replica hosting node status is {node.status}")
        if not node.accepts_new_projects:
            reasons.append("replica hosting node is not accepting workloads")

    return {
        "replica_id": str(replica.id),
        "database_id": str(database.id),
        "node_id": str(replica.node_id) if replica.node_id else None,
        "node_name": node.name if node else None,
        "eligible": not reasons,
        "reasons": reasons,
        "healthy": bool(replica.healthy),
        "status": replica.status,
        "lag_seconds": replica.lag_seconds,
        "lag_bytes": replica.lag_bytes,
        "last_checked_at": checked.isoformat() if checked else None,
        "anti_affinity": anti_affinity,
    }


def build_database_failover_plan(
    db: Session,
    *,
    database: HostingDatabase,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    replicas = db.scalars(
        select(HostingDatabaseReplica)
        .where(HostingDatabaseReplica.database_id == database.id)
        .order_by(HostingDatabaseReplica.created_at.asc(), HostingDatabaseReplica.id.asc())
    ).all()

    evaluations = [
        replica_promotion_evaluation(db, database=database, replica=replica, now=now)
        for replica in replicas
    ]
    evaluations.sort(
        key=lambda item: anti_affinity_sort_key(
            item["anti_affinity"],
            score=float(item["lag_seconds"] or 0.0),
            name=item["node_name"] or "",
            server_id=item["node_id"] or "",
        )
    )
    eligible = [item for item in evaluations if item["eligible"]]
    recommended = eligible[0] if eligible else None

    blockers: list[str] = []
    if database.status not in {"ready", "suspended"}:
        blockers.append(f"database status is {database.status}")
    if database.node_id is None:
        blockers.append("database primary is not assigned to a hosting node")
    if not replicas:
        blockers.append("no replica is configured")
    elif recommended is None:
        blockers.append("no replica currently meets safe promotion criteria")

    return {
        "database": {
            "id": str(database.id),
            "engine": database.engine,
            "name": database.database_name,
            "primary_node_id": str(database.node_id) if database.node_id else None,
            "status": database.status,
        },
        "promotion_ready": not blockers and recommended is not None,
        "recommended_replica": recommended,
        "replicas": evaluations,
        "blockers": blockers,
        "thresholds": {
            "health_grace_seconds": int(REPLICA_HEALTH_GRACE.total_seconds()),
            "max_lag_seconds": MAX_PROMOTION_LAG_SECONDS,
            "max_lag_bytes": MAX_PROMOTION_LAG_BYTES,
        },
        "execution_mode": "plan_only",
    }
