from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, IthuteSecurityEvent
from app.services.audit_integrity import verify_audit_row


SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def _severity_value(item: IthuteSecurityEvent) -> str:
    return item.severity.value if hasattr(item.severity, "value") else str(item.severity)


def serialize_security_event(item: IthuteSecurityEvent) -> dict:
    return {
        "id": str(item.id),
        "product_id": item.product_id,
        "severity": _severity_value(item),
        "event_type": item.event_type,
        "actor_ref": item.actor_ref,
        "subject_ref": item.subject_ref,
        "source_ip": item.source_ip,
        "details": item.details_json or {},
        "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def audit_integrity_status(db: Session, limit: int = 1000) -> dict:
    rows = list(
        db.scalars(
            select(AuditLog)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(max(1, min(limit, 5000)))
        )
    )
    rows.reverse()

    signed_started = False
    previous_signature: str | None = None
    signed = 0
    unsigned_after_chain = 0
    invalid_signatures = 0
    broken_links = 0
    latest_signature = None

    for row in rows:
        result = verify_audit_row(row)
        if not result["signed"]:
            if signed_started:
                unsigned_after_chain += 1
            continue

        signed_started = True
        signed += 1
        if not result["valid"]:
            invalid_signatures += 1
        if previous_signature is not None and result["prev_signature"] != previous_signature:
            broken_links += 1
        previous_signature = result["signature"]
        latest_signature = result["signature"]

    healthy = invalid_signatures == 0 and broken_links == 0 and unsigned_after_chain == 0
    return {
        "healthy": healthy,
        "checked_rows": len(rows),
        "signed_rows": signed,
        "invalid_signatures": invalid_signatures,
        "broken_links": broken_links,
        "unsigned_after_chain": unsigned_after_chain,
        "latest_signature": latest_signature,
        "detail": (
            "Signed audit history passed HMAC and chain-link verification."
            if healthy
            else "Audit integrity verification detected a modified, missing, or unsigned entry inside the signed history."
        ),
    }


def security_operations_summary(db: Session) -> dict:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    events = list(
        db.scalars(
            select(IthuteSecurityEvent)
            .where(IthuteSecurityEvent.created_at >= since)
            .order_by(IthuteSecurityEvent.created_at.desc())
            .limit(2000)
        )
    )
    counts = {key: 0 for key in SEVERITY_ORDER}
    unresolved = 0
    for item in events:
        severity = _severity_value(item)
        counts[severity] = counts.get(severity, 0) + 1
        if item.resolved_at is None and SEVERITY_ORDER.get(severity, 0) >= SEVERITY_ORDER["medium"]:
            unresolved += 1

    integrity = audit_integrity_status(db)
    posture = "healthy"
    if not integrity["healthy"] or counts.get("critical", 0):
        posture = "critical"
    elif counts.get("high", 0) or unresolved:
        posture = "attention"

    return {
        "posture": posture,
        "window": "24h",
        "events_total": len(events),
        "severity": counts,
        "unresolved_actionable": unresolved,
        "audit_integrity": integrity,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
