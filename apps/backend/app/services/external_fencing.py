from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    HostingDatabaseFailoverAttempt,
    HostingPostgresGroupFailoverAttempt,
    InfrastructureFenceAttempt,
    InfrastructureFenceController,
    InfrastructureServer,
)


def queue_external_fence_for_database_failover(
    db: Session,
    *,
    failover: HostingDatabaseFailoverAttempt,
    requested_by_user_id,
) -> InfrastructureFenceAttempt | None:
    server = db.scalar(
        select(InfrastructureServer).where(
            InfrastructureServer.hosting_node_id == failover.source_node_id
        )
    )
    if server is None:
        return None

    controllers = db.scalars(
        select(InfrastructureFenceController)
        .where(InfrastructureFenceController.status == "active")
        .order_by(InfrastructureFenceController.created_at.asc(), InfrastructureFenceController.id.asc())
    ).all()
    matching = [
        row for row in controllers
        if row.provider is None or (server.provider and row.provider.lower() == server.provider.lower())
    ]
    if not matching:
        return None

    existing = db.scalar(
        select(InfrastructureFenceAttempt).where(
            InfrastructureFenceAttempt.database_failover_attempt_id == failover.id,
            InfrastructureFenceAttempt.status.in_(["queued", "claimed", "succeeded"]),
        )
    )
    if existing is not None:
        return existing

    row = InfrastructureFenceAttempt(
        server_id=server.id,
        controller_id=matching[0].id,
        database_failover_attempt_id=failover.id,
        status="queued",
        requested_by_user_id=requested_by_user_id,
    )
    db.add(row)
    db.flush()
    return row



def queue_external_fence_for_postgres_group_failover(
    db: Session,
    *,
    failover: HostingPostgresGroupFailoverAttempt,
    requested_by_user_id,
) -> InfrastructureFenceAttempt | None:
    server = db.scalar(
        select(InfrastructureServer).where(
            InfrastructureServer.hosting_node_id == failover.source_node_id
        )
    )
    if server is None:
        return None

    controllers = db.scalars(
        select(InfrastructureFenceController)
        .where(InfrastructureFenceController.status == "active")
        .order_by(InfrastructureFenceController.created_at.asc(), InfrastructureFenceController.id.asc())
    ).all()
    matching = [
        row for row in controllers
        if row.provider is None or (server.provider and row.provider.lower() == server.provider.lower())
    ]
    if not matching:
        return None

    existing = db.scalar(
        select(InfrastructureFenceAttempt).where(
            InfrastructureFenceAttempt.postgres_group_failover_attempt_id == failover.id,
            InfrastructureFenceAttempt.status.in_(["queued", "claimed", "succeeded"]),
        )
    )
    if existing is not None:
        return existing

    row = InfrastructureFenceAttempt(
        server_id=server.id,
        controller_id=matching[0].id,
        postgres_group_failover_attempt_id=failover.id,
        status="queued",
        requested_by_user_id=requested_by_user_id,
    )
    db.add(row)
    db.flush()
    return row
