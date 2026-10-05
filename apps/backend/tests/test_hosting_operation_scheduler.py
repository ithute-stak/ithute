from datetime import datetime, timedelta, timezone

from app.models import HostingNode, HostingProject, HostingProjectOperation
from app.services.hosting_operation_scheduler import (
    claim_next_project_operation,
    operation_effective_priority,
)


def _node(db, owner):
    node = HostingNode(
        name=f"operation-node-{owner.id}",
        hostname=f"operation-{owner.id}.test",
        public_ip="192.0.2.88",
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


def _project(db, tenant, owner, node):
    project = HostingProject(
        tenant_id=tenant.id,
        node_id=node.id,
        name=f"Scheduler Project {owner.id}",
        slug=f"scheduler-{owner.id}",
        hostname=f"scheduler-{owner.id}.example.test",
        runtime="docker",
        source_branch="main",
        container_port=8080,
        health_path="/",
        storage_mb=512,
        memory_mb=512,
        cpu_millicores=500,
        pid_limit=256,
        status="running",
        failover_policy="manual",
        rules_version="2026-09-13",
        rules_accepted_at=datetime.now(timezone.utc),
        rules_accepted_by_user_id=owner.id,
        created_by_user_id=owner.id,
    )
    db.add(project)
    db.flush()
    return project


def _operation(db, tenant, owner, project, node, operation, created_at):
    row = HostingProjectOperation(
        tenant_id=tenant.id,
        project_id=project.id,
        node_id=node.id,
        operation=operation,
        status="queued",
        requested_by_user_id=owner.id,
        created_at=created_at,
    )
    db.add(row)
    db.flush()
    return row


def test_operation_priority_ages_waiting_work():
    now = datetime.now(timezone.utc)
    fresh_logs = operation_effective_priority("logs", now, now=now)
    old_logs = operation_effective_priority("logs", now - timedelta(hours=4), now=now)
    restart = operation_effective_priority("restart", now, now=now)

    assert restart < fresh_logs
    assert old_logs < fresh_logs
    assert old_logs <= restart


def test_operation_scheduler_prefers_priority_but_ages_old_work(db, platform_owner, tenant_admin):
    _, tenant, _ = tenant_admin
    now = datetime.now(timezone.utc)
    node = _node(db, platform_owner)
    project = _project(db, tenant, platform_owner, node)

    old_logs = _operation(
        db, tenant, platform_owner, project, node, "logs",
        now - timedelta(hours=4),
    )
    fresh_restart = _operation(
        db, tenant, platform_owner, project, node, "restart",
        now - timedelta(seconds=10),
    )

    claimed = claim_next_project_operation(
        db,
        node_id=node.id,
        now=now,
        concurrency_limit=2,
    )

    assert claimed is not None
    assert claimed.id == old_logs.id
    assert claimed.status == "claimed"
    assert fresh_restart.status == "queued"
    db.rollback()


def test_operation_scheduler_enforces_node_concurrency_limit(db, platform_owner, tenant_admin):
    _, tenant, _ = tenant_admin
    now = datetime.now(timezone.utc)
    node = _node(db, platform_owner)
    project = _project(db, tenant, platform_owner, node)

    active = _operation(db, tenant, platform_owner, project, node, "restart", now - timedelta(minutes=2))
    active.status = "claimed"
    active.claimed_at = now - timedelta(minutes=1)
    queued = _operation(db, tenant, platform_owner, project, node, "logs", now)

    claimed = claim_next_project_operation(
        db,
        node_id=node.id,
        now=now,
        concurrency_limit=1,
    )

    assert claimed is None
    assert queued.status == "queued"
    db.rollback()
