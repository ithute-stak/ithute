from datetime import datetime, timedelta, timezone
import uuid

from app.core.security import hash_token
from app.models import (
    HostingDatabase,
    HostingDatabaseGateway,
    HostingDatabaseGatewayPool,
    HostingDatabaseGatewayPoolMember,
    HostingNode,
    HostingPostgresReplicationGroup,
    HostingPostgresReplicationMember,
)
from app.services.database_gateway_ha import reconcile_database_gateway_health
from app.services.postgres_endpoints import (
    acknowledge_route_generation,
    ensure_postgres_ha_endpoint,
    gateway_route_snapshot,
)


def _node(db, owner, suffix):
    row = HostingNode(
        name=f"ha-gw-{suffix}-{uuid.uuid4().hex[:6]}",
        hostname=f"ha-gw-{suffix}-{uuid.uuid4().hex[:6]}.internal",
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
        operation="provision",
        created_by_user_id=owner.id,
    )
    db.add(row)
    db.flush()
    return row


def _gateway(db, owner, suffix, now):
    token = "ith_dbgw_" + uuid.uuid4().hex + uuid.uuid4().hex
    row = HostingDatabaseGateway(
        name=f"gateway-{suffix}-{uuid.uuid4().hex[:6]}",
        hostname=f"gateway-{suffix}.internal",
        token_hash=hash_token(token),
        token_hint=token[-12:],
        status="active",
        last_seen_at=now,
        agent_version="ithute-db-gateway/1",
        created_by_user_id=owner.id,
    )
    db.add(row)
    db.flush()
    return row


def _group(db, owner, node, database):
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


def _pool(db, owner, gateways, *, required=2):
    pool = HostingDatabaseGatewayPool(
        name=f"pool-{uuid.uuid4().hex[:6]}",
        frontend_hostname=f"db-ha-{uuid.uuid4().hex[:6]}.internal",
        required_ready_gateways=required,
        status="active",
        created_by_user_id=owner.id,
    )
    db.add(pool)
    db.flush()
    for gateway in gateways:
        db.add(HostingDatabaseGatewayPoolMember(pool_id=pool.id, gateway_id=gateway.id))
    db.flush()
    return pool


def test_ha_endpoint_requires_two_independent_gateway_acks(db, tenant_admin, platform_owner):
    user, tenant, _ = tenant_admin
    now = datetime.now(timezone.utc)
    primary = _node(db, platform_owner, "primary")
    database = _database(db, tenant, user, primary)
    group = _group(db, platform_owner, primary, database)
    gateways = [
        _gateway(db, platform_owner, "a", now),
        _gateway(db, platform_owner, "b", now),
    ]
    pool = _pool(db, platform_owner, gateways, required=2)
    endpoint = ensure_postgres_ha_endpoint(db, group=group, pool=pool)

    first, ready = acknowledge_route_generation(
        db,
        endpoint_id=endpoint.id,
        gateway_id=gateways[0].id,
        generation=endpoint.generation,
        now=now,
    )
    assert ready == 1
    assert first.status == "pending"
    assert first.applied_generation == 0

    second, ready = acknowledge_route_generation(
        db,
        endpoint_id=endpoint.id,
        gateway_id=gateways[1].id,
        generation=endpoint.generation,
        now=now,
    )
    assert ready == 2
    assert second.status == "ready"
    assert second.applied_generation == endpoint.generation
    db.rollback()


def test_each_pool_gateway_receives_same_route_with_own_ack_state(db, tenant_admin, platform_owner):
    user, tenant, _ = tenant_admin
    now = datetime.now(timezone.utc)
    primary = _node(db, platform_owner, "snapshot")
    database = _database(db, tenant, user, primary)
    group = _group(db, platform_owner, primary, database)
    gateway_a = _gateway(db, platform_owner, "snapshot-a", now)
    gateway_b = _gateway(db, platform_owner, "snapshot-b", now)
    pool = _pool(db, platform_owner, [gateway_a, gateway_b], required=2)
    endpoint = ensure_postgres_ha_endpoint(db, group=group, pool=pool)

    acknowledge_route_generation(
        db,
        endpoint_id=endpoint.id,
        gateway_id=gateway_a.id,
        generation=endpoint.generation,
        now=now,
    )

    a = gateway_route_snapshot(db, gateway=gateway_a)["routes"][0]
    b = gateway_route_snapshot(db, gateway=gateway_b)["routes"][0]
    assert a["endpoint_id"] == b["endpoint_id"] == str(endpoint.id)
    assert a["listen_port"] == b["listen_port"]
    assert a["generation"] == b["generation"] == endpoint.generation
    assert a["applied_generation"] == endpoint.generation
    assert b["applied_generation"] == 0
    db.rollback()


def test_gateway_crash_degrades_endpoint_after_quorum_loss(db, tenant_admin, platform_owner):
    user, tenant, _ = tenant_admin
    now = datetime.now(timezone.utc)
    primary = _node(db, platform_owner, "degrade")
    database = _database(db, tenant, user, primary)
    group = _group(db, platform_owner, primary, database)
    gateway_a = _gateway(db, platform_owner, "degrade-a", now)
    gateway_b = _gateway(db, platform_owner, "degrade-b", now)
    pool = _pool(db, platform_owner, [gateway_a, gateway_b], required=2)
    endpoint = ensure_postgres_ha_endpoint(db, group=group, pool=pool)
    for gateway in (gateway_a, gateway_b):
        acknowledge_route_generation(
            db,
            endpoint_id=endpoint.id,
            gateway_id=gateway.id,
            generation=endpoint.generation,
            now=now,
        )
    assert endpoint.status == "ready"

    gateway_b.last_seen_at = now - timedelta(minutes=5)
    db.flush()
    result = reconcile_database_gateway_health(db, now=now)

    assert result["endpoint_updates"] == 1
    assert endpoint.status == "degraded"
    assert pool.status == "degraded"
    db.rollback()


def test_gateway_quorum_recovers_after_failed_member_returns(db, tenant_admin, platform_owner):
    user, tenant, _ = tenant_admin
    now = datetime.now(timezone.utc)
    primary = _node(db, platform_owner, "recover")
    database = _database(db, tenant, user, primary)
    group = _group(db, platform_owner, primary, database)
    gateway_a = _gateway(db, platform_owner, "recover-a", now)
    gateway_b = _gateway(db, platform_owner, "recover-b", now - timedelta(minutes=5))
    pool = _pool(db, platform_owner, [gateway_a, gateway_b], required=2)
    endpoint = ensure_postgres_ha_endpoint(db, group=group, pool=pool)

    acknowledge_route_generation(
        db,
        endpoint_id=endpoint.id,
        gateway_id=gateway_a.id,
        generation=endpoint.generation,
        now=now,
    )
    acknowledge_route_generation(
        db,
        endpoint_id=endpoint.id,
        gateway_id=gateway_b.id,
        generation=endpoint.generation,
        now=now - timedelta(minutes=5),
    )
    reconcile_database_gateway_health(db, now=now)
    assert endpoint.status == "degraded"

    gateway_b.last_seen_at = now
    acknowledge_route_generation(
        db,
        endpoint_id=endpoint.id,
        gateway_id=gateway_b.id,
        generation=endpoint.generation,
        now=now,
    )
    reconcile_database_gateway_health(db, now=now)

    assert endpoint.status == "ready"
    assert pool.status == "active"
    db.rollback()
