from datetime import datetime, timedelta, timezone
import json
import uuid

from app.models import (
    HostingDatabase,
    HostingDatabaseReplica,
    HostingNode,
    HostingNodeAgent,
    InfrastructureServer,
)
from app.services.database_replication import build_database_failover_plan


def _node(db, owner, suffix):
    node = HostingNode(
        name=f"dbrep-{suffix}-{uuid.uuid4().hex[:6]}",
        hostname=f"dbrep-{suffix}-{uuid.uuid4().hex[:6]}.example.test",
        allocatable_storage_mb=10000,
        allocatable_memory_mb=8000,
        allocatable_cpu_millicores=4000,
        status="active",
        accepts_new_projects=True,
        created_by_user_id=owner.id,
    )
    db.add(node)
    db.flush()
    return node



def _replication_agent(db, owner, node):
    row = HostingNodeAgent(
        node_id=node.id,
        token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        token_hint="ith_host_test",
        agent_version="ithute-hosting-agent/4",
        capabilities_json=json.dumps({
            "postgres_physical_replication": {
                "mode": "physical_cluster",
                "supported": True,
                "promotion_requires_source_fencing": True,
                "in_recovery": True,
            }
        }),
        last_seen_at=datetime.now(timezone.utc),
        rotated_at=datetime.now(timezone.utc),
        rotated_by_user_id=owner.id,
    )
    db.add(row)
    db.flush()
    return row


def _server(db, owner, node, *, provider, region, datacenter, physical_host, network_segment):
    row = InfrastructureServer(
        name=node.name,
        hostname=node.hostname,
        region=region,
        provider=provider,
        datacenter=datacenter,
        physical_host=physical_host,
        network_segment=network_segment,
        roles_json='["database"]',
        status="active",
        hosting_node_id=node.id,
        created_by_user_id=owner.id,
    )
    db.add(row)
    db.flush()
    return row


def _database(db, tenant, owner, node):
    row = HostingDatabase(
        tenant_id=tenant.id,
        node_id=node.id,
        engine="postgresql",
        database_name=f"db_{uuid.uuid4().hex[:8]}",
        username=f"u_{uuid.uuid4().hex[:8]}",
        encrypted_password="encrypted",
        internal_port=5432,
        storage_mb=1024,
        status="ready",
        operation="idle",
        created_by_user_id=owner.id,
    )
    db.add(row)
    db.flush()
    return row


def test_database_failover_plan_accepts_fresh_low_lag_safe_replica(db, tenant_admin, platform_owner):
    user, tenant, _ = tenant_admin
    now = datetime.now(timezone.utc)
    primary = _node(db, platform_owner, "primary")
    replica_node = _node(db, platform_owner, "replica")
    _server(db, platform_owner, primary, provider="p1", region="r1", datacenter="dc1", physical_host="h1", network_segment="s1")
    _server(db, platform_owner, replica_node, provider="p2", region="r2", datacenter="dc2", physical_host="h2", network_segment="s2")
    _replication_agent(db, platform_owner, replica_node)
    database = _database(db, tenant, user, primary)
    replica = HostingDatabaseReplica(
        database_id=database.id,
        node_id=replica_node.id,
        status="streaming",
        healthy=True,
        lag_bytes=1024,
        lag_seconds=1.5,
        last_replayed_at=now,
        last_checked_at=now,
    )
    db.add(replica)
    db.flush()

    plan = build_database_failover_plan(db, database=database, now=now)

    assert plan["promotion_ready"] is True
    assert plan["recommended_replica"]["replica_id"] == str(replica.id)
    assert plan["recommended_replica"]["node_id"] == str(replica_node.id)
    assert plan["blockers"] == []
    db.rollback()


def test_database_failover_plan_rejects_stale_high_lag_replica(db, tenant_admin, platform_owner):
    user, tenant, _ = tenant_admin
    now = datetime.now(timezone.utc)
    primary = _node(db, platform_owner, "primary-stale")
    replica_node = _node(db, platform_owner, "replica-stale")
    _server(db, platform_owner, primary, provider="p1", region="r1", datacenter="dc1", physical_host="h1", network_segment="s1")
    _server(db, platform_owner, replica_node, provider="p2", region="r2", datacenter="dc2", physical_host="h2", network_segment="s2")
    database = _database(db, tenant, user, primary)
    db.add(HostingDatabaseReplica(
        database_id=database.id,
        node_id=replica_node.id,
        status="streaming",
        healthy=True,
        lag_bytes=100 * 1024 * 1024,
        lag_seconds=90.0,
        last_checked_at=now - timedelta(minutes=10),
    ))
    db.flush()

    plan = build_database_failover_plan(db, database=database, now=now)

    assert plan["promotion_ready"] is False
    assert "no replica currently meets safe promotion criteria" in plan["blockers"]
    reasons = plan["replicas"][0]["reasons"]
    assert any("stale" in reason for reason in reasons)
    assert any("exceeds" in reason for reason in reasons)
    db.rollback()


def test_database_failover_plan_rejects_same_network_segment(db, tenant_admin, platform_owner):
    user, tenant, _ = tenant_admin
    now = datetime.now(timezone.utc)
    primary = _node(db, platform_owner, "primary-seg")
    replica_node = _node(db, platform_owner, "replica-seg")
    _server(db, platform_owner, primary, provider="p1", region="r1", datacenter="dc1", physical_host="h1", network_segment="shared")
    _server(db, platform_owner, replica_node, provider="p2", region="r2", datacenter="dc2", physical_host="h2", network_segment="shared")
    _replication_agent(db, platform_owner, replica_node)
    database = _database(db, tenant, user, primary)
    db.add(HostingDatabaseReplica(
        database_id=database.id,
        node_id=replica_node.id,
        status="ready",
        healthy=True,
        lag_bytes=0,
        lag_seconds=0.0,
        last_checked_at=now,
    ))
    db.flush()

    plan = build_database_failover_plan(db, database=database, now=now)

    assert plan["promotion_ready"] is False
    assert "network_segment" in plan["replicas"][0]["anti_affinity"]["violations"]
    db.rollback()



def test_database_failover_plan_rejects_replica_without_physical_capability(db, tenant_admin, platform_owner):
    user, tenant, _ = tenant_admin
    now = datetime.now(timezone.utc)
    primary = _node(db, platform_owner, "primary-cap")
    replica_node = _node(db, platform_owner, "replica-cap")
    _server(db, platform_owner, primary, provider="p1", region="r1", datacenter="dc1", physical_host="h1", network_segment="s1")
    _server(db, platform_owner, replica_node, provider="p2", region="r2", datacenter="dc2", physical_host="h2", network_segment="s2")
    database = _database(db, tenant, user, primary)
    db.add(HostingDatabaseReplica(
        database_id=database.id,
        node_id=replica_node.id,
        status="streaming",
        healthy=True,
        lag_bytes=0,
        lag_seconds=0.0,
        last_checked_at=now,
    ))
    db.flush()

    plan = build_database_failover_plan(db, database=database, now=now)

    assert plan["promotion_ready"] is False
    assert any("does not advertise safe PostgreSQL physical replication" in reason for reason in plan["replicas"][0]["reasons"])
    db.rollback()
