from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_tenant_permission
from app.api.v1.hosting_operations import _agent_from_token, _project
from app.db.session import get_db
from app.models import AuditLog, HostingProject, HostingProjectOperation, User
from app.services.hosting_operation_scheduler import (
    claim_next_project_operation,
    renew_project_operation_lease,
)

router = APIRouter(tags=["hosting-project-operations"])
ACTIVE_STATUSES = {"queued", "claimed"}
MAX_LOG_OUTPUT = 256_000


class LogRequest(BaseModel):
    lines: int = Field(default=300, ge=1, le=2000)


class AgentProjectOperationStatus(BaseModel):
    fencing_token: str = Field(min_length=20, max_length=64)
    success: bool
    output: str | None = Field(default=None, max_length=MAX_LOG_OUTPUT)
    message: str | None = Field(default=None, max_length=2000)


class AgentProjectOperationLease(BaseModel):
    fencing_token: str = Field(min_length=20, max_length=64)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _operation_out(row: HostingProjectOperation) -> dict:
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "project_id": str(row.project_id),
        "node_id": str(row.node_id),
        "operation": row.operation,
        "status": row.status,
        "requested_lines": row.requested_lines,
        "output": row.output_text,
        "failure_message": row.failure_message,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "claimed_at": row.claimed_at.isoformat() if row.claimed_at else None,
        "attempt_count": row.attempt_count,
        "lease_expires_at": row.lease_expires_at.isoformat() if row.lease_expires_at else None,
        "lease_heartbeat_at": row.lease_heartbeat_at.isoformat() if row.lease_heartbeat_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


def _audit(db: Session, current: User | None, row: HostingProjectOperation, action: str, metadata: dict | None = None) -> None:
    db.add(AuditLog(
        tenant_id=row.tenant_id,
        actor_user_id=current.id if current else None,
        action=action,
        resource_type="hosting_project_operation",
        resource_id=str(row.id),
        metadata_json=json.dumps(metadata or {}, sort_keys=True),
    ))


def _active(db: Session, project_id: UUID, operation: str | None = None) -> HostingProjectOperation | None:
    query = select(HostingProjectOperation).where(
        HostingProjectOperation.project_id == project_id,
        HostingProjectOperation.status.in_(ACTIVE_STATUSES),
    )
    if operation is not None:
        query = query.where(HostingProjectOperation.operation == operation)
    return db.scalar(query.order_by(HostingProjectOperation.created_at.desc()))


def _queue(
    db: Session,
    *,
    project: HostingProject,
    current: User,
    operation: str,
    requested_lines: int | None = None,
) -> HostingProjectOperation:
    if project.node_id is None:
        raise HTTPException(status_code=409, detail="Project is not assigned to a hosting node")
    if _active(db, project.id, operation) is not None:
        raise HTTPException(status_code=409, detail=f"A {operation} operation is already in progress for this project")
    row = HostingProjectOperation(
        tenant_id=project.tenant_id,
        project_id=project.id,
        node_id=project.node_id,
        operation=operation,
        status="queued",
        requested_lines=requested_lines,
        requested_by_user_id=current.id,
    )
    db.add(row)
    db.flush()
    _audit(db, current, row, f"hosting.project.{operation}.queue", {"requested_lines": requested_lines})
    return row


