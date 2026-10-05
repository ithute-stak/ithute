from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    HostingDatabase,
    HostingDeployment,
    HostingFailoverAttempt,
    HostingNode,
    HostingNodeAgent,
    HostingNodeHealthState,
    HostingProject,
    HostingProjectOperation,
    InfrastructureServer,
)
from app.services.hosting_edge_handoff import HostingOriginError, reconcile_project_edge
from app.services.hosting_placement import rank_nodes
from app.services.failure_domains import failure_domain_overlap, failure_domain_sort_key

FAILOVER_AFTER_SECONDS = int(os.getenv("ITHUTE_HOSTING_FAILOVER_AFTER_SECONDS", "300"))
ACTIVE_ATTEMPT_STATUSES = {"pending", "deploying", "edge_pending"}
ACTIVE_DEPLOYMENT_STATUSES = {"queued", "claimed", "running"}


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _audit(db: Session, project: HostingProject, action: str, metadata: dict) -> None:
    db.add(
        AuditLog(
            tenant_id=project.tenant_id,
            actor_user_id=None,
            action=action,
            resource_type="hosting_project",
            resource_id=str(project.id),
            metadata_json=json.dumps(metadata, sort_keys=True),
        )
    )


def _last_healthy(db: Session, project_id) -> HostingDeployment | None:
    return db.scalar(
        select(HostingDeployment)
        .where(
            HostingDeployment.project_id == project_id,
            HostingDeployment.status == "healthy",
        )
        .order_by(HostingDeployment.release_number.desc())
    )


def _active_deployment(db: Session, project_id) -> HostingDeployment | None:
    return db.scalar(
        select(HostingDeployment)
        .where(
            HostingDeployment.project_id == project_id,
            HostingDeployment.status.in_(ACTIVE_DEPLOYMENT_STATUSES),
        )
        .order_by(HostingDeployment.created_at.desc())
    )


def _attempt(db: Session, project_id, source_node_id) -> HostingFailoverAttempt | None:
    return db.scalar(
        select(HostingFailoverAttempt)
        .where(
            HostingFailoverAttempt.project_id == project_id,
            HostingFailoverAttempt.source_node_id == source_node_id,
            HostingFailoverAttempt.status.in_(list(ACTIVE_ATTEMPT_STATUSES) + ["recovery_required", "failed"]),
        )
        .order_by(HostingFailoverAttempt.created_at.desc())
    )


def _managed_database_dependency(db: Session, project: HostingProject) -> HostingDatabase | None:
    return db.scalar(
        select(HostingDatabase)
        .where(
            HostingDatabase.project_id == project.id,
            HostingDatabase.status.notin_(["deleting", "deleted", "failed"]),
        )
        .order_by(HostingDatabase.created_at.asc())
    )


def _next_release_number(db: Session, project_id) -> int:
    from sqlalchemy import func
    current = db.scalar(
        select(func.coalesce(func.max(HostingDeployment.release_number), 0))
        .where(HostingDeployment.project_id == project_id)
    ) or 0
    return int(current) + 1


def _server_for_node(db: Session, node_id) -> InfrastructureServer | None:
    return db.scalar(select(InfrastructureServer).where(InfrastructureServer.hosting_node_id == node_id))


def _eligible_target(db: Session, project: HostingProject, source_node_id, preferred_target_node_id=None) -> tuple[HostingNode | None, str | None]:
    ranked = rank_nodes(
        db,
        workload="application",
        storage_mb=project.storage_mb,
        memory_mb=project.memory_mb,
        cpu_millicores=project.cpu_millicores,
        lock=True,
    )
    source_server = _server_for_node(db, source_node_id)

    if preferred_target_node_id is not None:
        match = next((row for row in ranked if row["node"].id == preferred_target_node_id), None)
        if match is None:
            return None, "Requested replacement node does not exist."
        if match["node"].id == source_node_id:
            return None, "Replacement node must be different from the current node."
        if not match["eligible"]:
            return None, "Requested replacement node is not eligible: " + "; ".join(match["reasons"])
        target_server = _server_for_node(db, match["node"].id)
        overlap = failure_domain_overlap(source_server, target_server)
        if overlap["highest_risk"] in {"physical_host", "network_segment"}:
            return None, (
                "Requested replacement node shares a critical failure domain "
                f"({overlap['highest_risk']}) with the source node."
            )
        return match["node"], None

    eligible_rows = []
    for row in ranked:
        if row["node"].id == source_node_id or not row["eligible"]:
            continue
        target_server = _server_for_node(db, row["node"].id)
        overlap = failure_domain_overlap(source_server, target_server)
        eligible_rows.append((row, overlap))

    if eligible_rows:
        eligible_rows.sort(
            key=lambda item: failure_domain_sort_key(
                item[1],
                placement_score=float(item[0].get("score") or 0.0),
                name=item[0].get("name") or "",
                node_id=str(item[0]["node"].id),
            )
        )
        best_row, best_overlap = eligible_rows[0]
        if best_overlap["highest_risk"] in {"physical_host", "network_segment"}:
            return None, (
                "No healthy replacement node is outside the source node's critical "
                f"{best_overlap['highest_risk']} failure domain."
            )
        return best_row["node"], None

    details = [
        f"{row['name']}: {', '.join(row['reasons']) or 'not eligible'}"
        for row in ranked
        if row["node"].id != source_node_id
    ][:5]
    return None, "No healthy replacement node has enough safe capacity." + (f" Checked: {' | '.join(details)}" if details else "")


