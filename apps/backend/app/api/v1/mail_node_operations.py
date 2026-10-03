from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_platform_owner
from app.core.config import settings
from app.core.security import hash_token
from app.db.session import get_db
from app.models import AuditLog, MailNode, MailNodeAgent, MailNodeOperation, MailNodeSnapshot, User
from app.models.mail import Mailbox, MailboxStorageType
from app.services.mail_node_commands import queue_mailbox_sync
from app.services.mail_routing_sync import sync_mail_routing
from app.services.security_approvals import SecurityApprovalError, consume_security_approval

router = APIRouter(tags=["mail-node-operations"])


class OperationResult(BaseModel):
    status: str = Field(pattern=r"^(completed|failed)$")
    message: str | None = Field(default=None, max_length=4000)
    result: dict = Field(default_factory=dict)


class FailoverRequest(BaseModel):
    target_node_id: UUID
    snapshot_id: UUID
    approval_id: UUID | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _agent_from_token(db: Session, token: str | None) -> tuple[MailNodeAgent, MailNode]:
    raw = (token or "").strip()
    if not raw or not raw.startswith("ith_mail_"):
        raise HTTPException(status_code=401, detail="Mail node agent credential required")
    agent = db.scalar(select(MailNodeAgent).where(MailNodeAgent.token_hash == hash_token(raw)))
    if agent is None:
        raise HTTPException(status_code=401, detail="Invalid mail node agent credential")
    node = db.get(MailNode, agent.node_id)
    if node is None or node.status == "disabled":
        raise HTTPException(status_code=403, detail="Mail node is disabled")
    return agent, node


def _node_ready(node: MailNode) -> bool:
    fresh = bool(
        node.last_heartbeat_at
        and (_now() - node.last_heartbeat_at).total_seconds() <= settings.mail_node_stale_seconds
    )
    return bool(node.status == "active" and fresh and node.smtp_ready and node.imap_ready and node.tls_ready and node.backup_ready)


