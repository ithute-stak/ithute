from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog


def log_finance_action(
    db: Session,
    *,
    action: str,
    resource_type: str,
    resource_id: UUID | str | None,
    actor_user_id: UUID | None = None,
    metadata: dict | None = None,
) -> AuditLog:
    row = AuditLog(
        tenant_id=None,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        metadata_json=json.dumps(metadata or {}, default=str, separators=(",", ":")),
    )
    db.add(row)
    return row


def finance_activity(db: Session, *, resource_type: str, resource_id: UUID | str) -> list[dict]:
    rows = db.scalars(
        select(AuditLog)
        .where(
            AuditLog.resource_type == resource_type,
            AuditLog.resource_id == str(resource_id),
            AuditLog.action.like("finance.%"),
        )
        .order_by(AuditLog.created_at.desc())
    ).all()
    output = []
    for row in rows:
        try:
            metadata = json.loads(row.metadata_json or "{}")
        except Exception:
            metadata = {}
        output.append(
            {
                "id": str(row.id),
                "action": row.action,
                "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
                "metadata": metadata,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return output


def finance_action_exists(db: Session, *, action: str, resource_type: str, resource_id: UUID | str) -> bool:
    return db.scalar(
        select(AuditLog.id).where(
            AuditLog.action == action,
            AuditLog.resource_type == resource_type,
            AuditLog.resource_id == str(resource_id),
        ).limit(1)
    ) is not None
