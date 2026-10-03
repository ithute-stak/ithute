from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_platform_owner
from app.db.session import get_db
from app.models import SecurityApprovalRequest, User
from app.services.security_approvals import approval_json, approve_dual_control

router = APIRouter(prefix="/security/approvals", tags=["security-approvals"])


@router.get("")
def list_approvals(
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    rows = db.scalars(
        select(SecurityApprovalRequest)
        .order_by(SecurityApprovalRequest.created_at.desc())
        .limit(200)
    ).all()
    return {"items": [approval_json(row) for row in rows]}


@router.post("/{approval_id}/approve")
def approve_request(
    approval_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    row = approve_dual_control(db, current=current, approval_id=approval_id)
    return approval_json(row)
