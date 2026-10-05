from __future__ import annotations

import hmac
import json
from typing import Any

from sqlalchemy import event, insert, text
from sqlalchemy.engine import Connection

from app.core.config import settings
from app.models.entities import AuditLog
from app.models.ithute_operating import IthuteSecurityEvent
from app.services.engine_router import execute_binary, execute_hmac_sha256
from app.services.security_event_rules import audit_security_severity


_INTEGRITY_VERSION = 1
_INSTALLED = False
_ADVISORY_LOCK_ID = 478421773


def _metadata(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {"_raw": value}
    return parsed if isinstance(parsed, dict) else {"_value": parsed}


def _without_integrity(metadata: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in metadata.items() if not key.startswith("_audit_integrity_")}


def _canonical(row: AuditLog, metadata: dict[str, Any], prev_signature: str) -> bytes:
    value = {
        "tenant_id": str(row.tenant_id) if row.tenant_id else None,
        "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
        "action": row.action,
        "resource_type": row.resource_type,
        "resource_id": row.resource_id,
        "metadata": _without_integrity(metadata),
        "prev_signature": prev_signature,
        "version": _INTEGRITY_VERSION,
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sign(payload: bytes) -> str:
    key_hex = str(
        execute_binary(
            "crypto.sha256",
            (settings.secret_key + "|ithute-audit-integrity-v1").encode("utf-8"),
        ).value
    )
    key = bytes.fromhex(key_hex)
    return str(execute_hmac_sha256(key, payload).value)


def _latest_anchor(connection: Connection) -> str:
    if connection.dialect.name == "postgresql":
        connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _ADVISORY_LOCK_ID})
    result = connection.execute(
        text("SELECT id, metadata_json FROM audit_logs ORDER BY created_at DESC, id DESC LIMIT 1")
    ).first()
    if result is None:
        return "genesis"
    metadata = _metadata(result.metadata_json)
    signature = metadata.get("_audit_integrity_signature")
    return str(signature) if signature else f"legacy:{result.id}"


def _before_insert(_mapper, connection: Connection, target: AuditLog) -> None:
    metadata = _metadata(target.metadata_json)
    prev_signature = _latest_anchor(connection)
    metadata = _without_integrity(metadata)
    metadata["_audit_integrity_version"] = _INTEGRITY_VERSION
    metadata["_audit_integrity_prev"] = prev_signature
    metadata["_audit_integrity_signature"] = _sign(_canonical(target, metadata, prev_signature))
    target.metadata_json = json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def verify_audit_row(row: AuditLog) -> dict[str, Any]:
    metadata = _metadata(row.metadata_json)
    signature = str(metadata.get("_audit_integrity_signature") or "")
    prev_signature = str(metadata.get("_audit_integrity_prev") or "")
    version = metadata.get("_audit_integrity_version")
    if not signature or not prev_signature or version != _INTEGRITY_VERSION:
        return {"signed": False, "valid": False, "signature": signature or None, "prev_signature": prev_signature or None}
    expected = _sign(_canonical(row, metadata, prev_signature))
    return {
        "signed": True,
        "valid": hmac.compare_digest(signature, expected),
        "signature": signature,
        "prev_signature": prev_signature,
    }


def _after_insert(_mapper, connection: Connection, target: AuditLog) -> None:
    severity = audit_security_severity(target.action)
    if severity is None:
        return
    metadata = _metadata(target.metadata_json)
    details = {
        "audit_log_id": str(target.id),
        "action": target.action,
        "resource_type": target.resource_type,
        "resource_id": target.resource_id,
        "tenant_id": str(target.tenant_id) if target.tenant_id else None,
        "product": "mailbox-dns",
        "integrity_signature": metadata.get("_audit_integrity_signature"),
    }
    source_ip = metadata.get("client_ip")
    connection.execute(
        insert(IthuteSecurityEvent.__table__).values(
            product_id=None,
            severity=severity,
            event_type=f"audit.{target.action}"[:160],
            actor_ref=str(target.actor_user_id) if target.actor_user_id else None,
            subject_ref=f"audit:{target.id}",
            source_ip=str(source_ip)[:64] if source_ip else None,
            details_json=details,
        )
    )


def install_audit_integrity() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    event.listen(AuditLog, "before_insert", _before_insert)
    event.listen(AuditLog, "after_insert", _after_insert)
    _INSTALLED = True
