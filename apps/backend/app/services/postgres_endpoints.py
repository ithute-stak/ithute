from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    HostingDatabase,
    HostingDatabaseGateway,
    HostingDatabaseGatewayPool,
    HostingDatabaseGatewayPoolMember,
    HostingNode,
    HostingPostgresEndpoint,
    HostingPostgresEndpointGatewayAck,
    HostingPostgresReplicationGroup,
    HostingPostgresReplicationMember,
    InfrastructureServer,
    InfrastructureWireGuardPeer,
)

_ENDPOINT_PORT_START = int(os.getenv("ITHUTE_POSTGRES_ENDPOINT_PORT_START", "20000"))
_ENDPOINT_PORT_END = int(os.getenv("ITHUTE_POSTGRES_ENDPOINT_PORT_END", "39999"))
_GATEWAY_FRESHNESS_SECONDS = int(os.getenv("ITHUTE_DB_GATEWAY_FRESHNESS_SECONDS", "30"))


def _pool_gateway_ids(db: Session, pool_id) -> list:
    return db.scalars(
        select(HostingDatabaseGatewayPoolMember.gateway_id)
        .where(HostingDatabaseGatewayPoolMember.pool_id == pool_id)
        .order_by(HostingDatabaseGatewayPoolMember.gateway_id.asc())
    ).all()


def _allocate_listen_port(db: Session, gateway_ids: list) -> int:
    if not (1024 <= _ENDPOINT_PORT_START <= _ENDPOINT_PORT_END <= 65535):
        raise RuntimeError("PostgreSQL endpoint port range is invalid")
    gateway_ids = list(dict.fromkeys(gateway_ids))
    endpoints = db.scalars(select(HostingPostgresEndpoint)).all()
    used: set[int] = set()
    for endpoint in endpoints:
        endpoint_gateways = {endpoint.gateway_id}
        if endpoint.gateway_pool_id is not None:
            endpoint_gateways.update(_pool_gateway_ids(db, endpoint.gateway_pool_id))
        if endpoint_gateways.intersection(gateway_ids):
            used.add(int(endpoint.listen_port))
    for port in range(_ENDPOINT_PORT_START, _ENDPOINT_PORT_END + 1):
        if port not in used:
            return port
    raise RuntimeError("PostgreSQL endpoint gateway port range is exhausted")


def _target_for_group(db: Session, group: HostingPostgresReplicationGroup) -> tuple[HostingNode, str, int]:
    node = db.get(HostingNode, group.primary_node_id)
    if node is None:
        raise RuntimeError("PostgreSQL replication-group primary hosting node is unavailable")

    member_id = db.scalar(
        select(HostingPostgresReplicationMember.database_id)
        .where(HostingPostgresReplicationMember.group_id == group.id)
        .order_by(HostingPostgresReplicationMember.database_id.asc())
    )
    database = db.get(HostingDatabase, member_id) if member_id is not None else None
    if database is None:
        raise RuntimeError("PostgreSQL replication group has no database member for route port discovery")
    server = db.scalar(
        select(InfrastructureServer).where(
            InfrastructureServer.hosting_node_id == node.id
        )
    )
    peer = (
        db.scalar(
            select(InfrastructureWireGuardPeer).where(
                InfrastructureWireGuardPeer.server_id == server.id,
                InfrastructureWireGuardPeer.status == "active",
            )
        )
        if server is not None
        else None
    )
    target_host = peer.assigned_ipv4 if peer is not None else node.hostname
    return node, target_host, int(database.internal_port)