def _create_attempt(db: Session, project: HostingProject, source_node_id, status: str, reason: str | None) -> HostingFailoverAttempt:
    row = HostingFailoverAttempt(
        project_id=project.id,
        source_node_id=source_node_id,
        status=status,
        reason=reason,
    )
    db.add(row)
    db.flush()
    return row


def _prepare_attempt(db: Session, project: HostingProject, source_node_id, now: datetime) -> HostingFailoverAttempt:
    existing = _attempt(db, project.id, source_node_id)
    if existing is not None:
        return existing

    if project.failover_policy != "stateless_auto":
        return _create_attempt(
            db,
            project,
            source_node_id,
            "recovery_required",
            "Automatic relocation is disabled. Project local /data may contain state.",
        )

    local_database = _managed_database_dependency(db, project)
    if local_database is not None:
        return _create_attempt(
            db,
            project,
            source_node_id,
            "recovery_required",
            f"Managed {local_database.engine} database is attached to this project. Database replication/failover must be resolved before application relocation.",
        )

    previous = _last_healthy(db, project.id)
    if previous is None:
        return _create_attempt(
            db,
            project,
            source_node_id,
            "recovery_required",
            "No previously healthy immutable deployment is available for relocation.",
        )

    row = _create_attempt(db, project, source_node_id, "pending", None)
    row.started_at = now
    return row


def _queue_replacement(db: Session, attempt: HostingFailoverAttempt, project: HostingProject, now: datetime, preferred_target_node_id=None) -> None:
    if _active_deployment(db, project.id) is not None:
        attempt.reason = "Waiting for the project's current deployment operation to finish."
        return

    previous = _last_healthy(db, project.id)
    if previous is None:
        attempt.status = "recovery_required"
        attempt.reason = "No previously healthy immutable deployment is available for relocation."
        return

    target, error = _eligible_target(db, project, attempt.source_node_id, preferred_target_node_id)
    if target is None:
        attempt.reason = error
        return
    if db.get(HostingNodeAgent, target.id) is None:
        attempt.reason = "Selected replacement node has no hosting agent credential."
        return

    deployment = HostingDeployment(
        tenant_id=project.tenant_id,
        project_id=project.id,
        node_id=target.id,
        previous_deployment_id=previous.id,
        release_number=_next_release_number(db, project.id),
        image_ref=previous.image_ref,
        image_digest=previous.image_digest,
        source_commit=previous.source_commit,
        reset_data_volume=True,
        status="queued",
        requested_by_user_id=project.created_by_user_id,
    )
    db.add(deployment)
    db.flush()

    attempt.target_node_id = target.id
    attempt.deployment_id = deployment.id
    attempt.status = "deploying"
    attempt.reason = None
    project.status = "deploying"
    _audit(db, project, "hosting.failover.replacement_queued", {
        "attempt_id": str(attempt.id),
        "source_node_id": str(attempt.source_node_id),
        "target_node_id": str(target.id),
        "deployment_id": str(deployment.id),
        "release_number": deployment.release_number,
    })


