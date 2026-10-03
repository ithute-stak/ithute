from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, SecurityApprovalRequest, User


def _now() -> datetime:
    return datetime.now(timezone.utc)


def canonical_payload(
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    payload: dict,
) -> tuple[str, str]:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    material = "\x1f".join((action, resource_type, resource_id, body))
    return body, hashlib.sha256(material.encode("utf-8")).hexdigest()


def request_dual_control(
    db: Session,
    *,
    current: User,
    action: str,
    resource_type: str,
    resource_id: str,
    payload: dict,
    tenant_id: UUID | None = None,
    ttl_minutes: int = 15,
) -> SecurityApprovalRequest:
    body, digest = canonical_payload(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        payload=payload,
    )
    now = _now()
    existing = db.scalar(
        select(SecurityApprovalRequest)
        .where(
            SecurityApprovalRequest.action == action,
            SecurityApprovalRequest.resource_type == resource_type,
            SecurityApprovalRequest.resource_id == resource_id,
            SecurityApprovalRequest.payload_hash == digest,
            SecurityApprovalRequest.requested_by_user_id == current.id,
            SecurityApprovalRequest.status == "pending",
            SecurityApprovalRequest.expires_at > now,
        )
        .order_by(SecurityApprovalRequest.created_at.desc())
    )
    if existing is not None:
        return existing

    row = SecurityApprovalRequest(
        tenant_id=tenant_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        payload_json=body,
        payload_hash=digest,
        status="pending",
        requested_by_user_id=current.id,
        created_at=now,
        expires_at=now + timedelta(minutes=max(5, min(ttl_minutes, 60))),
    )
    db.add(row)
    db.flush()
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=current.id,
            action="security.approval.request",
            resource_type=resource_type,
            resource_id=resource_id,
            metadata_json=json.dumps(
                {"approval_id": str(row.id), "protected_action": action, "payload_hash": digest},
                sort_keys=True,
            ),
        )
    )
    db.commit()
    db.refresh(row)
    return row


def approve_dual_control(
    db: Session,
    *,
    current: User,
    approval_id: UUID,
) -> SecurityApprovalRequest:
    row = db.get(SecurityApprovalRequest, approval_id)
    now = _now()
    if row is None:
        raise HTTPException(status_code=404, detail="Security approval not found")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail=f"Security approval is {row.status}")
    if row.expires_at <= now:
        row.status = "expired"
        db.commit()
        raise HTTPException(status_code=409, detail="Security approval expired")
    if row.requested_by_user_id == current.id:
        raise HTTPException(status_code=409, detail="A different administrator must approve this action")

    row.status = "approved"
    row.approved_by_user_id = current.id
    row.approved_at = now
    db.add(
        AuditLog(
            tenant_id=row.tenant_id,
            actor_user_id=current.id,
            action="security.approval.approve",
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            metadata_json=json.dumps(
                {
                    "approval_id": str(row.id),
                    "protected_action": row.action,
                    "requested_by_user_id": str(row.requested_by_user_id),
                },
                sort_keys=True,
            ),
        )
    )
    db.commit()
    db.refresh(row)
    return row


def consume_dual_control(
    db: Session,
    *,
    current: User,
    approval_id: UUID,
    action: str,
    resource_type: str,
    resource_id: str,
    payload: dict,
) -> SecurityApprovalRequest:
    row = db.get(SecurityApprovalRequest, approval_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Security approval not found")
    now = _now()
    if row.status != "approved" or row.approved_by_user_id is None:
        raise HTTPException(status_code=409, detail="Security approval has not been approved")
    if row.expires_at <= now:
        row.status = "expired"
        db.commit()
        raise HTTPException(status_code=409, detail="Security approval expired")
    if row.executed_at is not None:
        raise HTTPException(status_code=409, detail="Security approval was already used")
    if row.requested_by_user_id != current.id:
        raise HTTPException(status_code=403, detail="Only the original requester can execute this approval")
    if row.approved_by_user_id == current.id:
        raise HTTPException(status_code=409, detail="Requester and approver must be different users")

    _, digest = canonical_payload(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        payload=payload,
    )
    if (
        row.action != action
        or row.resource_type != resource_type
        or row.resource_id != resource_id
        or row.payload_hash != digest
    ):
        raise HTTPException(status_code=409, detail="Security approval does not match this operation")

    row.status = "executed"
    row.executed_at = now
    db.add(
        AuditLog(
            tenant_id=row.tenant_id,
            actor_user_id=current.id,
            action="security.approval.consume",
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            metadata_json=json.dumps(
                {"approval_id": str(row.id), "protected_action": row.action},
                sort_keys=True,
            ),
        )
    )
    return row


def approval_json(row: SecurityApprovalRequest) -> dict:
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id) if row.tenant_id else None,
        "action": row.action,
        "resource_type": row.resource_type,
        "resource_id": row.resource_id,
        "status": row.status,
        "requested_by_user_id": str(row.requested_by_user_id),
        "approved_by_user_id": str(row.approved_by_user_id) if row.approved_by_user_id else None,
        "created_at": row.created_at.isoformat(),
        "expires_at": row.expires_at.isoformat(),
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "executed_at": row.executed_at.isoformat() if row.executed_at else None,
    }
