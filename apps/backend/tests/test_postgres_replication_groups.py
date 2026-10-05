from datetime import datetime, timezone
import json
import uuid

from app.models import (
    HostingDatabase,
    HostingNode,
    HostingNodeAgent,
    HostingPostgresReplicationGroup,
    HostingPostgresReplicationMember,
    HostingPostgresReplicationStandby,
    InfrastructureServer,
)
from app.services.postgres_replication_groups import build_postgres_replication_group_plan


def _node(db, owner, suffix):
    node = HostingNode(
        name=f"pggrp-{suffix}-{uuid.uuid4().hex[:6]}",
        hostname=f"pggrp-{suffix}-{uuid.uuid4().hex[:6]}.example.test",
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


def _server(db, owner, node, *, provider, region, datacenter, physical_host, segment):
    row = InfrastructureServer(
        name=node.name,
        hostname=node.hostname,
        provider=provider,
        region=region,
        datacenter=datacenter,
        physical_host=physical_host,
        network_segment=segment,
        roles_json='["database"]',
        status="active",
        hosting_node_id=node.id,
        created_by_user_id=owner.id,
    )
    db.add(row)
    db.flush()
    return row


def _database(db, tenant, owner, node, suffix):
    row = HostingDatabase(
        tenant_id=tenant.id,
        node_id=node.id,
        engine="postgresql",
        database_name=f"db_{suffix}_{uuid.uuid4().hex[:6]}",
        username=f"u_{uuid.uuid4().hex[:8]}",
        encrypted_password="encrypted",
        internal_port=5432,
        storage_mb=1024,
        status="ready",
        operation="provision",
        created_by_user_id=owner.id,
    )
    db.add(row)
    db.flush()
    return row


def _agent(db, owner, node):
    row = HostingNodeAgent(
        node_id=node.id,
        token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        token_hint="ith_host_group",
        agent_version="ithute-hosting-agent/4",
        capabilities_json=json.dumps({
            "postgres_physical_replication": {
                "supported": True,
                "dedicated_cluster": True,
                "promotion_requires_source_fencing": True,
            }
        }),
        last_seen_at=datetime.now(timezone.utc),
        rotated_at=datetime.now(timezone.utc),
        rotated_by_user_id=owner.id,
    )
    db.add(row)
    db.flush()


def test_group_plan_allows_multiple_databases_to_move_as_one_cluster(db, tenant_admin, platform_owner):
    user, tenant, _ = tenant_admin
    now = datetime.now(timezone.utc)
    primary = _node(db, platform_owner, "primary")
    standby_node = _node(db, platform_owner, "standby")
    _server(db, platform_owner, primary, provider="p1", region="r1", datacenter="dc1", physical_host="h1", segment="s1")
    _server(db, platform_owner, standby_node, provider="p2", region="r2", datacenter="dc2", physical_host="h2", segment="s2")
    _agent(db, platform_owner, primary)
    _agent(db, platform_owner, standby_node)

    first = _database(db, tenant, user, primary, "one")
    second = _database(db, tenant, user, primary, "two")
    group = HostingPostgresReplicationGroup(
        name="tenant-cluster",
        primary_node_id=primary.id,
        status="active",
        created_by_user_id=platform_owner.id,
    )
    db.add(group)
    db.flush()
    db.add_all([
        HostingPostgresReplicationMember(group_id=group.id, database_id=first.id),
        HostingPostgresReplicationMember(group_id=group.id, database_id=second.id),
    ])
    standby = HostingPostgresReplicationStandby(
        group_id=group.id,
        node_id=standby_node.id,
        status="streaming",
        healthy=True,
        receive_lsn="0/500",
        replay_lsn="0/500",
        replay_backlog_bytes=0,
        replay_age_seconds=1000.0,
        in_recovery=True,
        last_checked_at=now,
    )
    db.add(standby)
    db.flush()

    plan = build_postgres_replication_group_plan(db, group=group, now=now)

    assert plan["promotion_ready"] is True
    assert len(plan["databases"]) == 2
    assert plan["recommended_standby"]["standby_id"] == str(standby.id)
    assert plan["blockers"] == []
    db.rollback()


def test_group_plan_blocks_member_database_on_wrong_primary_node(db, tenant_admin, platform_owner):
    user, tenant, _ = tenant_admin
    primary = _node(db, platform_owner, "primary-wrong")
    other = _node(db, platform_owner, "other")
    first = _database(db, tenant, user, primary, "good")
    second = _database(db, tenant, user, other, "wrong")
    group = HostingPostgresReplicationGroup(
        name="broken-group",
        primary_node_id=primary.id,
        status="active",
        created_by_user_id=platform_owner.id,
    )
    db.add(group)
    db.flush()
    db.add_all([
        HostingPostgresReplicationMember(group_id=group.id, database_id=first.id),
        HostingPostgresReplicationMember(group_id=group.id, database_id=second.id),
    ])
    db.flush()

    plan = build_postgres_replication_group_plan(db, group=group)

    assert plan["promotion_ready"] is False
    assert any("not assigned to the group primary node" in reason for reason in plan["blockers"])
    db.rollback()
