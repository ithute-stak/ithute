"""Persist receipt *evidence*, never infer reading from a notification alone."""
import hashlib
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.webmail_next import MailReadReceiptEvidence

ALLOWED_STATUSES = {"unverified_read_claim", "non_read_disposition"}


def record_unverified_receipt(
    db: Session, *, mailbox_id, original_message_id: str, recipient: str,
    disposition: str, raw_evidence: bytes,
) -> MailReadReceiptEvidence:
    """Only the server may call this with an authenticated mailbox_id.

    This operation deliberately does not support verified/read statuses.
    Attribution to a sent item must be checked before invoking this function.
    """
    if not original_message_id.startswith("<") or not original_message_id.endswith(">"):
        raise ValueError("Invalid original Message-ID")
    if not (0 < len(raw_evidence) <= 2_000_000):
        raise ValueError("Invalid receipt size")
    if disposition not in {"displayed", "deleted", "dispatched", "processed", "denied", "failed"}:
        raise ValueError("Invalid disposition")
    if not recipient or len(recipient) > 320:
        raise ValueError("Invalid recipient")
    evidence_key = hashlib.sha256(raw_evidence).hexdigest()
    previous = db.scalar(select(MailReadReceiptEvidence).where(
        MailReadReceiptEvidence.mailbox_id == mailbox_id,
        MailReadReceiptEvidence.evidence_key == evidence_key,
    ))
    if previous is not None:
        return previous
    status = "unverified_read_claim" if disposition == "displayed" else "non_read_disposition"
    row = MailReadReceiptEvidence(
        mailbox_id=mailbox_id, original_message_id=original_message_id,
        recipient=recipient.lower(), disposition=disposition, evidence_status=status,
        evidence_key=evidence_key,
    )
    db.add(row)
    db.flush()
    return row