def _queue_source_retirement(db: Session, project: HostingProject, source_node_id) -> HostingProjectOperation:
    existing = db.scalar(
        select(HostingProjectOperation)
        .where(
            HostingProjectOperation.project_id == project.id,
            HostingProjectOperation.node_id == source_node_id,
            HostingProjectOperation.operation == "retire",
            HostingProjectOperation.status.in_(["queued", "claimed"]),
        )
        .order_by(HostingProjectOperation.created_at.desc())
    )
    if existing is not None:
        return existing
    row = HostingProjectOperation(
        tenant_id=project.tenant_id,
        project_id=project.id,
        node_id=source_node_id,
        operation="retire",
        status="queued",
        requested_by_user_id=project.created_by_user_id,
    )
    db.add(row)
    db.flush()
    return row


def _finalize_attempt(db: Session, attempt: HostingFailoverAttempt, project: HostingProject, now: datetime) -> None:
    deployment = db.get(HostingDeployment, attempt.deployment_id) if attempt.deployment_id else None
    if deployment is None:
        attempt.status = "failed"
        attempt.reason = "Replacement deployment record is missing."
        attempt.completed_at = now
        return

    if deployment.status == "failed":
        attempt.status = "failed"
        attempt.reason = deployment.failure_message or "Replacement deployment failed."
        attempt.completed_at = now
        source = db.get(HostingNode, attempt.source_node_id)
        project.status = "running" if source and source.status == "active" else "failed"
        _audit(db, project, "hosting.failover.failed", {
            "attempt_id": str(attempt.id),
            "target_node_id": str(attempt.target_node_id) if attempt.target_node_id else None,
            "reason": attempt.reason,
        })
        return

    if deployment.status != "healthy" or not deployment.origin_url:
        return

    try:
        edge = reconcile_project_edge(db, project, deployment.origin_url)
    except HostingOriginError as exc:
        attempt.status = "edge_pending"
        attempt.edge_status = "pending_origin"
        attempt.reason = str(exc)
        return

    edge_status = str(edge.get("status") or "unknown")
    attempt.edge_status = edge_status
    if edge_status not in {"active", "not_requested"}:
        attempt.status = "edge_pending"
        attempt.reason = str(edge.get("error") or f"Waiting for edge state: {edge_status}")
        return

    old_node_id = project.node_id
    project.node_id = attempt.target_node_id
    project.image_ref = deployment.image_ref
    project.status = "running"
    attempt.status = "completed"
    attempt.reason = None
    attempt.completed_at = now
    retirement = _queue_source_retirement(db, project, attempt.source_node_id)
    _audit(db, project, "hosting.failover.completed", {
        "attempt_id": str(attempt.id),
        "source_node_id": str(attempt.source_node_id),
        "target_node_id": str(attempt.target_node_id),
        "previous_project_node_id": str(old_node_id) if old_node_id else None,
        "deployment_id": str(deployment.id),
        "edge_status": edge_status,
        "source_retirement_operation_id": str(retirement.id),
    })


