from datetime import datetime, timedelta, timezone
import uuid

from app.models import (
    HostingNode,
    HostingNodeAgent,
    HostingNodeHealthState,
    HostingPostgresGroupFailoverAttempt,
    HostingPostgresReplicationGroup,
    HostingPostgresReplicationStandby,
)
from app.services import postgres_rto_slo


def _node(db, owner, suffix: str) -> HostingNode:
    row = HostingNode(
        name=f"rto-{suffix}-{uuid.uuid4().hex[:6]}",
        hostname=f"rto-{suffix}-{uuid.uuid4().hex[:6]}.example.test",
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


def _group(db, owner, primary, *, auto=True, detection=30):
    row = HostingPostgresReplicationGroup(
        name=f"rto-group-{uuid.uuid4().hex[:6]}",
        primary_node_id=primary.id,
        status="active",
        auto_failover_enabled=auto,
        rto_target_seconds=300,
        detection_budget_seconds=detection,
        fencing_budget_seconds=120,
        promotion_budget_seconds=60,
        repair_budget_seconds=900,
        created_by_user_id=owner.id,
    )
    db.add(row)
    db.flush()
    return row


def test_auto_failover_creates_attempt_after_detection_budget_with_fresh_source_agent(
    db, platform_owner, monkeypatch
):
    now = datetime.now(timezone.utc)
    primary = _node(db, platform_owner, "primary")
    target = _node(db, platform_owner, "target")
    group = _group(db, platform_owner, primary, detection=30)
    standby = HostingPostgresReplicationStandby(
        group_id=group.id,
        node_id=target.id,
        status="streaming",
        healthy=True,
        in_recovery=True,
        last_checked_at=now,
    )
    db.add(standby)
    db.add(HostingNodeHealthState(
        node_id=primary.id,
        automation_enabled=True,
        health_status="unhealthy",
        unhealthy_since=now - timedelta(seconds=45),
        last_evaluated_at=now,
    ))
    db.add(HostingNodeAgent(
        node_id=primary.id,
        token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        token_hint="ith_rto_test",
        agent_version="ithute-hosting-agent/4",
        capabilities_json="{}",
        last_seen_at=now,
        rotated_at=now,
        rotated_by_user_id=platform_owner.id,
    ))
    db.flush()

    monkeypatch.setattr(
        postgres_rto_slo,
        "build_postgres_replication_group_plan",
        lambda *args, **kwargs: {
            "promotion_ready": True,
            "recommended_standby": {"standby_id": str(standby.id)},
            "blockers": [],
        },
    )

    result = postgres_rto_slo.reconcile_postgres_auto_failover(db, now=now)

    assert result["created"] == 1
    attempt = db.query(HostingPostgresGroupFailoverAttempt).filter(
        HostingPostgresGroupFailoverAttempt.group_id == group.id
    ).one()
    assert attempt.trigger == "health_automation"
    assert attempt.failure_detected_at == now - timedelta(seconds=45)
    assert attempt.source_node_id == primary.id
    assert attempt.target_node_id == target.id
    db.rollback()


def test_stale_source_without_external_fence_controller_blocks_auto_failover(
    db, platform_owner, monkeypatch
):
    now = datetime.now(timezone.utc)
    primary = _node(db, platform_owner, "stale")
    target = _node(db, platform_owner, "standby")
    group = _group(db, platform_owner, primary, detection=15)
    standby = HostingPostgresReplicationStandby(
        group_id=group.id,
        node_id=target.id,
        status="streaming",
        healthy=True,
        in_recovery=True,
        last_checked_at=now,
    )
    db.add(standby)
    db.add(HostingNodeHealthState(
        node_id=primary.id,
        automation_enabled=True,
        health_status="unhealthy",
        unhealthy_since=now - timedelta(minutes=5),
        last_evaluated_at=now,
    ))
    db.flush()

    monkeypatch.setattr(
        postgres_rto_slo,
        "build_postgres_replication_group_plan",
        lambda *args, **kwargs: {
            "promotion_ready": True,
            "recommended_standby": {"standby_id": str(standby.id)},
            "blockers": [],
        },
    )

    result = postgres_rto_slo.reconcile_postgres_auto_failover(db, now=now)

    assert result["created"] == 0
    assert result["blocked"] == 1
    assert result["items"][0]["status"] == "blocked_no_fencing_path"
    assert db.query(HostingPostgresGroupFailoverAttempt).count() == 0
    db.rollback()


def test_failover_slo_snapshot_measures_service_and_repair_windows():
    now = datetime.now(timezone.utc)
    group = HostingPostgresReplicationGroup(
        id=uuid.uuid4(),
        name="slo",
        primary_node_id=uuid.uuid4(),
        rto_target_seconds=300,
        detection_budget_seconds=60,
        fencing_budget_seconds=90,
        promotion_budget_seconds=60,
        repair_budget_seconds=600,
        created_by_user_id=uuid.uuid4(),
    )
    attempt = HostingPostgresGroupFailoverAttempt(
        id=uuid.uuid4(),
        group_id=group.id,
        standby_id=uuid.uuid4(),
        source_node_id=uuid.uuid4(),
        target_node_id=uuid.uuid4(),
        status="succeeded",
        trigger="health_automation",
        failure_detected_at=now,
        fence_started_at=now + timedelta(seconds=30),
        source_fenced_at=now + timedelta(seconds=80),
        promotion_started_at=now + timedelta(seconds=85),
        service_restored_at=now + timedelta(seconds=120),
        redundancy_restored_at=now + timedelta(seconds=420),
        rto_seconds=120,
        rto_met=True,
        repair_slo_met=True,
        created_by_user_id=uuid.uuid4(),
    )

    snapshot = postgres_rto_slo.failover_slo_snapshot(group=group, attempt=attempt)

    assert snapshot["phase_seconds"]["detection_to_fence_start"] == 30
    assert snapshot["phase_seconds"]["fencing"] == 50
    assert snapshot["phase_seconds"]["promotion_and_control_plane_cutover"] == 35
    assert snapshot["phase_seconds"]["service_restoration"] == 120
    assert snapshot["phase_seconds"]["redundancy_repair"] == 300
    assert snapshot["phase_budget_met"]["detection"] is True
    assert snapshot["phase_budget_met"]["fencing"] is True
    assert snapshot["phase_budget_met"]["promotion_and_control_plane_cutover"] is True
    assert snapshot["phase_budget_met"]["redundancy_repair"] is True
    assert snapshot["rto_met"] is True


def test_health_daemon_runs_postgres_auto_failover_reconcile():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    text = (root / "apps/backend/app/services/hosting_node_health_daemon.py").read_text()
    assert "reconcile_postgres_auto_failover" in text
    assert '"hosting_postgres_auto_failover_reconcile"' in text


def test_rto_policy_never_treats_heartbeat_loss_as_fence_proof():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    text = (root / "apps/backend/app/services/postgres_rto_slo.py").read_text()
    assert "blocked_no_fencing_path" in text
    assert "queue_external_fence_for_postgres_group_failover" in text
    assert "source_unreachable" not in text
    assert "force_promote" not in text
