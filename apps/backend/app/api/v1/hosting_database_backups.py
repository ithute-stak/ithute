from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_tenant_permission
from app.api.v1.hosting_operations import _agent_from_token
from app.db.session import get_db
from app.models import AuditLog, HostingDatabase, HostingDatabaseBackup, User

router = APIRouter(tags=["hosting-database-backups"])
ACTIVE_STATUSES = {"queued", "claimed"}


class AgentBackupStatus(BaseModel):
    success: bool
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    size_bytes: int | None = Field(default=None, ge=1)
    message: str | None = Field(default=None, max_length=2000)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _database(db: Session, tenant_id: UUID, database_id: UUID, *, lock: bool = False) -> HostingDatabase:
    query = select(HostingDatabase).where(HostingDatabase.id == database_id, HostingDatabase.tenant_id == tenant_id)
    if lock:
        query = query.with_for_update()
    row = db.scalar(query)
    if row is None:
        raise HTTPException(status_code=404, detail="Hosting database not found")
    return row


def _out(row: HostingDatabaseBackup) -> dict:
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "database_id": str(row.database_id),
        "node_id": str(row.node_id),
        "source_backup_id": str(row.source_backup_id) if row.source_backup_id else None,
        "operation": row.operation,
        "status": row.status,
        "storage_key": row.storage_key,
        "sha256": row.sha256,
        "size_bytes": row.size_bytes,
        "failure_message": row.failure_message,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "claimed_at": row.claimed_at.isoformat() if row.claimed_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


def _audit(db: Session, current: User | None, row: HostingDatabaseBackup, action: str, metadata: dict | None = None) -> None:
    db.add(AuditLog(
        tenant_id=row.tenant_id,
        actor_user_id=current.id if current else None,
        action=action,
        resource_type="hosting_database_backup",
        resource_id=str(row.id),
        metadata_json=json.dumps(metadata or {}, sort_keys=True),
    ))


def _has_active(db: Session, database_id: UUID) -> bool:
    return db.scalar(select(HostingDatabaseBackup.id).where(
        HostingDatabaseBackup.database_id == database_id,
        HostingDatabaseBackup.status.in_(ACTIVE_STATUSES),
    )) is not None


