from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_platform_owner
from app.db.session import get_db
from app.models import AuditLog, IthuteSecurityEvent, SecuritySeverity, User
from app.services.security_operations import (
    SEVERITY_ORDER,
    audit_integrity_status,
    security_operations_summary,
    serialize_security_event,
)


router = APIRouter(prefix="/security/operations", tags=["security-operations"])


@router.get("/summary")
def summary(
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    return security_operations_summary(db)


@router.get("/audit-integrity")
def audit_integrity(
    limit: int = Query(default=1000, ge=1, le=5000),
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    return audit_integrity_status(db, limit)


@router.get("/events")
def events(
    severity: str | None = Query(default=None),
    unresolved_only: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    if severity is not None and severity not in SEVERITY_ORDER:
        raise HTTPException(status_code=422, detail="invalid security severity")
    statement = select(IthuteSecurityEvent)
    if severity is not None:
        statement = statement.where(IthuteSecurityEvent.severity == SecuritySeverity(severity))
    if unresolved_only:
        statement = statement.where(IthuteSecurityEvent.resolved_at.is_(None))
    rows = db.scalars(statement.order_by(IthuteSecurityEvent.created_at.desc()).limit(limit)).all()
    return {"items": [serialize_security_event(item) for item in rows]}


@router.post("/events/{event_id}/resolve")
def resolve_event(
    event_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    item = db.get(IthuteSecurityEvent, event_id)
    if item is None:
        raise HTTPException(status_code=404, detail="security event not found")
    if item.resolved_at is None:
        item.resolved_at = datetime.now(timezone.utc)
        db.add(
            AuditLog(
                actor_user_id=current.id,
                action="security.event.resolve",
                resource_type="security_event",
                resource_id=str(item.id),
                metadata_json='{"outcome":"resolved"}',
            )
        )
        db.commit()
        db.refresh(item)
    return serialize_security_event(item)