def ensure_postgres_endpoint(
    db: Session,
    *,
    group: HostingPostgresReplicationGroup,
    gateway: HostingDatabaseGateway,
) -> HostingPostgresEndpoint:
    node, target_host, port = _target_for_group(db, group)
    row = db.scalar(
        select(HostingPostgresEndpoint)
        .where(HostingPostgresEndpoint.group_id == group.id)
        .with_for_update()
    )
    if row is None:
        row = HostingPostgresEndpoint(
            group_id=group.id,
            gateway_id=gateway.id,
            gateway_pool_id=None,
            hostname=gateway.hostname,
            listen_port=_allocate_listen_port(db, [gateway.id]),
            current_node_id=node.id,
            target_host=target_host,
            target_port=port,
            generation=1,
            applied_generation=0,
            required_gateway_acks=1,
            status="pending",
        )
        db.add(row)
        db.flush()
        return row

    changed = (
        row.gateway_id != gateway.id
        or row.gateway_pool_id is not None
        or row.hostname != gateway.hostname
        or row.current_node_id != node.id
        or row.target_host != target_host
        or int(row.target_port) != port
    )
    gateway_changed = row.gateway_id != gateway.id or row.gateway_pool_id is not None
    row.gateway_id = gateway.id
    row.gateway_pool_id = None
    row.required_gateway_acks = 1
    row.hostname = gateway.hostname
    if gateway_changed:
        row.listen_port = _allocate_listen_port(db, [gateway.id])
    row.current_node_id = node.id
    row.target_host = target_host
    row.target_port = port
    if changed:
        row.generation = int(row.generation) + 1
        row.applied_generation = 0
        row.status = "pending"
    db.flush()
    return row


def ensure_postgres_ha_endpoint(
    db: Session,
    *,
    group: HostingPostgresReplicationGroup,
    pool: HostingDatabaseGatewayPool,
) -> HostingPostgresEndpoint:
    if pool.status != "active":
        raise RuntimeError("Database gateway pool is not active")
    gateway_ids = _pool_gateway_ids(db, pool.id)
    if len(gateway_ids) < int(pool.required_ready_gateways):
        raise RuntimeError("Database gateway pool does not contain enough members for its readiness quorum")
    gateways = [
        db.get(HostingDatabaseGateway, gateway_id)
        for gateway_id in gateway_ids
    ]
    if any(gateway is None or gateway.status != "active" for gateway in gateways):
        raise RuntimeError("Database gateway pool contains an unavailable gateway")

    primary_gateway = gateways[0]
    node, target_host, port = _target_for_group(db, group)
    row = db.scalar(
        select(HostingPostgresEndpoint)
        .where(HostingPostgresEndpoint.group_id == group.id)
        .with_for_update()
    )
    if row is None:
        row = HostingPostgresEndpoint(
            group_id=group.id,
            gateway_id=primary_gateway.id,
            gateway_pool_id=pool.id,
            hostname=pool.frontend_hostname,
            listen_port=_allocate_listen_port(db, gateway_ids),
            current_node_id=node.id,
            target_host=target_host,
            target_port=port,
            generation=1,
            applied_generation=0,
            required_gateway_acks=int(pool.required_ready_gateways),
            status="pending",
        )
        db.add(row)
        db.flush()
        return row

    changed = (
        row.gateway_pool_id != pool.id
        or row.hostname != pool.frontend_hostname
        or int(row.required_gateway_acks) != int(pool.required_ready_gateways)
        or row.current_node_id != node.id
        or row.target_host != target_host
        or int(row.target_port) != port
    )
    pool_changed = row.gateway_pool_id != pool.id
    row.gateway_id = primary_gateway.id
    row.gateway_pool_id = pool.id
    row.hostname = pool.frontend_hostname
    row.required_gateway_acks = int(pool.required_ready_gateways)
    if pool_changed:
        row.listen_port = _allocate_listen_port(db, gateway_ids)
    row.current_node_id = node.id
    row.target_host = target_host
    row.target_port = port
    if changed:
        row.generation = int(row.generation) + 1
        row.applied_generation = 0
        row.status = "pending"
    db.flush()
    return row


def switch_postgres_endpoint_to_primary(
    db: Session,
    *,
    group: HostingPostgresReplicationGroup,
    now: datetime | None = None,
) -> HostingPostgresEndpoint | None:
    row = db.scalar(
        select(HostingPostgresEndpoint)
        .where(HostingPostgresEndpoint.group_id == group.id)
        .with_for_update()
    )
    if row is None:
        return None
    node, target_host, port = _target_for_group(db, group)
    if (
        row.current_node_id != node.id
        or row.target_host != target_host
        or int(row.target_port) != port
    ):
        row.current_node_id = node.id
        row.target_host = target_host
        row.target_port = port
        row.generation = int(row.generation) + 1
        row.applied_generation = 0
        row.status = "pending"
    db.flush()
    return row


