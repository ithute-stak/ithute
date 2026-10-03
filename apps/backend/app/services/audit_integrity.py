from __future__ import annotations

import hashlib
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog


_FIELD_SEPARATOR = "\x1f"


def audit_event_payload(row: AuditLog, previous_hash: str | None) -> str:
    return _FIELD_SEPARATOR.join(
        (
            previous_hash or "",
            str(row.id),
            str(row.tenant_id) if row.tenant_id else "",
            str(row.actor_user_id) if row.actor_user_id else "",
            row.action or "",
            row.resource_type or "",
            row.resource_id or "",
            row.metadata_json or "",
        )
    )


def calculate_event_hash(row: AuditLog, previous_hash: str | None) -> str:
    return hashlib.sha256(audit_event_payload(row, previous_hash).encode("utf-8")).hexdigest()


def verify_audit_chain(db: Session, tenant_id: UUID | None = None, *, limit: int = 5000) -> dict:
    query = select(AuditLog)
    if tenant_id is None:
        query = query.where(AuditLog.tenant_id.is_(None))
    else:
        query = query.where(AuditLog.tenant_id == tenant_id)
    rows = db.scalars(query.order_by(AuditLog.created_at.asc(), AuditLog.id.asc()).limit(limit)).all()

    sealed = [row for row in rows if row.event_hash]
    legacy = len(rows) - len(sealed)
    previous: str | None = None
    broken: list[dict] = []
    verified = 0

    for row in sealed:
        expected = calculate_event_hash(row, previous)
        continuity_ok = row.prev_hash == previous
        hash_ok = row.event_hash == expected
        if not continuity_ok or not hash_ok:
            broken.append(
                {
                    "id": str(row.id),
                    "continuity_ok": continuity_ok,
                    "hash_ok": hash_ok,
                }
            )
        else:
            verified += 1
        previous = row.event_hash

    return {
        "status": "healthy" if not broken else "broken",
        "scope": str(tenant_id) if tenant_id else "platform",
        "rows_scanned": len(rows),
        "sealed_rows": len(sealed),
        "legacy_unsealed_rows": legacy,
        "verified_rows": verified,
        "broken_rows": broken[:100],
        "chain_head": previous,
        "truncated": len(rows) >= limit,
    }


def classify_security_event(row: AuditLog) -> dict:
    action = (row.action or "").lower()
    resource = (row.resource_type or "").lower()
    text = f"{action} {resource}"

    if any(term in text for term in ("failover", "delete", "revoke", "secret", "token", "credential", "dnssec", "security")):
        category = "security"
    elif any(term in text for term in ("login", "auth", "session", "mfa", "passkey")):
        category = "identity"
    elif any(term in text for term in ("mail_node", "backup", "restore", "routing")):
        category = "infrastructure"
    else:
        category = "governance"

    if any(term in action for term in ("failed", "denied", "blocked", "delete", "revoke")):
        severity = "high"
    elif any(term in action for term in ("rotate", "failover", "dnssec", "backup_policy", "status.update")):
        severity = "medium"
    else:
        severity = "info"

    metadata = None
    if row.metadata_json:
        try:
            parsed = json.loads(row.metadata_json)
            metadata = parsed if isinstance(parsed, dict) else {"value": parsed}
        except json.JSONDecodeError:
            metadata = {"unparsed": True}

    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id) if row.tenant_id else None,
        "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
        "action": row.action,
        "resource_type": row.resource_type,
        "resource_id": row.resource_id,
        "category": category,
        "severity": severity,
        "metadata": metadata,
        "sealed": bool(row.event_hash),
        "event_hash": row.event_hash,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
