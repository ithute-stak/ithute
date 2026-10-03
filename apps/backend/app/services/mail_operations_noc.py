from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Domain, MailNode, MailNodeOperation, MailNodeSnapshot, Mailbox
from app.models.domains import DomainStatus
from app.services.mail_ops import MailOpsError, queue_summary, tls_status
from app.services.operations_status import OperationsStatusError, operations_status


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fresh(node: MailNode) -> bool:
    return bool(
        node.last_heartbeat_at
        and (_now() - node.last_heartbeat_at).total_seconds() <= settings.mail_node_stale_seconds
    )


def _node_ready(node: MailNode) -> bool:
    return bool(
        node.status == "active"
        and _fresh(node)
        and node.smtp_ready
        and node.imap_ready
        and node.tls_ready
        and node.backup_ready
    )


def _safe_runtime() -> dict:
    try:
        return operations_status()
    except OperationsStatusError as exc:
        return {"status": "unknown", "services": {}, "mail_queue_total": None, "error": str(exc)}


def _safe_queue() -> dict:
    try:
        return queue_summary()
    except MailOpsError as exc:
        return {"error": str(exc)}


def _safe_tls() -> dict:
    try:
        return tls_status()
    except MailOpsError as exc:
        return {"error": str(exc)}


def mail_operations_noc(db: Session) -> dict:
    nodes = db.scalars(select(MailNode).order_by(MailNode.name.asc())).all()
    recent_operations = db.scalars(
        select(MailNodeOperation).order_by(MailNodeOperation.created_at.desc()).limit(20)
    ).all()

    node_rows = []
    for node in nodes:
        latest_snapshot = db.scalar(
            select(MailNodeSnapshot)
            .where(MailNodeSnapshot.node_id == node.id, MailNodeSnapshot.status == "ready")
            .order_by(MailNodeSnapshot.completed_at.desc(), MailNodeSnapshot.created_at.desc())
            .limit(1)
        )
        total = int(node.total_storage_bytes or 0)
        used = int(node.used_storage_bytes or 0)
        storage_percent = round((used / total) * 100, 1) if total > 0 else None
        node_rows.append(
            {
                "id": str(node.id),
                "name": node.name,
                "hostname": node.hostname,
                "region": node.region,
                "status": node.status,
                "ready": _node_ready(node),
                "heartbeat_fresh": _fresh(node),
                "last_heartbeat_at": node.last_heartbeat_at.isoformat() if node.last_heartbeat_at else None,
                "smtp_ready": node.smtp_ready,
                "imap_ready": node.imap_ready,
                "tls_ready": node.tls_ready,
                "backup_ready": node.backup_ready,
                "readiness_error": node.readiness_error,
                "backup_error": node.backup_error,
                "total_storage_bytes": total or None,
                "used_storage_bytes": used or None,
                "storage_percent": storage_percent,
                "latest_backup_at": (
                    latest_snapshot.completed_at.isoformat()
                    if latest_snapshot and latest_snapshot.completed_at
                    else None
                ),
                "latest_backup_key": latest_snapshot.snapshot_key if latest_snapshot else None,
            }
        )

    active_nodes = [row for row in node_rows if row["status"] == "active"]
    ready_nodes = [row for row in node_rows if row["ready"]]
    failed_ops = [row for row in recent_operations if row.status == "failed"]

    mailbox_count = db.scalar(select(func.count(Mailbox.id))) or 0
    external_mailboxes = db.scalar(select(func.count(Mailbox.id)).where(Mailbox.mail_node_id.is_not(None))) or 0
    managed_domains = db.scalar(
        select(func.count(Domain.id)).where(Domain.status != DomainStatus.archived, Domain.mail_enabled.is_(True))
    ) or 0

    runtime = _safe_runtime()
    queue = _safe_queue()
    tls = _safe_tls()

    overall = "healthy"
    if active_nodes and len(ready_nodes) != len(active_nodes):
        overall = "attention"
    if runtime.get("status") == "degraded" or failed_ops:
        overall = "attention"
    if active_nodes and not ready_nodes:
        overall = "critical"

    return {
        "overall_status": overall,
        "checked_at": _now().isoformat(),
        "summary": {
            "nodes_total": len(node_rows),
            "nodes_active": len(active_nodes),
            "nodes_ready": len(ready_nodes),
            "mailboxes_total": int(mailbox_count),
            "mailboxes_external": int(external_mailboxes),
            "mail_domains": int(managed_domains),
            "failed_recent_operations": len(failed_ops),
        },
        "runtime": runtime,
        "queue": queue,
        "tls": tls,
        "nodes": node_rows,
        "recent_operations": [
            {
                "id": str(row.id),
                "node_id": str(row.node_id),
                "operation": row.operation,
                "status": row.status,
                "failure_message": row.failure_message,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            }
            for row in recent_operations
        ],
    }
