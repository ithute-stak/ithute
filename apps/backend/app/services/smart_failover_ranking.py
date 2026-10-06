from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InfrastructureNetworkObservation, InfrastructureServer
from app.services.cluster_engine import shortest_weighted_path
from app.services.failure_domains import failure_domain_overlap
from app.services.network_route_policy import build_weighted_network_edges


FAILOVER_NETWORK_LOOKBACK = timedelta(minutes=15)


def _observation_dict(row: InfrastructureNetworkObservation) -> dict:
    return {
        "source_server_id": str(row.source_server_id),
        "target_server_id": str(row.target_server_id),
        "reachable": row.reachable,
        "latency_average_ms": row.latency_average_ms,
        "jitter_average_ms": row.jitter_average_ms,
        "connect_loss_percent": row.connect_loss_percent,
        "samples": row.samples,
        "successes": row.successes,
        "created_at": row.created_at,
    }


def rank_failover_candidates(
    db: Session,
    *,
    source_server: InfrastructureServer | None,
    candidates: list[tuple[dict, InfrastructureServer | None]],
    now: datetime | None = None,
) -> list[dict]:
    """Rank already-eligible candidates by blast radius, route quality, then placement score."""
    now = now or datetime.now(timezone.utc)
    servers = [server for _, server in candidates if server is not None]
    server_ids = {server.id for server in servers}
    if source_server is not None:
        server_ids.add(source_server.id)

    observations = []
    if server_ids:
        rows = db.scalars(
            select(InfrastructureNetworkObservation).where(
                InfrastructureNetworkObservation.created_at >= now - FAILOVER_NETWORK_LOOKBACK,
                InfrastructureNetworkObservation.source_server_id.in_(server_ids),
                InfrastructureNetworkObservation.target_server_id.in_(server_ids),
            )
        ).all()
        observations = [_observation_dict(row) for row in rows]

    node_ids = sorted(str(server_id) for server_id in server_ids)
    edges = build_weighted_network_edges(observations, now=now)

    ranked: list[dict] = []
    for placement, target_server in candidates:
        overlap = failure_domain_overlap(source_server, target_server)
        critical_collision = overlap["highest_risk"] in {"physical_host", "network_segment"}

        route = {
            "engine": "unavailable",
            "reachable": False,
            "path": [],
            "total_weight": None,
        }
        if source_server is not None and target_server is not None:
            route = shortest_weighted_path(
                node_ids,
                edges,
                source=str(source_server.id),
                target=str(target_server.id),
            )

        placement_score = float(placement.get("score") or 0.0)
        route_weight = float(route["total_weight"]) if route.get("reachable") and route.get("total_weight") is not None else float("inf")
        ranked.append({
            "placement": placement,
            "target_server": target_server,
            "failure_domain": overlap,
            "route": route,
            "sort_key": (
                critical_collision,
                float(overlap.get("penalty") or 0.0),
                not bool(route.get("reachable")),
                route_weight,
                placement_score,
                str(placement.get("name") or "").lower(),
                str(placement["node"].id),
            ),
        })

    ranked.sort(key=lambda item: item["sort_key"])
    return ranked
