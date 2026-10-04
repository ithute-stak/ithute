from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EdgeRouteDeployment, HostingDatabase, HostingDeployment, HostingProject, HostingProvisioningWorkflow
from app.services.hosting_edge_handoff import HostingOriginError, reconcile_project_edge

ACTIVE_WORKFLOW_STATUSES = {"queued", "provisioning", "building", "deploying", "edge_pending"}


def run_hosting_provisioning_reconcile(db: Session, limit: int = 100) -> dict:
    rows = db.scalars(
        select(HostingProvisioningWorkflow)
        .where(HostingProvisioningWorkflow.status.in_(ACTIVE_WORKFLOW_STATUSES))
        .order_by(HostingProvisioningWorkflow.updated_at.asc())
        .limit(max(1, min(limit, 500)))
    ).all()
    checked = completed = pending = failed = 0

    for workflow in rows:
        checked += 1
        project = db.get(HostingProject, workflow.project_id)
        if project is None:
            workflow.status = "failed"
            workflow.failure_message = "Hosted project no longer exists"
            failed += 1
            continue

        deployment = db.scalar(
            select(HostingDeployment)
            .where(HostingDeployment.project_id == project.id)
            .order_by(HostingDeployment.created_at.desc())
            .limit(1)
        )
        database = db.get(HostingDatabase, workflow.database_id) if workflow.database_id else None

        if database is not None and database.status == "failed":
            workflow.status = "failed"
            workflow.failure_message = database.failure_message or "Managed database provisioning failed"
            failed += 1
            continue
        if deployment is not None and deployment.status == "failed":
            workflow.status = "failed"
            workflow.failure_message = deployment.failure_message or "Application deployment failed"
            failed += 1
            continue

        if deployment is None or deployment.status != "healthy":
            if deployment is not None and deployment.status in {"queued", "claimed", "running"}:
                workflow.status = "deploying"
            pending += 1
            continue

        database_ready = database is None or database.status in {"ready", "suspended"}
        if not database_ready:
            workflow.status = "provisioning"
            pending += 1
            continue

        if not project.hostname:
            workflow.status = "completed"
            workflow.failure_message = None
            workflow.completed_at = workflow.completed_at or datetime.now(timezone.utc)
            completed += 1
            continue

        if not deployment.origin_url:
            workflow.status = "edge_pending"
            workflow.failure_message = "Hosting node has not reported a trusted private origin yet"
            pending += 1
            continue

        try:
            edge = reconcile_project_edge(db, project, deployment.origin_url)
        except HostingOriginError as exc:
            workflow.status = "edge_pending"
            workflow.failure_message = str(exc)
            pending += 1
            continue

        if edge.get("status") == "active":
            workflow.status = "completed"
            workflow.failure_message = None
            workflow.completed_at = workflow.completed_at or datetime.now(timezone.utc)
            completed += 1
        elif edge.get("status") == "error":
            workflow.status = "edge_pending"
            workflow.failure_message = str(edge.get("error") or "Edge activation failed")
            pending += 1
        else:
            workflow.status = "edge_pending"
            workflow.failure_message = str(edge.get("error") or "") or None
            pending += 1

    db.commit()
    return {"checked": checked, "completed": completed, "pending": pending, "failed": failed}
