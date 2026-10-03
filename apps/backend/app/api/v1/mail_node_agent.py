from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_platform_owner
from app.core.security import hash_token
from app.db.session import get_db
from app.models import AuditLog, MailNode, MailNodeAgent, MailNodeCommand, MailNodeOperation, MailNodeSnapshot, User

router = APIRouter(tags=["mail-node-agent"])


class AgentHeartbeat(BaseModel):
    version: str = Field(min_length=1, max_length=80)
    total_storage_bytes: int | None = Field(default=None, ge=0)
    used_storage_bytes: int | None = Field(default=None, ge=0)
    capabilities: list[str] = Field(default_factory=lambda: ["mail", "storage"])
    smtp_ready: bool = False
    imap_ready: bool = False
    tls_ready: bool = False
    tls_not_after: datetime | None = None
    readiness_error: str | None = Field(default=None, max_length=2000)
    backup_ready: bool = False
    backup_error: str | None = Field(default=None, max_length=2000)


class AgentCommandStatus(BaseModel):
    status: str = Field(pattern=r"^(completed|failed)$")
    message: str | None = Field(default=None, max_length=4000)


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


@router.post("/platform/mail-nodes/{node_id}/agent-token")
def rotate_mail_node_agent_token(
    node_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    node = db.get(MailNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Mail node not found")

    raw = "ith_mail_" + secrets.token_urlsafe(36)
    now = _now()
    agent = db.get(MailNodeAgent, node_id)
    if agent is None:
        agent = MailNodeAgent(
            node_id=node.id,
            token_hash=hash_token(raw),
            token_hint=raw[:18],
            rotated_at=now,
            rotated_by_user_id=current.id,
        )
        db.add(agent)
    else:
        agent.token_hash = hash_token(raw)
        agent.token_hint = raw[:18]
        agent.agent_version = None
        agent.last_seen_at = None
        agent.rotated_at = now
        agent.rotated_by_user_id = current.id

    db.add(AuditLog(
        actor_user_id=current.id,
        action="mail_node.agent.rotate",
        resource_type="mail_node",
        resource_id=str(node.id),
        metadata_json=json.dumps({"node": node.name}),
    ))
    db.commit()
    return {
        "node_id": str(node.id),
        "token": raw,
        "token_hint": raw[:18],
        "warning": "This credential is shown once. Store it only on the target Ithute Mail Node Agent.",
    }


@router.get("/platform/mail-nodes/{node_id}/agent")
def mail_node_agent_status(
    node_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    node = db.get(MailNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Mail node not found")
    agent = db.get(MailNodeAgent, node_id)
    return {
        "node_id": str(node.id),
        "configured": agent is not None,
        "token_hint": agent.token_hint if agent else None,
        "agent_version": agent.agent_version if agent else None,
        "last_seen_at": agent.last_seen_at.isoformat() if agent and agent.last_seen_at else None,
        "rotated_at": agent.rotated_at.isoformat() if agent else None,
    }


def _queue_scheduled_backup_if_due(db: Session, agent: MailNodeAgent, node: MailNode) -> None:
    if node.status != "active" or not node.backup_ready:
        return
    pending = db.scalar(
        select(MailNodeOperation).where(
            MailNodeOperation.node_id == node.id,
            MailNodeOperation.operation == "backup",
            MailNodeOperation.status.in_(("queued", "claimed")),
        )
    )
    if pending is not None:
        return
    latest = db.scalar(
        select(MailNodeSnapshot)
        .where(
            MailNodeSnapshot.node_id == node.id,
            MailNodeSnapshot.status.in_(("ready", "creating")),
        )
        .order_by(MailNodeSnapshot.created_at.desc())
    )
    now = _now()
    interval = max(1, min(int(node.backup_interval_hours or 24), 168))
    if latest is not None and latest.created_at and now - latest.created_at < timedelta(hours=interval):
        return

    snapshot = MailNodeSnapshot(
        node_id=node.id,
        tenant_id=node.tenant_id,
        snapshot_key=f"{node.id.hex}-{now.strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}",
        status="creating",
    )
    db.add(snapshot)
    db.flush()
    db.add(MailNodeOperation(
        node_id=node.id,
        tenant_id=node.tenant_id,
        operation="backup",
        payload_json=json.dumps({"snapshot_id": str(snapshot.id), "snapshot_key": snapshot.snapshot_key}),
        requested_by_user_id=agent.rotated_by_user_id,
    ))


@router.post("/mail-node-agent/heartbeat")
def mail_node_agent_heartbeat(
    payload: AgentHeartbeat,
    x_ithute_mail_agent: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    agent, node = _agent_from_token(db, x_ithute_mail_agent)
    agent.agent_version = payload.version.strip()
    agent.last_seen_at = _now()
    node.agent_version = payload.version.strip()
    node.last_heartbeat_at = agent.last_seen_at
    if payload.total_storage_bytes is not None:
        node.total_storage_bytes = payload.total_storage_bytes
    if payload.used_storage_bytes is not None:
        node.used_storage_bytes = payload.used_storage_bytes
    node.capabilities_json = json.dumps(sorted({x.strip().lower() for x in payload.capabilities if x.strip()}))
    node.smtp_ready = payload.smtp_ready
    node.imap_ready = payload.imap_ready
    node.tls_ready = payload.tls_ready
    node.tls_not_after = payload.tls_not_after
    node.readiness_error = payload.readiness_error
    node.backup_ready = payload.backup_ready
    node.backup_error = payload.backup_error
    if node.status == "provisioning" and payload.smtp_ready and payload.imap_ready and payload.tls_ready and payload.backup_ready:
        node.status = "active"
    _queue_scheduled_backup_if_due(db, agent, node)
    db.commit()
    return {"ok": True, "node_id": str(node.id), "status": node.status}


@router.post("/mail-node-agent/commands/claim")
def claim_mail_node_command(
    x_ithute_mail_agent: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    agent, node = _agent_from_token(db, x_ithute_mail_agent)
    agent.last_seen_at = _now()
    node.last_heartbeat_at = agent.last_seen_at
    if node.status != "active":
        db.commit()
        return {"command": None}

    command = db.scalar(
        select(MailNodeCommand)
        .where(MailNodeCommand.node_id == node.id, MailNodeCommand.status == "queued")
        .order_by(MailNodeCommand.created_at.asc())
        .with_for_update(skip_locked=True)
    )
    if command is None:
        db.commit()
        return {"command": None}

    command.status = "claimed"
    command.claimed_at = _now()
    payload = json.loads(command.payload_json)
    db.commit()
    return {
        "command": {
            "id": str(command.id),
            "operation": command.operation,
            "mailbox_id": str(command.mailbox_id),
            "payload": payload,
        }
    }


@router.post("/mail-node-agent/commands/{command_id}/status")
def complete_mail_node_command(
    command_id: UUID,
    payload: AgentCommandStatus,
    x_ithute_mail_agent: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    agent, node = _agent_from_token(db, x_ithute_mail_agent)
    agent.last_seen_at = _now()
    node.last_heartbeat_at = agent.last_seen_at

    command = db.scalar(
        select(MailNodeCommand).where(
            MailNodeCommand.id == command_id,
            MailNodeCommand.node_id == node.id,
            MailNodeCommand.status == "claimed",
        )
    )
    if command is None:
        raise HTTPException(status_code=404, detail="Claimed mail node command not found")
    command.status = payload.status
    command.failure_message = payload.message if payload.status == "failed" else None
    command.completed_at = _now()
    db.commit()
    return {"ok": True, "command_id": str(command.id), "status": command.status}
