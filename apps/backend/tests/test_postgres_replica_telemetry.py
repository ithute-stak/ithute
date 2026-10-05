from datetime import datetime, timezone
import uuid

from app.models import HostingDatabase, HostingDatabaseReplica, HostingNode
from app.services.postgres_replica_telemetry import persist_postgres_replica_telemetry


def _node(db, owner, suffix: str) -> HostingNode:
    node = HostingNode(
        name=f"wal-{suffix}-{uuid.uuid4().hex[:6]}",
        hostname=f"wal-{suffix}-{uuid.uuid4().hex[:6]}.example.test",
        allocatable_storage_mb=4096,
        allocatable_memory_mb=4096,
        allocatable_cpu_millicores=2000,
        status="active",
        accepts_new_projects=True,
        created_by_user_id=owner.id,
    )
    db.add(node)
    db.flush()
    return node


def _database(db, tenant, owner, node) -> HostingDatabase:
    row = HostingDatabase(
        tenant_id=tenant.id,
        node_id=node.id,
        engine="postgresql",
        database_name=f"db_{uuid.uuid4().hex[:8]}",
        username=f"u_{uuid.uuid4().hex[:8]}",
        encrypted_password="encrypted",
        internal_port=5432,
        storage_mb=512,
        status="ready",
        operation="provision",
        created_by_user_id=owner.id,
    )
    db.add(row)
    db.flush()
    return row


def test_live_wal_telemetry_marks_single_replica_healthy(db, tenant_admin, platform_owner):
    user, tenant, _ = tenant_admin
    node = _node(db, platform_owner, "healthy")
    database = _database(db, tenant, user, node)
    replica = HostingDatabaseReplica(
        database_id=database.id,
        node_id=node.id,
        role="replica",
        status="planned",
        healthy=False,
    )
    db.add(replica)
    db.flush()
    now = datetime.now(timezone.utc)

    result = persist_postgres_replica_telemetry(
        db,
        node=node,
        now=now,
        capabilities={
            "postgres_physical_replication": {
                "mode": "physical_cluster",
                "supported": True,
                "dedicated_cluster": True,
                "in_recovery": True,
                "wal_receiver_streaming": True,
                "receive_lsn": "0/300",
                "replay_lsn": "0/2F0",
                "replay_backlog_bytes": 16,
                "replay_age_seconds": 600.0,
            }
        },
    )

    assert result["status"] == "healthy"
    assert replica.healthy is True
    assert replica.status == "streaming"
    assert replica.lag_bytes == 16
    assert replica.lag_seconds == 600.0
    assert replica.receive_lsn == "0/300"
    assert replica.replay_lsn == "0/2F0"
    assert replica.in_recovery is True
    assert replica.telemetry_error is None
    assert replica.last_checked_at == now
    db.rollback()


def test_replay_age_alone_does_not_make_idle_streaming_replica_unhealthy(db, tenant_admin, platform_owner):
    user, tenant, _ = tenant_admin
    node = _node(db, platform_owner, "idle")
    database = _database(db, tenant, user, node)
    replica = HostingDatabaseReplica(database_id=database.id, node_id=node.id, role="replica", status="planned", healthy=False)
    db.add(replica)
    db.flush()

    persist_postgres_replica_telemetry(
        db,
        node=node,
        capabilities={
            "postgres_physical_replication": {
                "supported": True,
                "dedicated_cluster": True,
                "in_recovery": True,
                "wal_receiver_streaming": True,
                "receive_lsn": "0/500",
                "replay_lsn": "0/500",
                "replay_backlog_bytes": 0,
                "replay_age_seconds": 86400.0,
            }
        },
    )

    assert replica.healthy is True
    assert replica.lag_bytes == 0
    assert replica.lag_seconds == 86400.0
    db.rollback()


def test_non_streaming_wal_receiver_marks_replica_unhealthy(db, tenant_admin, platform_owner):
    user, tenant, _ = tenant_admin
    node = _node(db, platform_owner, "disconnected")
    database = _database(db, tenant, user, node)
    replica = HostingDatabaseReplica(database_id=database.id, node_id=node.id, role="replica", status="streaming", healthy=True)
    db.add(replica)
    db.flush()

    result = persist_postgres_replica_telemetry(
        db,
        node=node,
        capabilities={
            "postgres_physical_replication": {
                "supported": True,
                "dedicated_cluster": True,
                "in_recovery": True,
                "wal_receiver_streaming": False,
                "receive_lsn": "0/500",
                "replay_lsn": "0/500",
                "replay_backlog_bytes": 0,
                "replay_age_seconds": 10.0,
            }
        },
    )

    assert result["status"] == "unhealthy"
    assert replica.healthy is False
    assert "WAL receiver is not streaming" in replica.telemetry_error
    db.rollback()


def test_multiple_replica_records_on_dedicated_node_fail_closed_as_ambiguous(db, tenant_admin, platform_owner):
    user, tenant, _ = tenant_admin
    node = _node(db, platform_owner, "ambiguous")
    first = _database(db, tenant, user, node)
    second = _database(db, tenant, user, node)
    rows = [
        HostingDatabaseReplica(database_id=first.id, node_id=node.id, role="replica", status="planned", healthy=False),
        HostingDatabaseReplica(database_id=second.id, node_id=node.id, role="replica", status="planned", healthy=False),
    ]
    db.add_all(rows)
    db.flush()

    result = persist_postgres_replica_telemetry(
        db,
        node=node,
        capabilities={"postgres_physical_replication": {"supported": True}},
    )

    assert result["status"] == "ambiguous"
    assert all(row.healthy is False for row in rows)
    assert all("ambiguous" in (row.telemetry_error or "").lower() for row in rows)
    db.rollback()
