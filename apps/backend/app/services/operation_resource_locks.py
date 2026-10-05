from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    HostingOperationResourceLock,
    HostingOperationResourceWait,
    HostingProjectOperation,
)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def canonical_resource_keys(resource_keys: list[str]) -> list[str]:
    return sorted({str(key).strip() for key in resource_keys if str(key).strip()})


def release_operation_resources(db: Session, operation_id: UUID) -> None:
    db.execute(delete(HostingOperationResourceWait).where(HostingOperationResourceWait.operation_id == operation_id))
    db.execute(delete(HostingOperationResourceLock).where(HostingOperationResourceLock.operation_id == operation_id))
    db.flush()


def _active_locks(db: Session, *, now: datetime) -> dict[str, HostingOperationResourceLock]:
    rows = db.scalars(select(HostingOperationResourceLock).with_for_update()).all()
    active: dict[str, HostingOperationResourceLock] = {}
    for row in rows:
        expires = _utc(row.lease_expires_at)
        if expires is None or expires <= now:
            db.delete(row)
            continue
        active[row.resource_key] = row
    db.flush()
    return active


def build_wait_for_graph(
    locks: list[HostingOperationResourceLock],
    waits: list[HostingOperationResourceWait],
) -> dict[UUID, set[UUID]]:
    holder_by_resource = {row.resource_key: row.operation_id for row in locks}
    graph: dict[UUID, set[UUID]] = defaultdict(set)
    for wait in waits:
        holder = holder_by_resource.get(wait.resource_key)
        if holder is not None and holder != wait.operation_id:
            graph[wait.operation_id].add(holder)
            graph.setdefault(holder, set())
    return graph


def detect_deadlock_cycle(graph: dict[UUID, set[UUID]]) -> list[UUID]:
    visiting: set[UUID] = set()
    visited: set[UUID] = set()
    stack: list[UUID] = []

    def visit(node: UUID) -> list[UUID]:
        if node in visiting:
            index = stack.index(node)
            return stack[index:] + [node]
        if node in visited:
            return []
        visiting.add(node)
        stack.append(node)
        for neighbor in sorted(graph.get(node, set()), key=str):
            cycle = visit(neighbor)
            if cycle:
                return cycle
        stack.pop()
        visiting.remove(node)
        visited.add(node)
        return []

    for node in sorted(graph, key=str):
        cycle = visit(node)
        if cycle:
            return cycle
    return []


def acquire_operation_resources(
    db: Session,
    *,
    operation: HostingProjectOperation,
    resource_keys: list[str],
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    keys = canonical_resource_keys(resource_keys)
    if not keys:
        return {"acquired": True, "blocked_on": [], "deadlock_cycle": []}
    if operation.status != "claimed" or not operation.fencing_token or operation.lease_expires_at is None:
        return {"acquired": False, "blocked_on": keys, "deadlock_cycle": []}

    active = _active_locks(db, now=now)
    conflicting = [
        key for key in keys
        if key in active and active[key].operation_id != operation.id
    ]

    db.execute(delete(HostingOperationResourceWait).where(HostingOperationResourceWait.operation_id == operation.id))

    if conflicting:
        for key in conflicting:
            db.add(HostingOperationResourceWait(operation_id=operation.id, resource_key=key))
        db.flush()
        locks = db.scalars(select(HostingOperationResourceLock)).all()
        waits = db.scalars(select(HostingOperationResourceWait)).all()
        cycle = detect_deadlock_cycle(build_wait_for_graph(locks, waits))
        return {
            "acquired": False,
            "blocked_on": conflicting,
            "deadlock_cycle": [str(item) for item in cycle],
        }

    lease_expires_at = _utc(operation.lease_expires_at)
    for key in keys:
        row = active.get(key)
        if row is None:
            db.add(HostingOperationResourceLock(
                resource_key=key,
                operation_id=operation.id,
                fencing_token=operation.fencing_token,
                lease_expires_at=lease_expires_at,
            ))
        else:
            row.fencing_token = operation.fencing_token
            row.lease_expires_at = lease_expires_at
    db.flush()
    return {"acquired": True, "blocked_on": [], "deadlock_cycle": []}


def renew_operation_resource_leases(
    db: Session,
    *,
    operation: HostingProjectOperation,
) -> None:
    if not operation.fencing_token or operation.lease_expires_at is None:
        return
    rows = db.scalars(
        select(HostingOperationResourceLock).where(
            HostingOperationResourceLock.operation_id == operation.id
        ).with_for_update()
    ).all()
    for row in rows:
        if row.fencing_token == operation.fencing_token:
            row.lease_expires_at = operation.lease_expires_at
    db.flush()
