from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog
from app.services.finance_audit import log_finance_action

_REMINDER_ENABLED = "finance.client.reminders.enabled"
_REMINDER_DISABLED = "finance.client.reminders.disabled"


def client_reminders_enabled(db: Session, client_id: UUID | None) -> bool:
    if client_id is None:
        return True
    row = db.scalar(
        select(AuditLog)
        .where(
            AuditLog.resource_type == "finance_client",
            AuditLog.resource_id == str(client_id),
            AuditLog.action.in_([_REMINDER_ENABLED, _REMINDER_DISABLED]),
        )
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    return row is None or row.action != _REMINDER_DISABLED


def set_client_reminders(db: Session, client_id: UUID, enabled: bool, *, actor_user_id: UUID | None = None) -> None:
    log_finance_action(
        db,
        action=_REMINDER_ENABLED if enabled else _REMINDER_DISABLED,
        resource_type="finance_client",
        resource_id=client_id,
        actor_user_id=actor_user_id,
        metadata={"reminders_enabled": enabled},
    )
