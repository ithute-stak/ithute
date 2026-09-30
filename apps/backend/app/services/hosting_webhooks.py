from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import HostingBuild, HostingProject, HostingSource, HostingSourceWebhook

ACTIVE_BUILD_STATUSES = ("queued", "claimed", "building")


def queue_webhook_build(
    db: Session,
    *,
    webhook: HostingSourceWebhook,
    source: HostingSource,
    project: HostingProject,
    commit: str | None = None,
) -> HostingBuild | None:
    """Queue a webhook build or remember one pending rebuild.

    A source can be actively materialized by only one builder at a time. If a
    push arrives during a build, remember that another rebuild is due instead
    of creating a job that a second builder could claim while the source is in
    `building` state.
    """
    active = db.scalar(
        select(HostingBuild.id).where(
            HostingBuild.project_id == project.id,
            HostingBuild.status.in_(ACTIVE_BUILD_STATUSES),
        )
    )
    if active is not None or source.status != "ready":
        webhook.pending_rebuild = True
        webhook.pending_commit = commit
        return None

    row = HostingBuild(
        tenant_id=source.tenant_id,
        project_id=project.id,
        source_id=source.id,
        runtime=project.runtime,
        status="queued",
        requested_by_user_id=webhook.created_by_user_id,
    )
    db.add(row)
    webhook.pending_rebuild = False
    webhook.pending_commit = None
    return row


def queue_pending_webhook_rebuild(db: Session, source_id) -> HostingBuild | None:
    webhook = db.scalar(
        select(HostingSourceWebhook)
        .where(
            HostingSourceWebhook.source_id == source_id,
            HostingSourceWebhook.status == "active",
            HostingSourceWebhook.pending_rebuild.is_(True),
        )
        .with_for_update()
    )
    if webhook is None:
        return None
    source = db.get(HostingSource, source_id)
    project = db.get(HostingProject, webhook.project_id)
    if source is None or project is None:
        return None
    return queue_webhook_build(
        db,
        webhook=webhook,
        source=source,
        project=project,
        commit=webhook.pending_commit,
    )
