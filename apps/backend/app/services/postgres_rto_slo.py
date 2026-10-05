from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    HostingNodeAgent,
    HostingNodeHealthState,
    HostingPostgresGroupFailoverAttempt,
    HostingPostgresReplicationGroup,
    HostingPostgresReplicationStandby,
    HostingPostgresTopologyRepair,
    InfrastructureFenceController,
    InfrastructureServer,
)
from app.services.external_fencing import queue_external_fence_for_postgres_group_failover
from app.services.hosting_node_health import HEARTBEAT_GRACE_SECONDS
from app.services.postgres_replication_groups import build_postgres_replication_group_plan


ACTIVE_FAILOVER = ("requested", "fence_claimed", "source_fenced", "promote_claimed")


def _utc(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _agent_fresh(agent: HostingNodeAgent | None, now: datetime) -> bool:
    seen = _utc(agent.last_seen_at) if agent else None
    return bool(seen and seen >= now - timedelta(seconds=HEARTBEAT_GRACE_SECONDS))


def _matching_external_fence_available(
    db: Session,
    *,
    group: HostingPostgresReplicationGroup,
) -> bool:
    server = db.scalar(
        select(InfrastructureServer).where(
            InfrastructureServer.hosting_node_id == group.primary_node_id
        )
    )
    if server is None:
        return False
    controllers = db.scalars(
        select(InfrastructureFenceController).where(
            InfrastructureFenceController.status == "active"
        )
    ).all()
    return any(
        row.provider is None
        or (server.provider and row.provider.lower() == server.provider.lower())
        for row in controllers
    )


def _audit(db: Session, group, action: str, metadata: dict) -> None:
    db.add(
        AuditLog(
            actor_user_id=None,
            action=action,
            resource_type="hosting_postgres_replication_group",
            resource_id=str(group.id),
            metadata_json=json.dumps(metadata, sort_keys=True),
        )
    )


def reconcile_postgres_auto_failover(
    db: Session,
    *,
    now: datetime | None = None,
    limit: int = 200,
) -> dict:
    now = now or datetime.now(timezone.utc)
    groups = db.scalars(
        select(HostingPostgresReplicationGroup)
        .where(
            HostingPostgresReplicationGroup.auto_failover_enabled.is_(True),
            HostingPostgresReplicationGroup.status == "active",
        )
        .limit(max(1, min(limit, 1000)))
    ).all()

    checked = eligible = created = blocked = 0
    items: list[dict] = []
    for group in groups:
        checked += 1
        state = db.get(HostingNodeHealthState, group.primary_node_id)
        unhealthy_since = _utc(state.unhealthy_since) if state else None
        if state is None or state.health_status != "unhealthy" or unhealthy_since is None:
            continue

        unhealthy_for = int((now - unhealthy_since).total_seconds())
        if unhealthy_for < int(group.detection_budget_seconds):
            continue
        eligible += 1

        active = db.scalar(
            select(HostingPostgresGroupFailoverAttempt.id).where(
                HostingPostgresGroupFailoverAttempt.group_id == group.id,
                HostingPostgresGroupFailoverAttempt.status.in_(ACTIVE_FAILOVER),
            )
        )
        if active is not None:
            continue

        plan = build_postgres_replication_group_plan(db, group=group, now=now)
        recommended = plan.get("recommended_standby")
        if not plan.get("promotion_ready") or not isinstance(recommended, dict):
            blocked += 1
            items.append({
                "group_id": str(group.id),
                "status": "blocked_no_safe_standby",
                "reasons": plan.get("blockers", []),
            })
            continue

        source_agent = db.get(HostingNodeAgent, group.primary_node_id)
        source_agent_fresh = _agent_fresh(source_agent, now)
        external_fence_available = _matching_external_fence_available(db, group=group)
        if not source_agent_fresh and not external_fence_available:
            blocked += 1
            items.append({
                "group_id": str(group.id),
                "status": "blocked_no_fencing_path",
            })
            continue

        standby = db.scalar(
            select(HostingPostgresReplicationStandby).where(
                HostingPostgresReplicationStandby.id == recommended["standby_id"],
                HostingPostgresReplicationStandby.group_id == group.id,
            )
        )
        if standby is None:
            blocked += 1
            continue

        attempt = HostingPostgresGroupFailoverAttempt(
            group_id=group.id,
            standby_id=standby.id,
            source_node_id=group.primary_node_id,
            target_node_id=standby.node_id,
            status="requested",
            trigger="health_automation",
            failure_detected_at=unhealthy_since,
            created_by_user_id=group.created_by_user_id,
        )
        db.add(attempt)
        db.flush()

        external = queue_external_fence_for_postgres_group_failover(
            db,
            failover=attempt,
            requested_by_user_id=group.created_by_user_id,
        )
        if external is not None:
            attempt.fence_started_at = now

        _audit(
            db,
            group,
            "hosting.postgres_replication_group.auto_failover.requested",
            {
                "attempt_id": str(attempt.id),
                "source_node_id": str(attempt.source_node_id),
                "target_node_id": str(attempt.target_node_id),
                "unhealthy_for_seconds": unhealthy_for,
                "detection_budget_seconds": group.detection_budget_seconds,
                "source_agent_fresh": source_agent_fresh,
                "external_fence_attempt_id": str(external.id) if external else None,
            },
        )
        created += 1
        items.append({
            "group_id": str(group.id),
            "attempt_id": str(attempt.id),
            "status": "requested",
        })

    db.commit()
    return {
        "checked": checked,
        "eligible": eligible,
        "created": created,
        "blocked": blocked,
        "items": items,
    }


def failover_slo_snapshot(
    *,
    group: HostingPostgresReplicationGroup,
    attempt: HostingPostgresGroupFailoverAttempt,
) -> dict:
    detected = _utc(attempt.failure_detected_at) or _utc(attempt.created_at)
    fence_started = _utc(attempt.fence_started_at)
    fenced = _utc(attempt.source_fenced_at)
    promotion_started = _utc(attempt.promotion_started_at)
    restored = _utc(attempt.service_restored_at)
    redundancy = _utc(attempt.redundancy_restored_at)

    def elapsed(start, end):
        if start is None or end is None:
            return None
        return max(0, int((end - start).total_seconds()))

    phase_seconds = {
        "detection_to_fence_start": elapsed(detected, fence_started),
        "fencing": elapsed(fence_started, fenced),
        "promotion_and_control_plane_cutover": elapsed(promotion_started, restored),
        "service_restoration": elapsed(detected, restored),
        "redundancy_repair": elapsed(restored, redundancy),
    }

    def within(value, budget):
        return None if value is None else value <= int(budget)

    return {
        "trigger": attempt.trigger,
        "status": attempt.status,
        "rto_target_seconds": group.rto_target_seconds,
        "rto_seconds": attempt.rto_seconds,
        "rto_met": attempt.rto_met,
        "repair_budget_seconds": group.repair_budget_seconds,
        "repair_slo_met": attempt.repair_slo_met,
        "phase_seconds": phase_seconds,
        "phase_budget_met": {
            "detection": within(phase_seconds["detection_to_fence_start"], group.detection_budget_seconds),
            "fencing": within(phase_seconds["fencing"], group.fencing_budget_seconds),
            "promotion_and_control_plane_cutover": within(
                phase_seconds["promotion_and_control_plane_cutover"],
                group.promotion_budget_seconds,
            ),
            "redundancy_repair": within(
                phase_seconds["redundancy_repair"],
                group.repair_budget_seconds,
            ),
        },
        "timestamps": {
            "failure_detected_at": detected.isoformat() if detected else None,
            "fence_started_at": fence_started.isoformat() if fence_started else None,
            "source_fenced_at": fenced.isoformat() if fenced else None,
            "promotion_started_at": promotion_started.isoformat() if promotion_started else None,
            "service_restored_at": restored.isoformat() if restored else None,
            "redundancy_restored_at": redundancy.isoformat() if redundancy else None,
        },
    }


def mark_redundancy_restored_if_ready(
    db: Session,
    *,
    group_id,
    now: datetime | None = None,
) -> HostingPostgresGroupFailoverAttempt | None:
    now = now or datetime.now(timezone.utc)
    attempt = db.scalar(
        select(HostingPostgresGroupFailoverAttempt)
        .where(
            HostingPostgresGroupFailoverAttempt.group_id == group_id,
            HostingPostgresGroupFailoverAttempt.status == "succeeded",
            HostingPostgresGroupFailoverAttempt.redundancy_restored_at.is_(None),
        )
        .order_by(HostingPostgresGroupFailoverAttempt.promoted_at.desc())
        .with_for_update()
    )
    if attempt is None or attempt.service_restored_at is None:
        return None

    active_repairs = db.scalar(
        select(HostingPostgresTopologyRepair.id).where(
            HostingPostgresTopologyRepair.group_id == group_id,
            HostingPostgresTopologyRepair.status.in_(["queued", "claimed"]),
        )
    )
    if active_repairs is not None:
        return None

    group = db.get(HostingPostgresReplicationGroup, group_id)
    if group is None:
        return None
    healthy_standbys = db.scalars(
        select(HostingPostgresReplicationStandby).where(
            HostingPostgresReplicationStandby.group_id == group_id,
            HostingPostgresReplicationStandby.healthy.is_(True),
            HostingPostgresReplicationStandby.status.in_(["streaming", "ready"]),
            HostingPostgresReplicationStandby.in_recovery.is_(True),
        )
    ).all()
    minimum = max(1, int(group.required_sync_standbys or 0))
    if len(healthy_standbys) < minimum:
        return None

    attempt.redundancy_restored_at = now
    repair_seconds = max(
        0,
        int((now - _utc(attempt.service_restored_at)).total_seconds()),
    )
    attempt.repair_slo_met = repair_seconds <= int(group.repair_budget_seconds)
    _audit(
        db,
        group,
        "hosting.postgres_replication_group.redundancy_restored",
        {
            "attempt_id": str(attempt.id),
            "healthy_standbys": len(healthy_standbys),
            "required_standbys": minimum,
            "repair_seconds": repair_seconds,
            "repair_budget_seconds": group.repair_budget_seconds,
            "repair_slo_met": attempt.repair_slo_met,
        },
    )
    db.flush()
    return attempt
