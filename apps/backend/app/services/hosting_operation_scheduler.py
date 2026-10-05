from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import HostingNode, HostingProjectOperation


DEFAULT_NODE_OPERATION_CONCURRENCY = 2
MAX_NODE_OPERATION_CONCURRENCY = 16
AGING_INTERVAL_SECONDS = 300
MAX_AGING_BONUS = 40
DEFAULT_OPERATION_LEASE_SECONDS = 120
MIN_OPERATION_LEASE_SECONDS = 30
MAX_OPERATION_LEASE_SECONDS = 900
MAX_OPERATION_ATTEMPTS = 5

_BASE_PRIORITY = {
    "retire": 10,
    "restart": 20,
    "logs": 60,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def operation_lease_seconds() -> int:
    raw = os.getenv("ITHUTE_HOSTING_OPERATION_LEASE_SECONDS", str(DEFAULT_OPERATION_LEASE_SECONDS))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_OPERATION_LEASE_SECONDS
    return max(MIN_OPERATION_LEASE_SECONDS, min(value, MAX_OPERATION_LEASE_SECONDS))


def reclaim_expired_project_operations(
    db: Session,
    *,
    node_id: UUID,
    now: datetime | None = None,
) -> dict:
    now = now or _now()
    rows = db.scalars(
        select(HostingProjectOperation)
        .where(
            HostingProjectOperation.node_id == node_id,
            HostingProjectOperation.status == "claimed",
            HostingProjectOperation.lease_expires_at.is_not(None),
            HostingProjectOperation.lease_expires_at <= now,
        )
        .with_for_update(skip_locked=True)
    ).all()

    requeued = failed = 0
    for row in rows:
        if int(row.attempt_count or 0) >= MAX_OPERATION_ATTEMPTS:
            row.status = "failed"
            row.failure_message = "Operation lease expired after maximum retry attempts"
            row.completed_at = now
            failed += 1
        else:
            row.status = "queued"
            row.failure_message = "Previous operation lease expired; retrying"
            row.claimed_at = None
            requeued += 1
        row.fencing_token = None
        row.lease_expires_at = None
        row.lease_heartbeat_at = None
    if rows:
        db.flush()
    return {"requeued": requeued, "failed": failed}


def renew_project_operation_lease(
    db: Session,
    *,
    row: HostingProjectOperation,
    fencing_token: str,
    now: datetime | None = None,
) -> bool:
    now = now or _now()
    if row.status != "claimed":
        return False
    if not row.fencing_token or not secrets.compare_digest(row.fencing_token, fencing_token):
        return False
    if row.lease_expires_at is None or row.lease_expires_at <= now:
        return False
    row.lease_heartbeat_at = now
    row.lease_expires_at = now + timedelta(seconds=operation_lease_seconds())
    db.flush()
    return True


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

    reclaim_expired_project_operations(db, node_id=node_id, now=now)

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
    row.attempt_count = int(row.attempt_count or 0) + 1
    row.fencing_token = secrets.token_urlsafe(32)
    row.lease_heartbeat_at = now
    row.lease_expires_at = now + timedelta(seconds=operation_lease_seconds())
    db.flush()
    return row
