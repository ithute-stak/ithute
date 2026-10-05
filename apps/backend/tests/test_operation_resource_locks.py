from datetime import datetime, timedelta, timezone
import uuid

from sqlalchemy import select

from app.models import (
    HostingNode,
    HostingOperationResourceLock,
    HostingOperationResourceWait,
    HostingProject,
    HostingProjectOperation,
)
from app.services.operation_resource_locks import (
    acquire_operation_resources,
    build_wait_for_graph,
    canonical_resource_keys,
    detect_deadlock_cycle,
    release_operation_resources,
)


def _operation(db, tenant, owner, *, suffix: str) -> HostingProjectOperation:
    now = datetime.now(timezone.utc)
    node = HostingNode(
        name=f"lock-node-{suffix}-{uuid.uuid4().hex[:6]}",
        hostname=f"lock-{suffix}-{uuid.uuid4().hex[:6]}.example.test",
        allocatable_storage_mb=4096,
        allocatable_memory_mb=4096,
        allocatable_cpu_millicores=4000,
        status="active",
        accepts_new_projects=True,
        created_by_user_id=owner.id,
    )
    db.add(node)
    db.flush()
    project = HostingProject(
        tenant_id=tenant.id,
        node_id=node.id,
        name=f"Lock project {suffix}",
        slug=f"lock-{suffix}-{uuid.uuid4().hex[:8]}",
        runtime="docker",
        source_branch="main",
        container_port=8080,
        health_path="/",
        storage_mb=128,
        memory_mb=128,
        cpu_millicores=100,
        pid_limit=64,
        status="running",
        failover_policy="manual",
        rules_version="2026-09-13",
        rules_accepted_at=now,
        rules_accepted_by_user_id=owner.id,
        created_by_user_id=owner.id,
    )
    db.add(project)
    db.flush()
    operation = HostingProjectOperation(
        tenant_id=tenant.id,
        project_id=project.id,
        node_id=node.id,
        operation="restart",
        status="claimed",
        requested_by_user_id=owner.id,
        claimed_at=now,
        attempt_count=1,
        fencing_token=("f" + uuid.uuid4().hex)[:32],
        lease_expires_at=now + timedelta(minutes=2),
        lease_heartbeat_at=now,
    )
    db.add(operation)
    db.flush()
    return operation


def test_canonical_resource_keys_are_sorted_and_unique():
    assert canonical_resource_keys(["b", "a", "b", ""]) == ["a", "b"]


def test_wait_for_graph_detects_cycle():
    a, b = uuid.uuid4(), uuid.uuid4()
    now = datetime.now(timezone.utc)
    locks = [
        HostingOperationResourceLock(resource_key="r1", operation_id=a, fencing_token="a" * 32, lease_expires_at=now + timedelta(minutes=1)),
        HostingOperationResourceLock(resource_key="r2", operation_id=b, fencing_token="b" * 32, lease_expires_at=now + timedelta(minutes=1)),
    ]
    waits = [
        HostingOperationResourceWait(operation_id=a, resource_key="r2"),
        HostingOperationResourceWait(operation_id=b, resource_key="r1"),
    ]

    cycle = detect_deadlock_cycle(build_wait_for_graph(locks, waits))

    assert cycle
    assert cycle[0] == cycle[-1]
    assert set(cycle[:-1]) == {a, b}


def test_atomic_resource_acquire_blocks_without_partial_locks(db, tenant_admin, platform_owner):
    _, tenant, _ = tenant_admin
    now = datetime.now(timezone.utc)
    owner = _operation(db, tenant, platform_owner, suffix="owner")
    waiter = _operation(db, tenant, platform_owner, suffix="waiter")
    db.add(
        HostingOperationResourceLock(
            resource_key="resource:b",
            operation_id=owner.id,
            fencing_token=owner.fencing_token,
            lease_expires_at=owner.lease_expires_at,
        )
    )
    db.flush()

    result = acquire_operation_resources(
        db,
        operation=waiter,
        resource_keys=["resource:a", "resource:b"],
        now=now,
    )

    assert result["acquired"] is False
    assert result["blocked_on"] == ["resource:b"]
    assert db.scalar(select(HostingOperationResourceLock).where(
        HostingOperationResourceLock.operation_id == waiter.id
    )) is None
    waits = db.scalars(select(HostingOperationResourceWait).where(
        HostingOperationResourceWait.operation_id == waiter.id
    )).all()
    assert [row.resource_key for row in waits] == ["resource:b"]
    db.rollback()


def test_release_operation_resources_clears_locks_and_waits(db, tenant_admin, platform_owner):
    _, tenant, _ = tenant_admin
    operation = _operation(db, tenant, platform_owner, suffix="release")
    db.add(
        HostingOperationResourceLock(
            resource_key="resource:a",
            operation_id=operation.id,
            fencing_token=operation.fencing_token,
            lease_expires_at=operation.lease_expires_at,
        )
    )
    db.add(HostingOperationResourceWait(operation_id=operation.id, resource_key="resource:b"))
    db.flush()

    release_operation_resources(db, operation.id)

    assert db.scalar(select(HostingOperationResourceLock).where(
        HostingOperationResourceLock.operation_id == operation.id
    )) is None
    assert db.scalar(select(HostingOperationResourceWait).where(
        HostingOperationResourceWait.operation_id == operation.id
    )) is None
    db.rollback()
