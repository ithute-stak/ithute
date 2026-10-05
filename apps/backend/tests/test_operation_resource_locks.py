from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import uuid

from app.models import HostingOperationResourceLock, HostingOperationResourceWait
from app.services.operation_resource_locks import (
    acquire_operation_resources,
    build_wait_for_graph,
    canonical_resource_keys,
    detect_deadlock_cycle,
    release_operation_resources,
)


def test_canonical_resource_keys_are_sorted_and_unique():
    assert canonical_resource_keys(["b", "a", "b", ""]) == ["a", "b"]


def test_wait_for_graph_detects_cycle():
    a, b = uuid.uuid4(), uuid.uuid4()
    locks = [
        HostingOperationResourceLock(
            resource_key="r1",
            operation_id=a,
            fencing_token="a" * 32,
            lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
        ),
        HostingOperationResourceLock(
            resource_key="r2",
            operation_id=b,
            fencing_token="b" * 32,
            lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
        ),
    ]
    waits = [
        HostingOperationResourceWait(operation_id=a, resource_key="r2"),
        HostingOperationResourceWait(operation_id=b, resource_key="r1"),
    ]

    graph = build_wait_for_graph(locks, waits)
    cycle = detect_deadlock_cycle(graph)

    assert cycle
    assert cycle[0] == cycle[-1]
    assert {str(item) for item in cycle[:-1]} == {str(a), str(b)}


def test_atomic_resource_acquire_blocks_without_partial_locks(db):
    now = datetime.now(timezone.utc)
    owner = uuid.uuid4()
    waiter = uuid.uuid4()

    db.add(
        HostingOperationResourceLock(
            resource_key="resource:b",
            operation_id=owner,
            fencing_token="o" * 32,
            lease_expires_at=now + timedelta(minutes=1),
        )
    )
    db.flush()

    operation = SimpleNamespace(
        id=waiter,
        status="claimed",
        fencing_token="w" * 32,
        lease_expires_at=now + timedelta(minutes=1),
    )
    result = acquire_operation_resources(
        db,
        operation=operation,
        resource_keys=["resource:a", "resource:b"],
        now=now,
    )

    assert result["acquired"] is False
    assert result["blocked_on"] == ["resource:b"]
    own_locks = db.query(HostingOperationResourceLock).filter(
        HostingOperationResourceLock.operation_id == waiter
    ).all()
    assert own_locks == []
    waits = db.query(HostingOperationResourceWait).filter(
        HostingOperationResourceWait.operation_id == waiter
    ).all()
    assert [row.resource_key for row in waits] == ["resource:b"]
    db.rollback()


def test_release_operation_resources_clears_locks_and_waits(db):
    now = datetime.now(timezone.utc)
    operation_id = uuid.uuid4()
    db.add(
        HostingOperationResourceLock(
            resource_key="resource:a",
            operation_id=operation_id,
            fencing_token="f" * 32,
            lease_expires_at=now + timedelta(minutes=1),
        )
    )
    db.add(HostingOperationResourceWait(operation_id=operation_id, resource_key="resource:b"))
    db.flush()

    release_operation_resources(db, operation_id)

    assert db.query(HostingOperationResourceLock).filter(
        HostingOperationResourceLock.operation_id == operation_id
    ).count() == 0
    assert db.query(HostingOperationResourceWait).filter(
        HostingOperationResourceWait.operation_id == operation_id
    ).count() == 0
    db.rollback()