def _operation_json(row: MailNodeOperation) -> dict:
    return {
        "id": str(row.id),
        "node_id": str(row.node_id),
        "target_node_id": str(row.target_node_id) if row.target_node_id else None,
        "tenant_id": str(row.tenant_id) if row.tenant_id else None,
        "operation": row.operation,
        "status": row.status,
        "failure_message": row.failure_message,
        "result": json.loads(row.result_json) if row.result_json else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "claimed_at": row.claimed_at.isoformat() if row.claimed_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


@router.post("/platform/mail-nodes/{node_id}/backup", status_code=202)
def create_mail_node_backup(
    node_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    node = db.get(MailNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Mail node not found")
    fresh = bool(
        node.last_heartbeat_at
        and (_now() - node.last_heartbeat_at).total_seconds() <= settings.mail_node_stale_seconds
    )
    if node.status != "active" or not fresh or not node.backup_ready:
        raise HTTPException(status_code=409, detail="Mail node must be active with a fresh heartbeat and reachable off-node backup before backup can be requested")
    if db.get(MailNodeAgent, node.id) is None:
        raise HTTPException(status_code=409, detail="Mail node does not have an agent credential")
    pending = db.scalar(
        select(MailNodeOperation).where(
            MailNodeOperation.node_id == node.id,
            MailNodeOperation.operation == "backup",
            MailNodeOperation.status.in_(("queued", "claimed")),
        )
    )
    if pending is not None:
        raise HTTPException(status_code=409, detail="A mail-node backup is already in progress")

    snapshot = MailNodeSnapshot(
        node_id=node.id,
        tenant_id=node.tenant_id,
        snapshot_key=f"{node.id.hex}-{_now().strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}",
        status="creating",
    )
    db.add(snapshot)
    db.flush()

    operation = MailNodeOperation(
        node_id=node.id,
        tenant_id=node.tenant_id,
        operation="backup",
        payload_json=json.dumps({"snapshot_id": str(snapshot.id), "snapshot_key": snapshot.snapshot_key}),
        requested_by_user_id=current.id,
    )
    db.add(operation)
    db.add(AuditLog(
        actor_user_id=current.id,
        tenant_id=node.tenant_id,
        action="mail_node.backup.queue",
        resource_type="mail_node",
        resource_id=str(node.id),
        metadata_json=json.dumps({"snapshot_id": str(snapshot.id), "snapshot_key": snapshot.snapshot_key}),
    ))
    db.commit()
    db.refresh(operation)
    return {"operation": _operation_json(operation), "snapshot_id": str(snapshot.id), "snapshot_key": snapshot.snapshot_key}


@router.get("/platform/mail-nodes/{node_id}/snapshots")
def list_mail_node_snapshots(
    node_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    if db.get(MailNode, node_id) is None:
        raise HTTPException(status_code=404, detail="Mail node not found")
    rows = db.scalars(
        select(MailNodeSnapshot)
        .where(MailNodeSnapshot.node_id == node_id)
        .order_by(MailNodeSnapshot.created_at.desc())
        .limit(100)
    ).all()
    return {
        "items": [
            {
                "id": str(row.id),
                "node_id": str(row.node_id),
                "snapshot_key": row.snapshot_key,
                "remote_uri": row.remote_uri,
                "size_bytes": row.size_bytes,
                "checksum_sha256": row.checksum_sha256,
                "status": row.status,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            }
            for row in rows
        ]
    }


@router.post("/platform/mail-nodes/{source_node_id}/failover", status_code=202)
def queue_mail_node_failover(
    source_node_id: UUID,
    payload: FailoverRequest,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    source = db.get(MailNode, source_node_id)
    target = db.get(MailNode, payload.target_node_id)
    snapshot = db.get(MailNodeSnapshot, payload.snapshot_id)
    if source is None or target is None:
        raise HTTPException(status_code=404, detail="Source or target mail node not found")
    if source.id == target.id:
        raise HTTPException(status_code=422, detail="Failover target must be a different mail node")
    if snapshot is None or snapshot.node_id != source.id or snapshot.status != "ready":
        raise HTTPException(status_code=409, detail="Failover requires a ready snapshot from the source node")
    if not _node_ready(target):
        raise HTTPException(status_code=409, detail="Failover target must be active with SMTP, IMAP, TLS and off-node backup ready")
    if target.tenant_id is not None and target.tenant_id != source.tenant_id:
        raise HTTPException(status_code=409, detail="Failover target belongs to a different tenant")
    if db.get(MailNodeAgent, target.id) is None:
        raise HTTPException(status_code=409, detail="Failover target does not have an agent credential")

    if settings.security_dual_control_enabled:
        if payload.approval_id is None:
            raise HTTPException(status_code=409, detail="Approved two-person security change is required for failover")
        try:
            consume_security_approval(
                db,
                approval_id=payload.approval_id,
                action="mail_node.failover",
                resource_type="mail_node",
                resource_id=str(source.id),
                payload_match={
                    "target_node_id": str(target.id),
                    "snapshot_id": str(snapshot.id),
                },
            )
        except SecurityApprovalError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    operation = MailNodeOperation(
        node_id=target.id,
        target_node_id=target.id,
        tenant_id=source.tenant_id,
        operation="restore_failover",
        payload_json=json.dumps({
            "source_node_id": str(source.id),
            "target_node_id": str(target.id),
            "snapshot_id": str(snapshot.id),
            "snapshot_key": snapshot.snapshot_key,
            "remote_uri": snapshot.remote_uri,
            "checksum_sha256": snapshot.checksum_sha256,
        }),
        requested_by_user_id=current.id,
    )
    db.add(operation)
    source.status = "maintenance"
    db.add(AuditLog(
        actor_user_id=current.id,
        tenant_id=source.tenant_id,
        action="mail_node.failover.queue",
        resource_type="mail_node",
        resource_id=str(source.id),
        metadata_json=json.dumps({"target_node_id": str(target.id), "snapshot_id": str(snapshot.id), "approval_id": str(payload.approval_id) if payload.approval_id else None}),
    ))
    db.commit()
    db.refresh(operation)
    return {"operation": _operation_json(operation)}


@router.get("/platform/mail-node-operations")
def list_mail_node_operations(
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    rows = db.scalars(select(MailNodeOperation).order_by(MailNodeOperation.created_at.desc()).limit(200)).all()
    return {"items": [_operation_json(row) for row in rows]}


@router.post("/mail-node-agent/operations/claim")
def claim_mail_node_operation(
    x_ithute_mail_agent: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    agent, node = _agent_from_token(db, x_ithute_mail_agent)
    agent.last_seen_at = _now()
    node.last_heartbeat_at = agent.last_seen_at

    row = db.scalar(
        select(MailNodeOperation)
        .where(MailNodeOperation.node_id == node.id, MailNodeOperation.status == "queued")
        .order_by(MailNodeOperation.created_at.asc())
        .with_for_update(skip_locked=True)
    )
    if row is None:
        db.commit()
        return {"operation": None}
    row.status = "claimed"
    row.claimed_at = _now()
    payload = json.loads(row.payload_json or "{}")
    db.commit()
    return {
        "operation": {
            "id": str(row.id),
            "operation": row.operation,
            "payload": payload,
        }
    }


def _queue_snapshot_retention(db: Session, agent: MailNodeAgent, node: MailNode) -> None:
    keep = max(1, min(int(node.backup_retention_count or 7), 100))
    ready = db.scalars(
        select(MailNodeSnapshot)
        .where(MailNodeSnapshot.node_id == node.id, MailNodeSnapshot.status == "ready")
        .order_by(MailNodeSnapshot.created_at.desc())
    ).all()
    for snapshot in ready[keep:]:
        if not snapshot.remote_uri:
            continue
        pending = db.scalar(
            select(MailNodeOperation).where(
                MailNodeOperation.node_id == node.id,
                MailNodeOperation.operation == "delete_snapshot",
                MailNodeOperation.status.in_(("queued", "claimed")),
                MailNodeOperation.payload_json.contains(str(snapshot.id)),
            )
        )
        if pending is not None:
            continue
        snapshot.status = "deleting"
        db.add(MailNodeOperation(
            node_id=node.id,
            tenant_id=node.tenant_id,
            operation="delete_snapshot",
            payload_json=json.dumps({
                "snapshot_id": str(snapshot.id),
                "snapshot_key": snapshot.snapshot_key,
                "remote_uri": snapshot.remote_uri,
            }),
            requested_by_user_id=agent.rotated_by_user_id,
        ))


@router.post("/mail-node-agent/operations/{operation_id}/status")
def complete_mail_node_operation(
    operation_id: UUID,
    payload: OperationResult,
    x_ithute_mail_agent: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    agent, node = _agent_from_token(db, x_ithute_mail_agent)
    agent.last_seen_at = _now()
    node.last_heartbeat_at = agent.last_seen_at

    row = db.scalar(
        select(MailNodeOperation).where(
            MailNodeOperation.id == operation_id,
            MailNodeOperation.node_id == node.id,
            MailNodeOperation.status == "claimed",
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Claimed mail node operation not found")

    row.status = payload.status
    row.completed_at = _now()
    row.failure_message = payload.message if payload.status == "failed" else None
    row.result_json = json.dumps(payload.result or {}, sort_keys=True)

    operation_payload = json.loads(row.payload_json or "{}")
    if row.operation == "backup":
        snapshot_id = UUID(str(operation_payload["snapshot_id"]))
        snapshot = db.get(MailNodeSnapshot, snapshot_id)
        if snapshot:
            if payload.status == "completed":
                snapshot.status = "ready"
                snapshot.remote_uri = str(payload.result.get("remote_uri") or "") or None
                snapshot.size_bytes = int(payload.result.get("size_bytes") or 0) or None
                snapshot.checksum_sha256 = str(payload.result.get("checksum_sha256") or "") or None
                snapshot.completed_at = _now()
            else:
                snapshot.status = "failed"
        if payload.status == "completed":
            _queue_snapshot_retention(db, agent, node)

    if row.operation == "delete_snapshot":
        snapshot_id = UUID(str(operation_payload["snapshot_id"]))
        snapshot = db.get(MailNodeSnapshot, snapshot_id)
        if snapshot:
            snapshot.status = "deleted" if payload.status == "completed" else "ready"

    if row.operation == "restore_failover" and payload.status == "completed":
        source_node_id = UUID(str(operation_payload["source_node_id"]))
        target_node_id = UUID(str(operation_payload["target_node_id"]))
        target = db.get(MailNode, target_node_id)
        if target is None or not _node_ready(target):
            raise HTTPException(status_code=409, detail="Failover target lost readiness before activation")

        mailboxes = db.scalars(
            select(Mailbox).where(
                Mailbox.mail_node_id == source_node_id,
                Mailbox.storage_type == MailboxStorageType.external,
            )
        ).all()
        for mailbox in mailboxes:
            if target.tenant_id is not None and target.tenant_id != mailbox.tenant_id:
                raise HTTPException(status_code=409, detail="Failover target tenant scope does not match mailbox")
            mailbox.mail_node_id = target.id
            queue_mailbox_sync(db, mailbox)

        db.flush()
        sync_mail_routing(db)
        db.add(AuditLog(
            actor_user_id=None,
            tenant_id=row.tenant_id,
            action="mail_node.failover.complete",
            resource_type="mail_node",
            resource_id=str(source_node_id),
            metadata_json=json.dumps({"target_node_id": str(target_node_id), "mailboxes_moved": len(mailboxes)}),
        ))

    db.commit()
    return {"ok": True, "operation": _operation_json(row)}
