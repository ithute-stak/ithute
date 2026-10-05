from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import HostingNode, HostingProjectOperation


DEFAULT_NODE_OPERATION_CONCURRENCY = 2
MAX_NODE_OPERATION_CONCURRENCY = 16
AGING_INTERVAL_SECONDS = 300
MAX_AGING_BONUS = 40

_BASE_PRIORITY = {
    "retire": 10,
    "restart": 20,
    "logs": 60,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def node_operation_concurrency_limit() -> int:
    raw = os.getenv("ITHUTE_HOSTING_OPERATION_CONCURRENCY_PER_NODE", str(DEFAULT_NODE_OPERATION_CONCURRENCY))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_NODE_OPERATION_CONCURRENCY
    return max(1, min(value, MAX_NODE_OPERATION_CONCURRENCY))


def operation_effective_priority(
    operation: str,
    created_at: datetime,
    *,
    now: datetime | None = None,
) -> int:
    now = now or _now()
    created = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
    waited_seconds = max(0, int((now - created).total_seconds()))
    aging_bonus = min(MAX_AGING_BONUS, waited_seconds // AGING_INTERVAL_SECONDS)
    base = _BASE_PRIORITY.get((operation or "").strip().lower(), 50)
    return max(0, base - aging_bonus)


def _claim_sort_key(row: HostingProjectOperation, *, now: datetime) -> tuple:
    return (
        operation_effective_priority(row.operation, row.created_at, now=now),
        row.created_at,
        str(row.id),
    )


def claim_next_project_operation(
    db: Session,
    *,
    node_id: UUID,
    now: datetime | None = None,
    concurrency_limit: int | None = None,
) -> HostingProjectOperation | None:
    """Admit one queued operation for a node using bounded, aging-aware priority scheduling.

    The hosting-node row is locked first so concurrent agent polls serialize admission
    decisions for the same node. Existing API states are preserved: queued -> claimed.
    """
    now = now or _now()
    limit = concurrency_limit or node_operation_concurrency_limit()
    limit = max(1, min(int(limit), MAX_NODE_OPERATION_CONCURRENCY))

    node = db.scalar(
        select(HostingNode)
        .where(HostingNode.id == node_id)
        .with_for_update()
    )
    if node is None:
        return None

    claimed_count = int(
        db.scalar(
            select(func.count(HostingProjectOperation.id)).where(
                HostingProjectOperation.node_id == node_id,
                HostingProjectOperation.status == "claimed",
            )
        )
        or 0
    )
    if claimed_count >= limit:
        return None

    queued = db.scalars(
        select(HostingProjectOperation)
        .where(
            HostingProjectOperation.node_id == node_id,
            HostingProjectOperation.status == "queued",
        )
        .order_by(HostingProjectOperation.created_at.asc(), HostingProjectOperation.id.asc())
        .limit(128)
        .with_for_update(skip_locked=True)
    ).all()
    if not queued:
        return None

    row = min(queued, key=lambda candidate: _claim_sort_key(candidate, now=now))
    row.status = "claimed"
    row.claimed_at = now
    db.flush()
    return row