@router.get("/tenants/{tenant_id}/hosting/databases/{database_id}/backups")
def list_database_backups(
    tenant_id: UUID,
    database_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.read", db, current)
    _database(db, tenant_id, database_id)
    rows = db.scalars(
        select(HostingDatabaseBackup)
        .where(HostingDatabaseBackup.database_id == database_id)
        .order_by(HostingDatabaseBackup.created_at.desc())
        .limit(100)
    ).all()
    return {"items": [_out(row) for row in rows]}


@router.post("/tenants/{tenant_id}/hosting/databases/{database_id}/backups", status_code=202)
def queue_database_backup(
    tenant_id: UUID,
    database_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    database = _database(db, tenant_id, database_id, lock=True)
    if database.node_id is None:
        raise HTTPException(status_code=409, detail="Database is not assigned to a hosting node")
    if database.status not in {"ready", "suspended"}:
        raise HTTPException(status_code=409, detail="Database must be ready or suspended before backup")
    if _has_active(db, database.id):
        raise HTTPException(status_code=409, detail="A database backup or restore operation is already in progress")
    backup_id = uuid.uuid4()
    extension = "pgdump" if database.engine == "postgresql" else "sql"
    row = HostingDatabaseBackup(
        id=backup_id,
        tenant_id=tenant_id,
        database_id=database.id,
        node_id=database.node_id,
        source_backup_id=None,
        operation="backup",
        status="queued",
        storage_key=f"{tenant_id}/{database.id}/{backup_id}.{extension}",
        requested_by_user_id=current.id,
    )
    db.add(row)
    db.flush()
    _audit(db, current, row, "hosting.database.backup.queue", {"engine": database.engine})
    db.commit()
    db.refresh(row)
    return _out(row)


@router.post("/tenants/{tenant_id}/hosting/databases/{database_id}/backups/{backup_id}/restore", status_code=202)
def queue_database_restore(
    tenant_id: UUID,
    database_id: UUID,
    backup_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    database = _database(db, tenant_id, database_id, lock=True)
    if database.node_id is None:
        raise HTTPException(status_code=409, detail="Database is not assigned to a hosting node")
    if database.status != "suspended":
        raise HTTPException(status_code=409, detail="Suspend the database before restore so application writes cannot race the restore")
    if _has_active(db, database.id):
        raise HTTPException(status_code=409, detail="A database backup or restore operation is already in progress")
    source = db.scalar(select(HostingDatabaseBackup).where(
        HostingDatabaseBackup.id == backup_id,
        HostingDatabaseBackup.database_id == database.id,
        HostingDatabaseBackup.operation == "backup",
        HostingDatabaseBackup.status == "succeeded",
    ))
    if source is None or not source.sha256 or not source.size_bytes:
        raise HTTPException(status_code=409, detail="Restore target must be a completed verified backup from this database")
    restore_id = uuid.uuid4()
    row = HostingDatabaseBackup(
        id=restore_id,
        tenant_id=tenant_id,
        database_id=database.id,
        node_id=database.node_id,
        source_backup_id=source.id,
        operation="restore",
        status="queued",
        storage_key=source.storage_key,
        sha256=source.sha256,
        size_bytes=source.size_bytes,
        requested_by_user_id=current.id,
    )
    db.add(row)
    db.flush()
    _audit(db, current, row, "hosting.database.restore.queue", {"source_backup_id": str(source.id), "sha256": source.sha256})
    db.commit()
    db.refresh(row)
    return _out(row)


@router.post("/hosting/agent/database-backups/claim")
def claim_database_backup(
    x_ithute_hosting_agent: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    agent, node = _agent_from_token(db, x_ithute_hosting_agent)
    agent.last_seen_at = _now()
    row = db.scalar(
        select(HostingDatabaseBackup)
        .where(HostingDatabaseBackup.node_id == node.id, HostingDatabaseBackup.status == "queued")
        .order_by(HostingDatabaseBackup.created_at.asc())
        .with_for_update(skip_locked=True)
    )
    if row is None:
        db.commit()
        return {"backup": None}
    database = db.get(HostingDatabase, row.database_id)
    if database is None or database.node_id != node.id:
        row.status = "failed"
        row.failure_message = "Database is unavailable on this hosting node"
        row.completed_at = _now()
        db.commit()
        return {"backup": None}
    if row.operation == "restore" and database.status != "suspended":
        row.status = "failed"
        row.failure_message = "Database must remain suspended for restore"
        row.completed_at = _now()
        db.commit()
        return {"backup": None}
    row.status = "claimed"
    row.claimed_at = _now()
    db.commit()
    return {
        "backup": {
            "id": str(row.id),
            "operation": row.operation,
            "storage_key": row.storage_key,
            "sha256": row.sha256,
            "size_bytes": row.size_bytes,
            "database": {
                "id": str(database.id),
                "engine": database.engine,
                "database_name": database.database_name,
                "status": database.status,
            },
        }
    }


@router.post("/hosting/agent/database-backups/{backup_id}/status")
def report_database_backup(
    backup_id: UUID,
    payload: AgentBackupStatus,
    x_ithute_hosting_agent: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    agent, node = _agent_from_token(db, x_ithute_hosting_agent)
    agent.last_seen_at = _now()
    row = db.scalar(select(HostingDatabaseBackup).where(
        HostingDatabaseBackup.id == backup_id,
        HostingDatabaseBackup.node_id == node.id,
        HostingDatabaseBackup.status == "claimed",
    ).with_for_update())
    if row is None:
        raise HTTPException(status_code=404, detail="Claimed database backup operation not found for this node")
    row.completed_at = _now()
    if payload.success:
        if row.operation == "backup":
            if payload.sha256 is None or payload.size_bytes is None:
                raise HTTPException(status_code=422, detail="Successful backup must report SHA-256 and size")
            row.sha256 = payload.sha256
            row.size_bytes = payload.size_bytes
        row.status = "succeeded"
        row.failure_message = None
        _audit(db, None, row, f"hosting.database.{row.operation}.complete", {"sha256": row.sha256, "size_bytes": row.size_bytes})
    else:
        row.status = "failed"
        row.failure_message = (payload.message or "Hosting node reported database backup operation failure").strip()[:2000]
        _audit(db, None, row, f"hosting.database.{row.operation}.failed", {"message": row.failure_message})
    db.commit()
    db.refresh(row)
    return _out(row)