def run_application_failover_reconcile(db: Session, limit: int = 200) -> dict:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=max(FAILOVER_AFTER_SECONDS, 60))

    unhealthy_states = db.scalars(
        select(HostingNodeHealthState)
        .where(
            HostingNodeHealthState.automation_enabled.is_(True),
            HostingNodeHealthState.health_status == "unhealthy",
            HostingNodeHealthState.unhealthy_since.is_not(None),
            HostingNodeHealthState.unhealthy_since <= cutoff,
            HostingNodeHealthState.last_transition == "auto_drained",
        )
        .limit(max(1, min(limit, 1000)))
    ).all()

    created = queued = completed = failed = recovery_required = pending = 0

    for state in unhealthy_states:
        source = db.get(HostingNode, state.node_id)
        if source is None or source.status != "draining" or source.accepts_new_projects:
            continue
        projects = db.scalars(
            select(HostingProject)
            .where(
                HostingProject.node_id == source.id,
                HostingProject.status != "suspended",
            )
            .order_by(HostingProject.created_at.asc())
        ).all()
        for project in projects:
            existing = _attempt(db, project.id, source.id)
            if existing is None:
                existing = _prepare_attempt(db, project, source.id, now)
                created += 1
            if existing.status == "pending":
                before = existing.deployment_id
                _queue_replacement(db, existing, project, now)
                if existing.deployment_id and existing.deployment_id != before:
                    queued += 1
            if existing.status in {"deploying", "edge_pending"}:
                before = existing.status
                _finalize_attempt(db, existing, project, now)
                if existing.status == "completed":
                    completed += 1
                elif existing.status == "failed" and before != "failed":
                    failed += 1
            if existing.status == "recovery_required":
                recovery_required += 1
            elif existing.status in ACTIVE_ATTEMPT_STATUSES:
                pending += 1

    # Clear unresolved pre-deployment records when the source recovers before
    # a replacement was actually staged. A later failure creates a fresh event.
    unresolved = db.scalars(
        select(HostingFailoverAttempt)
        .where(
            HostingFailoverAttempt.status.in_(["pending", "recovery_required"]),
            HostingFailoverAttempt.deployment_id.is_(None),
        )
        .limit(max(1, min(limit, 1000)))
    ).all()
    for attempt in unresolved:
        source = db.get(HostingNode, attempt.source_node_id)
        state = db.get(HostingNodeHealthState, attempt.source_node_id)
        still_failed = bool(
            source
            and source.status == "draining"
            and not source.accepts_new_projects
            and state
            and state.automation_enabled
            and state.health_status == "unhealthy"
            and state.last_transition == "auto_drained"
        )
        if not still_failed:
            attempt.status = "resolved_by_source_recovery"
            attempt.reason = "Source node recovered before a replacement deployment was staged."
            attempt.completed_at = now

    # Continue previously started relocation attempts even if the source node
    # recovers before cutover. This avoids abandoning a healthy staged release.
    active_attempts = db.scalars(
        select(HostingFailoverAttempt)
        .where(HostingFailoverAttempt.status.in_(["deploying", "edge_pending"]))
        .limit(max(1, min(limit, 1000)))
    ).all()
    for attempt in active_attempts:
        project = db.get(HostingProject, attempt.project_id)
        if project is None:
            attempt.status = "failed"
            attempt.reason = "Hosted project no longer exists."
            attempt.completed_at = now
            continue
        if project.node_id == attempt.target_node_id:
            continue
        before = attempt.status
        _finalize_attempt(db, attempt, project, now)
        if before != attempt.status and attempt.status == "completed":
            completed += 1
        elif before != attempt.status and attempt.status == "failed":
            failed += 1

    db.commit()
    return {
        "sources": len(unhealthy_states),
        "attempts_created": created,
        "replacements_queued": queued,
        "completed": completed,
        "failed": failed,
        "recovery_required": recovery_required,
        "pending": pending,
        "failover_after_seconds": FAILOVER_AFTER_SECONDS,
    }



def request_project_relocation(
    db: Session,
    project: HostingProject,
    *,
    preferred_target_node_id=None,
    reason: str = "manual_rebalance",
) -> HostingFailoverAttempt:
    now = datetime.now(timezone.utc)
    if project.node_id is None:
        raise ValueError("Project is not assigned to a hosting node")
    if project.failover_policy != "stateless_auto":
        raise ValueError("Project must explicitly use stateless_auto before it can be relocated")
    if project.status == "suspended":
        raise ValueError("Suspended projects cannot be relocated")
    existing = _attempt(db, project.id, project.node_id)
    if existing is not None:
        if existing.status in {"recovery_required", "failed"}:
            existing.status = "superseded"
            existing.completed_at = now
            existing.reason = "Superseded by an explicit stateless relocation request."
        else:
            raise ValueError("A failover or recovery action already exists for this project")
    local_database = _managed_database_dependency(db, project)
    if local_database is not None:
        raise ValueError("Project has an Ithute-managed database and cannot use application-only relocation until database failover is available")
    previous = _last_healthy(db, project.id)
    if previous is None:
        raise ValueError("Project has no healthy immutable deployment to relocate")

    attempt = _create_attempt(db, project, project.node_id, "pending", reason)
    attempt.started_at = now
    _queue_replacement(db, attempt, project, now, preferred_target_node_id)
    if attempt.deployment_id is None:
        if attempt.reason:
            raise ValueError(attempt.reason)
        raise ValueError("Replacement deployment could not be queued")
    return attempt


def failover_attempt_out(row: HostingFailoverAttempt) -> dict:
    return {
        "id": str(row.id),
        "project_id": str(row.project_id),
        "source_node_id": str(row.source_node_id),
        "target_node_id": str(row.target_node_id) if row.target_node_id else None,
        "deployment_id": str(row.deployment_id) if row.deployment_id else None,
        "status": row.status,
        "reason": row.reason,
        "edge_status": row.edge_status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
