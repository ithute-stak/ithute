from __future__ import annotations

from datetime import datetime, timezone
import math

from app.services.cluster_engine import shortest_weighted_path


MAX_ROUTE_OBSERVATION_AGE_SECONDS = 15 * 60
LOSS_PENALTY_PER_PERCENT = 5.0
JITTER_PENALTY_FACTOR = 1.5
STALE_PENALTY_PER_MINUTE = 2.0
MAX_STALE_PENALTY = 120.0
RELIABILITY_PENALTY_MAX = 50.0
CONGESTION_PENALTY_MAX = 100.0


def _as_float(value: object, *, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(result):
        return default
    return result


def _observation_age_seconds(created_at: object, *, now: datetime) -> float | None:
    if not isinstance(created_at, datetime):
        return None
    current = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
    return max(0.0, (now - current).total_seconds())


def route_edge_weight(observation: dict, *, now: datetime | None = None) -> dict | None:
    """Convert one trusted topology observation into an explainable non-negative route cost."""
    now = now or datetime.now(timezone.utc)
    if not bool(observation.get("reachable")):
        return None

    latency = max(0.0, _as_float(observation.get("latency_average_ms")))
    jitter = max(0.0, _as_float(observation.get("jitter_average_ms")))
    loss = min(100.0, max(0.0, _as_float(observation.get("connect_loss_percent"))))
    samples = max(1, int(_as_float(observation.get("samples"), default=1.0)))
    successes = min(samples, max(0, int(_as_float(observation.get("successes"), default=0.0))))
    reliability = successes / samples

    age_seconds = _observation_age_seconds(observation.get("created_at"), now=now)
    if age_seconds is None or age_seconds > MAX_ROUTE_OBSERVATION_AGE_SECONDS:
        return None

    congestion_percent = min(
        100.0,
        max(0.0, _as_float(observation.get("congestion_percent"))),
    )

    latency_component = latency
    loss_component = loss * LOSS_PENALTY_PER_PERCENT
    jitter_component = jitter * JITTER_PENALTY_FACTOR
    stale_component = min(
        MAX_STALE_PENALTY,
        (age_seconds / 60.0) * STALE_PENALTY_PER_MINUTE,
    )
    reliability_component = (1.0 - reliability) * RELIABILITY_PENALTY_MAX
    congestion_component = (congestion_percent / 100.0) * CONGESTION_PENALTY_MAX

    total = (
        latency_component
        + loss_component
        + jitter_component
        + stale_component
        + reliability_component
        + congestion_component
    )
    return {
        "weight": total,
        "components": {
            "latency": latency_component,
            "connect_loss": loss_component,
            "jitter": jitter_component,
            "staleness": stale_component,
            "reliability": reliability_component,
            "congestion": congestion_component,
        },
        "age_seconds": age_seconds,
        "reliability": reliability,
    }


def build_weighted_network_edges(
    observations: list[dict],
    *,
    now: datetime | None = None,
) -> list[dict]:
    """Build one current weighted edge per directed source/target pair from latest trusted observations."""
    now = now or datetime.now(timezone.utc)
    latest: dict[tuple[str, str], dict] = {}
    for observation in observations:
        source = str(observation.get("source") or observation.get("source_server_id") or "")
        target = str(observation.get("target") or observation.get("target_server_id") or "")
        if not source or not target or source == target:
            continue
        created_at = observation.get("created_at")
        if not isinstance(created_at, datetime):
            continue
        key = (source, target)
        current = latest.get(key)
        if current is None or created_at > current["created_at"]:
            latest[key] = {**observation, "source": source, "target": target}

    edges: list[dict] = []
    for (source, target), observation in sorted(latest.items()):
        weighted = route_edge_weight(observation, now=now)
        if weighted is None:
            continue
        edges.append({
            "source": source,
            "target": target,
            "weight": weighted["weight"],
            "components": weighted["components"],
            "age_seconds": weighted["age_seconds"],
            "reliability": weighted["reliability"],
        })
    return edges


def best_network_route(
    node_ids: list[str],
    observations: list[dict],
    *,
    source: str,
    target: str,
    now: datetime | None = None,
) -> dict:
    edges = build_weighted_network_edges(observations, now=now)
    result = shortest_weighted_path(node_ids, edges, source=source, target=target)
    result["edges"] = edges
    return result
