from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import SecurityApprovalRequest


class SecurityApprovalError(RuntimeError):
    pass


def now() -> datetime:
    return datetime.now(timezone.utc)


def consume_security_approval(
    db: Session,
    *,
    approval_id: UUID,
    action: str,
    resource_type: str,
    resource_id: str,
) -> SecurityApprovalRequest:
    row = db.get(SecurityApprovalRequest, approval_id)
    current = now()
    if row is None:
        raise SecurityApprovalError("security approval not found")
    if row.status != "approved" or row.approved_at is None:
        raise SecurityApprovalError("security approval is not approved")
    if row.expires_at <= current:
        row.status = "expired"
        raise SecurityApprovalError("security approval expired")
    if row.consumed_at is not None:
        raise SecurityApprovalError("security approval was already consumed")
    if row.action != action or row.resource_type != resource_type or row.resource_id != resource_id:
        raise SecurityApprovalError("security approval does not match this operation")
    row.consumed_at = current
    row.status = "consumed"
    return row
