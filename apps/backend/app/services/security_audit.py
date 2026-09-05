import hashlib
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Mailbox

_ALLOWED_METADATA_KEYS = {"client_ip", "user_agent", "request_id", "outcome", "retry_after"}


def _target_digest(address: str) -> str:
    return hashlib.sha256(address.strip().lower().encode("utf-8")).hexdigest()[:24]


def record_webmail_security_event(
    db: Session,
    *,
    action: str,
    address: str,
    client_ip: str,
    user_agent: str | None = None,
    request_id: str | None = None,
    outcome: str,
    retry_after: int | None = None,
) -> AuditLog:
    """Append a redacted webmail security event to the existing audit ledger.

    Mailbox addresses are resolved to an internal mailbox id when possible. For
    unknown login targets only a short SHA-256 digest is stored, so attempted
    credentials and plaintext unknown addresses never enter the audit log.
    Passwords, session tokens, message bodies and attachment contents are never
    accepted by this API.
    """
    normalized = address.strip().lower()
    mailbox = db.scalar(select(Mailbox).where(Mailbox.address == normalized))
    metadata = {
        "client_ip": (client_ip or "unknown")[:64],
        "user_agent": (user_agent or "")[:512],
        "request_id": (request_id or "")[:64],
        "outcome": outcome[:64],
    }
    if retry_after is not None:
        metadata["retry_after"] = max(0, int(retry_after))
    metadata = {key: value for key, value in metadata.items() if key in _ALLOWED_METADATA_KEYS}
    row = AuditLog(
        tenant_id=mailbox.tenant_id if mailbox else None,
        actor_user_id=None,
        action=action[:100],
        resource_type="mailbox_security",
        resource_id=str(mailbox.id) if mailbox else f"unknown:{_target_digest(normalized)}",
        metadata_json=json.dumps(metadata, sort_keys=True, separators=(",", ":")),
    )
    db.add(row)
    db.flush()
    return row


def assert_redacted_metadata(metadata_json: str | None, forbidden_values: list[str]) -> None:
    """Verifier helper that raises if a secret value appears in audit metadata."""
    text = metadata_json or ""
    for value in forbidden_values:
        if value and value in text:
            raise ValueError("Sensitive value leaked into security audit metadata")
