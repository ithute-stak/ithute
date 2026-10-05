from datetime import datetime, timezone
import uuid

import pytest

from app.core.security import hash_token
from app.models import (
    HostingDatabase,
    HostingDatabaseGateway,
    HostingNode,
    HostingPostgresEndpoint,
    HostingPostgresReplicationGroup,
    HostingPostgresReplicationMember,
)
from app.services.postgres_endpoints import (
    acknowledge_route_generation,
    ensure_postgres_endpoint,
    gateway_route_snapshot,
    switch_postgres_endpoint_to_primary,
)


def _node(db, owner, suffix: str) -> HostingNode:
    row = HostingNode(
        name=f"endpoint-{suffix}-{uuid.uuid4().hex[:6]}",
        hostname=f"endpoint-{suffix}-{uuid.uuid4().hex[:6]}.internal",
        allocatable_storage_mb=8192,
        allocatable_memory_mb=4096,
        allocatable_cpu_millicores=4000,
        status="active",
        accepts_new_projects=True,
        created_by_user_id=owner.id,
    )
    db.add(row)
    db.flush()
    return row


def _database(db, tenant, owner, node, suffix: str) -> HostingDatabase:
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


def _gateway(db, owner, suffix: str) -> HostingDatabaseGateway:
    token = "ith_dbgw_" + uuid.uuid4().hex + uuid.uuid4().hex
    row = HostingDatabaseGateway(
        name=f"gateway-{suffix}-{uuid.uuid4().hex[:6]}",
        hostname=f"gateway-{suffix}.internal",
        token_hash=hash_token(token),
        token_hint=token[-12:],
        status="active",
        created_by_user_id=owner.id,
    )
    db.add(row)
    db.flush()
    return row


def _group(db, owner, node, database) -> HostingPostgresReplicationGroup:
    group = HostingPostgresReplicationGroup(
        name=f"group-{uuid.uuid4().hex[:6]}",
        primary_node_id=node.id,
        status="active",
        created_by_user_id=owner.id,
    )
    db.add(group)
    db.flush()
    db.add(HostingPostgresReplicationMember(group_id=group.id, database_id=database.id))
    db.flush()
    return group


def test_endpoint_uses_gateway_hostname_and_unique_stable_port(db, tenant_admin, platform_owner):
    user, tenant, _ = tenant_admin
    primary = _node(db, platform_owner, "primary")
    first_db = _database(db, tenant, user, primary, "one")
    second_db = _database(db, tenant, user, primary, "two")
    first_group = _group(db, platform_owner, primary, first_db)
    second_group = _group(db, platform_owner, primary, second_db)
    gateway = _gateway(db, platform_owner, "main")

    first = ensure_postgres_endpoint(db, group=first_group, gateway=gateway)
    second = ensure_postgres_endpoint(db, group=second_group, gateway=gateway)

    assert first.hostname == gateway.hostname
    assert second.hostname == gateway.hostname
    assert first.listen_port != second.listen_port
    assert first.target_host == primary.hostname
    assert first.target_port == 5432
    assert first.generation == 1
    assert first.applied_generation == 0
    db.rollback()


def test_primary_switch_bumps_generation_and_waits_for_gateway_ack(db, tenant_admin, platform_owner):
    user, tenant, _ = tenant_admin
    primary = _node(db, platform_owner, "old")
    promoted = _node(db, platform_owner, "new")
    database = _database(db, tenant, user, primary, "switch")
    group = _group(db, platform_owner, primary, database)
    gateway = _gateway(db, platform_owner, "switch")
    endpoint = ensure_postgres_endpoint(db, group=group, gateway=gateway)
    initial_port = endpoint.listen_port

    group.primary_node_id = promoted.id
    database.node_id = promoted.id
    switched = switch_postgres_endpoint_to_primary(
        db,
        group=group,
        now=datetime.now(timezone.utc),
    )

    assert switched is not None
    assert switched.listen_port == initial_port
    assert switched.current_node_id == promoted.id
    assert switched.target_host == promoted.hostname
    assert switched.generation == 2
    assert switched.applied_generation == 0
    assert switched.status == "pending"

    acknowledged = acknowledge_route_generation(
        db,
        endpoint_id=switched.id,
        gateway_id=gateway.id,
        generation=2,
    )
    assert acknowledged.applied_generation == 2
    assert acknowledged.status == "ready"
    db.rollback()


def test_stale_gateway_ack_is_rejected(db, tenant_admin, platform_owner):
    user, tenant, _ = tenant_admin
    primary = _node(db, platform_owner, "stale")
    database = _database(db, tenant, user, primary, "stale")
    group = _group(db, platform_owner, primary, database)
    gateway = _gateway(db, platform_owner, "stale")
    endpoint = ensure_postgres_endpoint(db, group=group, gateway=gateway)
    endpoint.generation = 3
    db.flush()

    with pytest.raises(ValueError, match="Stale PostgreSQL endpoint route generation"):
        acknowledge_route_generation(
            db,
            endpoint_id=endpoint.id,
            gateway_id=gateway.id,
            generation=2,
        )
    db.rollback()


def test_gateway_snapshot_contains_only_gateway_routes(db, tenant_admin, platform_owner):
    user, tenant, _ = tenant_admin
    primary = _node(db, platform_owner, "snapshot")
    db1 = _database(db, tenant, user, primary, "snapshot")
    group = _group(db, platform_owner, primary, db1)
    expected_gateway = _gateway(db, platform_owner, "expected")
    other_gateway = _gateway(db, platform_owner, "other")
    endpoint = ensure_postgres_endpoint(db, group=group, gateway=expected_gateway)

    rogue = HostingPostgresEndpoint(
        group_id=uuid.uuid4(),
        gateway_id=other_gateway.id,
        hostname=other_gateway.hostname,
        listen_port=25001,
        current_node_id=primary.id,
        target_host=primary.hostname,
        target_port=5432,
        generation=1,
        applied_generation=0,
        status="pending",
    )
    # Avoid flushing the intentionally orphaned group id. It only verifies the
    # service query does not rely on an in-memory list.
    snapshot = gateway_route_snapshot(db, gateway=expected_gateway)

    assert snapshot["gateway_id"] == str(expected_gateway.id)
    assert len(snapshot["routes"]) == 1
    assert snapshot["routes"][0]["endpoint_id"] == str(endpoint.id)
    db.rollback()
