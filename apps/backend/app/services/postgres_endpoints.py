from __future__ import annotations

import os
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    HostingDatabase,
    HostingDatabaseGateway,
    HostingNode,
    HostingPostgresEndpoint,
    HostingPostgresReplicationGroup,
    HostingPostgresReplicationMember,
)


_DNS_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*$")
_ENDPOINT_PORT_START = int(os.getenv("ITHUTE_POSTGRES_ENDPOINT_PORT_START", "20000"))
_ENDPOINT_PORT_END = int(os.getenv("ITHUTE_POSTGRES_ENDPOINT_PORT_END", "39999"))




def _allocate_listen_port(db: Session, gateway_id) -> int:
    if not (1024 <= _ENDPOINT_PORT_START <= _ENDPOINT_PORT_END <= 65535):
        raise RuntimeError("PostgreSQL endpoint port range is invalid")
    used = set(
        int(value)
        for value in db.scalars(
            select(HostingPostgresEndpoint.listen_port).where(
                HostingPostgresEndpoint.gateway_id == gateway_id
            )
        ).all()
    )
    for port in range(_ENDPOINT_PORT_START, _ENDPOINT_PORT_END + 1):
        if port not in used:
            return port
    raise RuntimeError("PostgreSQL endpoint gateway port range is exhausted")



def _target_for_group(db: Session, group: HostingPostgresReplicationGroup) -> tuple[HostingNode, int]:
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
    return node, int(database.internal_port)


def ensure_postgres_endpoint(
    db: Session,
    *,
    group: HostingPostgresReplicationGroup,
    gateway: HostingDatabaseGateway,
) -> HostingPostgresEndpoint:
    node, port = _target_for_group(db, group)
    row = db.scalar(
        select(HostingPostgresEndpoint)
        .where(HostingPostgresEndpoint.group_id == group.id)
        .with_for_update()
    )
    if row is None:
        row = HostingPostgresEndpoint(
            group_id=group.id,
            gateway_id=gateway.id,
            hostname=gateway.hostname,
            listen_port=_allocate_listen_port(db, gateway.id),
            current_node_id=node.id,
            target_host=node.hostname,
            target_port=port,
            generation=1,
            applied_generation=0,
            status="pending",
        )
        db.add(row)
        db.flush()
        return row

    changed = (
        row.gateway_id != gateway.id
        or row.hostname != gateway.hostname
        or row.current_node_id != node.id
        or row.target_host != node.hostname
        or int(row.target_port) != port
    )
    row.gateway_id = gateway.id
    row.hostname = gateway.hostname
    row.current_node_id = node.id
    row.target_host = node.hostname
    row.target_port = port
    if changed:
        row.generation = int(row.generation) + 1
        row.status = "pending"
    db.flush()
    return row


def switch_postgres_endpoint_to_primary(
    db: Session,
    *,
    group: HostingPostgresReplicationGroup,
    now: datetime | None = None,
) -> HostingPostgresEndpoint | None:
    now = now or datetime.now(timezone.utc)
    row = db.scalar(
        select(HostingPostgresEndpoint)
        .where(HostingPostgresEndpoint.group_id == group.id)
        .with_for_update()
    )
    if row is None:
        return None
    node, port = _target_for_group(db, group)
    if (
        row.current_node_id != node.id
        or row.target_host != node.hostname
        or int(row.target_port) != port
    ):
        row.current_node_id = node.id
        row.target_host = node.hostname
        row.target_port = port
        row.generation = int(row.generation) + 1
        row.status = "pending"
        row.last_routed_at = now
    db.flush()
    return row


def gateway_route_snapshot(db: Session, *, gateway: HostingDatabaseGateway) -> dict:
    rows = db.scalars(
        select(HostingPostgresEndpoint)
        .where(HostingPostgresEndpoint.gateway_id == gateway.id)
        .order_by(HostingPostgresEndpoint.hostname.asc(), HostingPostgresEndpoint.id.asc())
    ).all()
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
            }
            for row in rows
        ],
    }


def acknowledge_route_generation(
    db: Session,
    *,
    endpoint_id,
    gateway_id,
    generation: int,
    now: datetime | None = None,
) -> HostingPostgresEndpoint:
    now = now or datetime.now(timezone.utc)
    row = db.scalar(
        select(HostingPostgresEndpoint)
        .where(
            HostingPostgresEndpoint.id == endpoint_id,
            HostingPostgresEndpoint.gateway_id == gateway_id,
        )
        .with_for_update()
    )
    if row is None:
        raise ValueError("PostgreSQL endpoint route not found")
    if int(generation) != int(row.generation):
        raise ValueError("Stale PostgreSQL endpoint route generation")
    row.applied_generation = int(generation)
    row.status = "ready"
    row.last_routed_at = now
    db.flush()
    return row
