from datetime import datetime, timezone
import json
import uuid

from app.models import (
    HostingNode,
    HostingNodeAgent,
    HostingPostgresReplicationGroup,
    HostingPostgresReplicationStandby,
)
from app.services.postgres_rpo_policy import (
    persist_primary_rpo_telemetry,
    queue_rpo_policy_operation,
    validate_rpo_request,
)


def _node(db, owner, suffix: str) -> HostingNode:
    row = HostingNode(
        name=f"rpo-{suffix}-{uuid.uuid4().hex[:6]}",
        hostname=f"rpo-{suffix}-{uuid.uuid4().hex[:6]}.example.test",
        allocatable_storage_mb=8192,
        allocatable_memory_mb=4096,
        allocatable_cpu_millicores=4000,
        status="active",
        accepts_new_projects=True,
        created_by_user_id=owner.id,
    )
    db.add(row)
    db.flush()
    return row


def _agent(db, owner, node, *, recovery: bool = False):
    row = HostingNodeAgent(
        node_id=node.id,
        token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        token_hint="ith_host_rpo",
        agent_version="ithute-hosting-agent/4",
        capabilities_json=json.dumps({
            "postgres_physical_replication": {
                "supported": True,
                "dedicated_cluster": True,
                "promotion_requires_source_fencing": True,
                "in_recovery": recovery,
            }
        }),
        last_seen_at=datetime.now(timezone.utc),
        rotated_at=datetime.now(timezone.utc),
        rotated_by_user_id=owner.id,
    )
    db.add(row)
    db.flush()
    return row


def _group(db, owner, primary, *, rpo_class="async", required=0):
    row = HostingPostgresReplicationGroup(
        name=f"rpo-group-{uuid.uuid4().hex[:6]}",
        primary_node_id=primary.id,
        status="active",
        rpo_class=rpo_class,
        required_sync_standbys=required,
        rpo_healthy=rpo_class == "async",
        created_by_user_id=owner.id,
    )
    db.add(row)
    db.flush()
    return row


def test_async_policy_rejects_nonzero_sync_requirement(db, platform_owner):
    primary = _node(db, platform_owner, "async")
    group = _group(db, platform_owner, primary)

    errors = validate_rpo_request(
        db,
        group=group,
        rpo_class="async",
        required_sync_standbys=1,
    )

    assert errors == ["async RPO class requires zero synchronous standbys"]
    db.rollback()


def test_sync_policy_requires_enough_fresh_healthy_standbys(db, platform_owner):
    primary = _node(db, platform_owner, "primary")
    standby_node = _node(db, platform_owner, "standby")
    _agent(db, platform_owner, primary, recovery=False)
    group = _group(db, platform_owner, primary)
    db.add(HostingPostgresReplicationStandby(
        group_id=group.id,
        node_id=standby_node.id,
        status="streaming",
        healthy=True,
        in_recovery=True,
        last_checked_at=datetime.now(timezone.utc),
    ))
    db.flush()

    assert validate_rpo_request(
        db,
        group=group,
        rpo_class="sync_flush",
        required_sync_standbys=1,
    ) == []
    errors = validate_rpo_request(
        db,
        group=group,
        rpo_class="sync_flush",
        required_sync_standbys=2,
    )
    assert any("only 1 are currently healthy" in error for error in errors)
    db.rollback()


def test_primary_heartbeat_confirms_sync_flush_policy(db, platform_owner):
    primary = _node(db, platform_owner, "flush")
    group = _group(db, platform_owner, primary, rpo_class="sync_flush", required=1)

    result = persist_primary_rpo_telemetry(
        db,
        node=primary,
        capabilities={
            "postgres_physical_replication": {
                "supported": True,
                "dedicated_cluster": True,
                "in_recovery": False,
                "primary_synchronous_commit": "on",
                "primary_synchronous_standby_names": "ANY 1 (*)",
                "primary_sync_standbys": 1,
            }
        },
    )

    assert result["status"] == "healthy"
    assert group.rpo_healthy is True
    assert group.observed_synchronous_commit == "on"
    assert group.observed_sync_standbys == 1
    assert group.rpo_last_checked_at is not None
    db.rollback()


def test_sync_apply_requires_remote_apply_not_plain_on(db, platform_owner):
    primary = _node(db, platform_owner, "apply")
    group = _group(db, platform_owner, primary, rpo_class="sync_apply", required=1)

    first = persist_primary_rpo_telemetry(
        db,
        node=primary,
        capabilities={
            "postgres_physical_replication": {
                "supported": True,
                "dedicated_cluster": True,
                "in_recovery": False,
                "primary_synchronous_commit": "on",
                "primary_synchronous_standby_names": "ANY 1 (*)",
                "primary_sync_standbys": 1,
            }
        },
    )
    assert first["status"] == "unhealthy"
    assert group.rpo_healthy is False

    second = persist_primary_rpo_telemetry(
        db,
        node=primary,
        capabilities={
            "postgres_physical_replication": {
                "supported": True,
                "dedicated_cluster": True,
                "in_recovery": False,
                "primary_synchronous_commit": "remote_apply",
                "primary_synchronous_standby_names": "ANY 1 (*)",
                "primary_sync_standbys": 1,
            }
        },
    )
    assert second["status"] == "healthy"
    assert group.rpo_healthy is True
    db.rollback()


def test_policy_queue_marks_group_unverified_until_heartbeat(db, platform_owner):
    primary = _node(db, platform_owner, "queue")
    group = _group(db, platform_owner, primary)

    operation = queue_rpo_policy_operation(
        db,
        group=group,
        rpo_class="sync_flush",
        required_sync_standbys=1,
        created_by_user_id=platform_owner.id,
    )

    assert operation.status == "queued"
    assert operation.node_id == primary.id
    assert group.rpo_class == "sync_flush"
    assert group.required_sync_standbys == 1
    assert group.rpo_healthy is False
    assert group.rpo_last_checked_at is None
    db.rollback()
