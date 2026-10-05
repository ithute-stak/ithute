from datetime import datetime, timedelta, timezone

import pytest

from app.models import HostingNode, HostingProject
from app.services.resource_manager import node_resource_snapshot, reserve_capacity


def _node(db, owner):
    node = HostingNode(
        name=f"resource-node-{owner.id}",
        hostname=f"resource-{owner.id}.test",
        public_ip="192.0.2.44",
        allocatable_storage_mb=10_000,
        allocatable_memory_mb=8_000,
        allocatable_cpu_millicores=4_000,
        status="active",
        accepts_new_projects=True,
        created_by_user_id=owner.id,
    )
    db.add(node)
    db.flush()
    return node


def _project(db, tenant, owner, node, *, status, suffix, cpu, memory, storage):
    project = HostingProject(
        tenant_id=tenant.id,
        node_id=node.id,
        name=f"Resource Project {suffix}",
        slug=f"resource-{suffix}",
        hostname=f"resource-{suffix}.example.test",
        runtime="docker",
        source_branch="main",
        container_port=8080,
        health_path="/",
        storage_mb=storage,
        memory_mb=memory,
        cpu_millicores=cpu,
        pid_limit=256,
        status=status,
        failover_policy="manual",
        rules_version="2026-09-13",
        rules_accepted_at=datetime.now(timezone.utc),
        rules_accepted_by_user_id=owner.id,
        created_by_user_id=owner.id,
    )
    db.add(project)
    db.flush()
    return project


def test_resource_snapshot_separates_allocated_reserved_and_available(db, platform_owner, tenant_admin):
    _, tenant, _ = tenant_admin
    node = _node(db, platform_owner)
    _project(
        db, tenant, platform_owner, node,
        status="healthy", suffix="active",
        cpu=1_000, memory=2_000, storage=3_000,
    )
    _project(
        db, tenant, platform_owner, node,
        status="suspended", suffix="suspended",
        cpu=500, memory=500, storage=500,
    )

    reservation = reserve_capacity(
        db,
        node_id=node.id,
        cpu_millicores=500,
        memory_mb=1_000,
        storage_mb=2_000,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        created_by_user_id=platform_owner.id,
        purpose="placement-test",
    )

    snapshot = node_resource_snapshot(db, node)

    assert reservation.status == "active"
    assert snapshot["capacity"] == {
        "cpu_millicores": 4_000,
        "memory_mb": 8_000,
        "storage_mb": 10_000,
    }
    assert snapshot["allocated"] == {
        "cpu_millicores": 1_000,
        "memory_mb": 2_000,
        "storage_mb": 3_000,
    }
    assert snapshot["reserved"] == {
        "cpu_millicores": 500,
        "memory_mb": 1_000,
        "storage_mb": 2_000,
    }
    assert snapshot["available"] == {
        "cpu_millicores": 2_500,
        "memory_mb": 5_000,
        "storage_mb": 5_000,
    }
    assert snapshot["overcommitted"] == {
        "cpu_millicores": False,
        "memory_mb": False,
        "storage_mb": False,
    }
    db.rollback()


def test_resource_reservation_rejects_overbooking(db, platform_owner):
    node = _node(db, platform_owner)

    reserve_capacity(
        db,
        node_id=node.id,
        cpu_millicores=3_500,
        memory_mb=7_500,
        storage_mb=9_500,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        created_by_user_id=platform_owner.id,
    )

    with pytest.raises(ValueError, match="insufficient available capacity"):
        reserve_capacity(
            db,
            node_id=node.id,
            cpu_millicores=600,
            memory_mb=600,
            storage_mb=600,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            created_by_user_id=platform_owner.id,
        )
    db.rollback()


def test_expired_reservation_no_longer_consumes_available_capacity(db, platform_owner):
    node = _node(db, platform_owner)
    reservation = reserve_capacity(
        db,
        node_id=node.id,
        cpu_millicores=1_000,
        memory_mb=1_000,
        storage_mb=1_000,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
        created_by_user_id=platform_owner.id,
    )

    future = datetime.now(timezone.utc) + timedelta(minutes=2)
    snapshot = node_resource_snapshot(db, node, now=future)

    assert reservation.status == "expired"
    assert snapshot["reserved"] == {
        "cpu_millicores": 0,
        "memory_mb": 0,
        "storage_mb": 0,
    }
    assert snapshot["available"] == snapshot["capacity"]
    db.rollback()
