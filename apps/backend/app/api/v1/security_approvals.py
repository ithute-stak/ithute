from __future__ import annotations

import json
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_platform_owner
from app.core.config import settings
from app.db.session import get_db
from app.models import AuditLog, SecurityApprovalRequest, User
from app.services.security_approvals import now


router = APIRouter(prefix="/security/approvals", tags=["security-approvals"])


class ApprovalCreate(BaseModel):
    action: str = Field(min_length=3, max_length=80, pattern=r"^[a-z0-9._:-]+$")
    resource_type: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9._:-]+$")
    resource_id: str = Field(min_length=1, max_length=160)
    payload: dict = Field(default_factory=dict)


def _out(row: SecurityApprovalRequest) -> dict:
    return {
        "id": str(row.id),
        "action": row.action,
        "resource_type": row.resource_type,
        "resource_id": row.resource_id,
        "payload": json.loads(row.payload_json or "{}"),
        "status": row.status,
        "requested_by_user_id": str(row.requested_by_user_id),
        "approved_by_user_id": str(row.approved_by_user_id) if row.approved_by_user_id else None,
        "expires_at": row.expires_at.isoformat(),
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "consumed_at": row.consumed_at.isoformat() if row.consumed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("")
def list_security_approvals(
    status: str | None = Query(default=None, max_length=24),
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    statement = select(SecurityApprovalRequest)
    if status:
        statement = statement.where(SecurityApprovalRequest.status == status)
    rows = db.scalars(statement.order_by(SecurityApprovalRequest.created_at.desc()).limit(200)).all()
    return {"items": [_out(row) for row in rows]}


@router.post("", status_code=201)
def request_security_approval(
    payload: ApprovalCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    expires = now() + timedelta(minutes=settings.security_approval_ttl_minutes)
    row = SecurityApprovalRequest(
        action=payload.action,
        resource_type=payload.resource_type,
        resource_id=payload.resource_id,
        payload_json=json.dumps(payload.payload, sort_keys=True, separators=(",", ":")),
        requested_by_user_id=current.id,
        expires_at=expires,
    )
    db.add(row)
    db.flush()
    db.add(AuditLog(
        actor_user_id=current.id,
        action="security.approval.request",
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        metadata_json=json.dumps({"approval_id": str(row.id), "action": row.action}, sort_keys=True),
    ))
    db.commit()
    db.refresh(row)
    return _out(row)


@router.post("/{approval_id}/approve")
def approve_security_approval(
    approval_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    row = db.get(SecurityApprovalRequest, approval_id)
    if row is None:
        raise HTTPException(status_code=404, detail="security approval not found")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="security approval is no longer pending")
    if row.expires_at <= now():
        row.status = "expired"
        db.commit()
        raise HTTPException(status_code=409, detail="security approval expired")
    if row.requested_by_user_id == current.id:
        raise HTTPException(status_code=409, detail="requester cannot approve their own security change")
    row.status = "approved"
    row.approved_by_user_id = current.id
    row.approved_at = now()
    db.add(AuditLog(
        actor_user_id=current.id,
        action="security.approval.approve",
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        metadata_json=json.dumps({"approval_id": str(row.id), "action": row.action}, sort_keys=True),
    ))
    db.commit()
    db.refresh(row)
    return _out(row)


@router.post("/{approval_id}/reject")
def reject_security_approval(
    approval_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    row = db.get(SecurityApprovalRequest, approval_id)
    if row is None:
        raise HTTPException(status_code=404, detail="security approval not found")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="security approval is no longer pending")
    row.status = "rejected"
    row.approved_by_user_id = current.id
    row.approved_at = now()
    db.add(AuditLog(
        actor_user_id=current.id,
        action="security.approval.reject",
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        metadata_json=json.dumps({"approval_id": str(row.id), "action": row.action}, sort_keys=True),
    ))
    db.commit()
    db.refresh(row)
    return _out(row)