@router.get("/tenants/{tenant_id}/hosting/projects/{project_id}/operations")
def list_project_operations(
    tenant_id: UUID,
    project_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.read", db, current)
    project = _project(db, tenant_id, project_id)
    rows = db.scalars(
        select(HostingProjectOperation)
        .where(HostingProjectOperation.project_id == project.id)
        .order_by(HostingProjectOperation.created_at.desc())
        .limit(100)
    ).all()
    return {"items": [_operation_out(row) for row in rows]}


@router.get("/tenants/{tenant_id}/hosting/projects/{project_id}/operations/{operation_id}")
def get_project_operation(
    tenant_id: UUID,
    project_id: UUID,
    operation_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.read", db, current)
    _project(db, tenant_id, project_id)
    row = db.scalar(select(HostingProjectOperation).where(
        HostingProjectOperation.id == operation_id,
        HostingProjectOperation.project_id == project_id,
        HostingProjectOperation.tenant_id == tenant_id,
    ))
    if row is None:
        raise HTTPException(status_code=404, detail="Project operation not found")
    return _operation_out(row)


@router.post("/tenants/{tenant_id}/hosting/projects/{project_id}/restart", status_code=202)
def restart_project(
    tenant_id: UUID,
    project_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    project = _project(db, tenant_id, project_id, lock=True)
    if project.status != "running":
        raise HTTPException(status_code=409, detail="Only a running hosted project can be restarted")
    if _active(db, project.id) is not None:
        raise HTTPException(status_code=409, detail="Wait for the current project operation to finish before restarting")
    row = _queue(db, project=project, current=current, operation="restart")
    db.commit()
    db.refresh(row)
    return _operation_out(row)


@router.post("/tenants/{tenant_id}/hosting/projects/{project_id}/logs", status_code=202)
def request_project_logs(
    tenant_id: UUID,
    project_id: UUID,
    payload: LogRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.read", db, current)
    project = _project(db, tenant_id, project_id, lock=True)
    if project.status not in {"running", "deploying", "failed"}:
        raise HTTPException(status_code=409, detail="Logs are available only for a deployed or deploying project")
    row = _queue(db, project=project, current=current, operation="logs", requested_lines=payload.lines)
    db.commit()
    db.refresh(row)
    return _operation_out(row)


@router.post("/hosting/agent/project-operations/claim")
def claim_project_operation(
    x_ithute_hosting_agent: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    agent, node = _agent_from_token(db, x_ithute_hosting_agent)
    agent.last_seen_at = _now()
    row = claim_next_project_operation(db, node_id=node.id, now=_now())
    if row is None:
        db.commit()
        return {"operation": None}
    project = db.get(HostingProject, row.project_id)
    if project is None:
        row.status = "failed"
        row.failure_message = "Project is unavailable"
        row.completed_at = _now()
        db.commit()
        return {"operation": None}
    if row.operation == "retire":
        if project.node_id == node.id:
            row.status = "failed"
            row.failure_message = "Refusing to retire the project's active placement"
            row.completed_at = _now()
            db.commit()
            return {"operation": None}
    elif project.node_id != node.id:
        row.status = "failed"
        row.failure_message = "Project is unavailable on this hosting node"
        row.completed_at = _now()
        db.commit()
        return {"operation": None}
    db.commit()
    return {
        "operation": {
            "id": str(row.id),
            "operation": row.operation,
            "requested_lines": row.requested_lines,
            "attempt": row.attempt_count,
            "fencing_token": row.fencing_token,
            "lease_expires_at": row.lease_expires_at.isoformat() if row.lease_expires_at else None,
            "project": {
                "id": str(project.id),
                "container_port": project.container_port,
                "health_path": project.health_path,
                "status": project.status,
                "discard_local_data": row.operation == "retire",
            },
        }
    }


@router.post("/hosting/agent/project-operations/{operation_id}/heartbeat")
def heartbeat_project_operation(
    operation_id: UUID,
    payload: AgentProjectOperationLease,
    x_ithute_hosting_agent: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    agent, node = _agent_from_token(db, x_ithute_hosting_agent)
    agent.last_seen_at = _now()
    row = db.scalar(
        select(HostingProjectOperation)
        .where(
            HostingProjectOperation.id == operation_id,
            HostingProjectOperation.node_id == node.id,
            HostingProjectOperation.status == "claimed",
        )
        .with_for_update()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Claimed project operation not found for this hosting node")
    if not renew_project_operation_lease(
        db,
        row=row,
        fencing_token=payload.fencing_token,
        now=_now(),
    ):
        raise HTTPException(status_code=409, detail="Operation lease is stale or fencing token is no longer valid")
    db.commit()
    db.refresh(row)
    return {
        "id": str(row.id),
        "attempt": row.attempt_count,
        "lease_expires_at": row.lease_expires_at.isoformat() if row.lease_expires_at else None,
    }


@router.post("/hosting/agent/project-operations/{operation_id}/status")
def report_project_operation(
    operation_id: UUID,
    payload: AgentProjectOperationStatus,
    x_ithute_hosting_agent: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    agent, node = _agent_from_token(db, x_ithute_hosting_agent)
    agent.last_seen_at = _now()
    row = db.scalar(
        select(HostingProjectOperation)
        .where(
            HostingProjectOperation.id == operation_id,
            HostingProjectOperation.node_id == node.id,
            HostingProjectOperation.status == "claimed",
        )
        .with_for_update()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Claimed project operation not found for this hosting node")
    now = _now()
    if (
        not row.fencing_token
        or row.fencing_token != payload.fencing_token
        or row.lease_expires_at is None
        or row.lease_expires_at <= now
    ):
        raise HTTPException(status_code=409, detail="Operation lease is stale or fencing token is no longer valid")
    row.completed_at = now
    if payload.success:
        row.status = "succeeded"
        row.failure_message = None
        row.lease_expires_at = None
        row.lease_heartbeat_at = None
        row.output_text = (payload.output or "")[-MAX_LOG_OUTPUT:] if row.operation == "logs" else None
        _audit(db, None, row, f"hosting.project.{row.operation}.complete", {"output_chars": len(row.output_text or "")})
    else:
        row.status = "failed"
        row.output_text = None
        row.lease_expires_at = None
        row.lease_heartbeat_at = None
        row.failure_message = (payload.message or "Hosting node reported project operation failure").strip()[:2000]
        _audit(db, None, row, f"hosting.project.{row.operation}.failed", {"message": row.failure_message})
    db.commit()
    db.refresh(row)
    return _operation_out(row)