def _gateway_can_serve_endpoint(db: Session, endpoint: HostingPostgresEndpoint, gateway_id) -> bool:
    if endpoint.gateway_pool_id is None:
        return endpoint.gateway_id == gateway_id
    member = db.get(
        HostingDatabaseGatewayPoolMember,
        {"pool_id": endpoint.gateway_pool_id, "gateway_id": gateway_id},
    )
    return member is not None


def _gateway_ack_generation(db: Session, endpoint_id, gateway_id) -> int:
    ack = db.get(
        HostingPostgresEndpointGatewayAck,
        {"endpoint_id": endpoint_id, "gateway_id": gateway_id},
    )
    return int(ack.generation) if ack is not None else 0


def gateway_route_snapshot(db: Session, *, gateway: HostingDatabaseGateway) -> dict:
    rows = db.scalars(
        select(HostingPostgresEndpoint)
        .order_by(HostingPostgresEndpoint.hostname.asc(), HostingPostgresEndpoint.id.asc())
    ).all()
    rows = [row for row in rows if _gateway_can_serve_endpoint(db, row, gateway.id)]
    return {
        "gateway_id": str(gateway.id),
        "routes": [
            {
                "endpoint_id": str(row.id),
                "hostname": row.hostname,
                "listen_port": row.listen_port,
                "target_host": row.target_host,
                "target_port": row.target_port,
                "generation": row.generation,
                "applied_generation": _gateway_ack_generation(db, row.id, gateway.id),
                "required_gateway_acks": row.required_gateway_acks,
            }
            for row in rows
        ],
    }


def _fresh_ack_count(
    db: Session,
    *,
    endpoint: HostingPostgresEndpoint,
    now: datetime,
) -> int:
    threshold = now - timedelta(seconds=max(10, min(_GATEWAY_FRESHNESS_SECONDS, 300)))
    gateway_ids = (
        _pool_gateway_ids(db, endpoint.gateway_pool_id)
        if endpoint.gateway_pool_id is not None
        else [endpoint.gateway_id]
    )
    count = 0
    for gateway_id in gateway_ids:
        gateway = db.get(HostingDatabaseGateway, gateway_id)
        ack = db.get(
            HostingPostgresEndpointGatewayAck,
            {"endpoint_id": endpoint.id, "gateway_id": gateway_id},
        )
        seen = gateway.last_seen_at if gateway is not None else None
        if seen is not None and seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
        if (
            gateway is not None
            and gateway.status == "active"
            and seen is not None
            and seen >= threshold
            and ack is not None
            and int(ack.generation) == int(endpoint.generation)
        ):
            count += 1
    return count


def acknowledge_route_generation(
    db: Session,
    *,
    endpoint_id,
    gateway_id,
    generation: int,
    now: datetime | None = None,
) -> tuple[HostingPostgresEndpoint, int]:
    now = now or datetime.now(timezone.utc)
    row = db.scalar(
        select(HostingPostgresEndpoint)
        .where(HostingPostgresEndpoint.id == endpoint_id)
        .with_for_update()
    )
    if row is None or not _gateway_can_serve_endpoint(db, row, gateway_id):
        raise ValueError("PostgreSQL endpoint route not found")
    if int(generation) != int(row.generation):
        raise ValueError("Stale PostgreSQL endpoint route generation")

    ack = db.get(
        HostingPostgresEndpointGatewayAck,
        {"endpoint_id": row.id, "gateway_id": gateway_id},
    )
    if ack is None:
        ack = HostingPostgresEndpointGatewayAck(
            endpoint_id=row.id,
            gateway_id=gateway_id,
            generation=int(generation),
            applied_at=now,
        )
        db.add(ack)
    else:
        ack.generation = int(generation)
        ack.applied_at = now
    db.flush()

    ready_count = _fresh_ack_count(db, endpoint=row, now=now)
    if ready_count >= int(row.required_gateway_acks):
        row.applied_generation = int(generation)
        row.status = "ready"
        row.last_routed_at = now
    else:
        row.applied_generation = 0
        row.status = "pending"
    db.flush()
    return row, ready_count
