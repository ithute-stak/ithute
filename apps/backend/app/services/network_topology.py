from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import InfrastructureNetworkObservation, InfrastructureServer


TOPOLOGY_RETENTION_DAYS = 14
MAX_TOPOLOGY_RESULTS = 64


def _f(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if result < 0:
        return None
    return result


def _i(value: object) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result


def _normalize_observation(source_server_id: UUID, item: dict, *, default_samples: int) -> dict | None:
    try:
        target_server_id = UUID(str(item.get("id") or ""))
    except (TypeError, ValueError, AttributeError):
        return None
    if target_server_id == source_server_id:
        return None

    port = _i(item.get("port"))
    samples = _i(item.get("attempts"))
    if samples is None:
        samples = default_samples
    successes = _i(item.get("successes"))
    loss = _f(item.get("connect_loss_percent"))
    if port is None or not 1 <= port <= 65535:
        return None
    if samples is None or not 1 <= samples <= 10:
        return None
    if successes is None or not 0 <= successes <= samples:
        return None
    if loss is None or not 0 <= loss <= 100:
        return None

    reachable = bool(item.get("reachable"))
    if reachable != (successes > 0):
        return None

    latency_min = _f(item.get("latency_min_ms"))
    latency_avg = _f(item.get("latency_average_ms"))
    latency_max = _f(item.get("latency_max_ms"))
    jitter_avg = _f(item.get("jitter_average_ms"))

    if successes == 0:
        latency_min = latency_avg = latency_max = jitter_avg = None
    else:
        if latency_min is None or latency_avg is None or latency_max is None:
            return None
        if not (latency_min <= latency_avg <= latency_max):
            return None

    return {
        "target_server_id": target_server_id,
        "port": port,
        "samples": samples,
        "successes": successes,
        "reachable": reachable,
        "connect_loss_percent": loss,
        "latency_min_ms": latency_min,
        "latency_average_ms": latency_avg,
        "latency_max_ms": latency_max,
        "jitter_average_ms": jitter_avg,
    }


def persist_topology_observations(
    db: Session,
    *,
    source_server: InfrastructureServer,
    payload: object,
    now: datetime | None = None,
) -> int:
    if not isinstance(payload, dict):
        return 0
    if str(payload.get("engine") or "").lower() != "go":
        return 0
    if str(payload.get("source_id") or "") != str(source_server.id):
        return 0

    default_samples = _i(payload.get("samples"))
    if default_samples is None or not 1 <= default_samples <= 10:
        return 0

    results = payload.get("results")
    if not isinstance(results, list) or len(results) > MAX_TOPOLOGY_RESULTS:
        return 0

    normalized: list[dict] = []
    target_ids: set[UUID] = set()
    for raw in results:
        if not isinstance(raw, dict):
            continue
        item = _normalize_observation(source_server.id, raw, default_samples=default_samples)
        if item is None:
            continue
        target_ids.add(item["target_server_id"])
        normalized.append(item)

    if not normalized:
        return 0

    known_targets = set(
        db.scalars(
            select(InfrastructureServer.id).where(InfrastructureServer.id.in_(target_ids))
        ).all()
    )
    created = 0
    for item in normalized:
        if item["target_server_id"] not in known_targets:
            continue
        db.add(
            InfrastructureNetworkObservation(
                source_server_id=source_server.id,
                **item,
            )
        )
        created += 1

    current = now or datetime.now(timezone.utc)
    db.execute(
        delete(InfrastructureNetworkObservation).where(
            InfrastructureNetworkObservation.created_at < current - timedelta(days=TOPOLOGY_RETENTION_DAYS)
        )
    )
    return created
