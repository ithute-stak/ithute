from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    HostingDatabaseGateway,
    HostingDatabaseGatewayPool,
    HostingDatabaseGatewayPoolMember,
    HostingPostgresEndpoint,
    HostingPostgresEndpointGatewayAck,
)

_GATEWAY_FRESHNESS_SECONDS = int(os.getenv("ITHUTE_DB_GATEWAY_FRESHNESS_SECONDS", "30"))


def _utc(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _fresh(now: datetime, gateway: HostingDatabaseGateway | None) -> bool:
    seen = _utc(gateway.last_seen_at) if gateway is not None else None
    threshold = now - timedelta(seconds=max(10, min(_GATEWAY_FRESHNESS_SECONDS, 300)))
    return bool(
        gateway is not None
        and gateway.status == "active"
        and seen is not None
        and seen >= threshold
    )


def _endpoint_ready_count(
    db: Session,
    *,
    endpoint: HostingPostgresEndpoint,
    gateway_ids: list,
    now: datetime,
) -> int:
    ready = 0
    for gateway_id in gateway_ids:
        gateway = db.get(HostingDatabaseGateway, gateway_id)
        ack = db.get(
            HostingPostgresEndpointGatewayAck,
            {"endpoint_id": endpoint.id, "gateway_id": gateway_id},
        )
        if (
            _fresh(now, gateway)
            and ack is not None
            and int(ack.generation) == int(endpoint.generation)
        ):
            ready += 1
    return ready


def reconcile_database_gateway_health(
    db: Session,
    *,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    pools = db.scalars(
        select(HostingDatabaseGatewayPool).where(
            HostingDatabaseGatewayPool.status.in_(["active", "degraded"])
        )
    ).all()

    pool_updates = endpoint_updates = 0
    details: list[dict] = []
    for pool in pools:
        gateway_ids = db.scalars(
            select(HostingDatabaseGatewayPoolMember.gateway_id).where(
                HostingDatabaseGatewayPoolMember.pool_id == pool.id
            )
        ).all()
        fresh_gateways = sum(
            1 for gateway_id in gateway_ids
            if _fresh(now, db.get(HostingDatabaseGateway, gateway_id))
        )
        desired_pool_status = (
            "active"
            if fresh_gateways >= int(pool.required_ready_gateways)
            else "degraded"
        )
        if pool.status != desired_pool_status:
            pool.status = desired_pool_status
            pool_updates += 1

        endpoints = db.scalars(
            select(HostingPostgresEndpoint).where(
                HostingPostgresEndpoint.gateway_pool_id == pool.id
            )
        ).all()
        endpoint_states = []
        for endpoint in endpoints:
            ready = _endpoint_ready_count(
                db,
                endpoint=endpoint,
                gateway_ids=gateway_ids,
                now=now,
            )
            desired_endpoint_status = (
                "ready"
                if ready >= int(endpoint.required_gateway_acks)
                and int(endpoint.applied_generation) == int(endpoint.generation)
                else "degraded"
            )
            if endpoint.status != desired_endpoint_status:
                endpoint.status = desired_endpoint_status
                endpoint_updates += 1
            endpoint_states.append({
                "endpoint_id": str(endpoint.id),
                "ready_gateways": ready,
                "required_gateway_acks": endpoint.required_gateway_acks,
                "status": endpoint.status,
            })

        details.append({
            "pool_id": str(pool.id),
            "fresh_gateways": fresh_gateways,
            "required_ready_gateways": pool.required_ready_gateways,
            "status": pool.status,
            "endpoints": endpoint_states,
        })

    db.commit()
    return {
        "pools_checked": len(pools),
        "pool_updates": pool_updates,
        "endpoint_updates": endpoint_updates,
        "pools": details,
    }
