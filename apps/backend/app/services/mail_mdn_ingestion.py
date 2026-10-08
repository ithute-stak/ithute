"""Mail-domain ingestion boundary for untrusted external MDNs.

Caller MUST retrieve the original sent item using an authenticated mailbox
context and provide its actual Message-ID and recipient; no public ingestion
endpoint is exposed. The service never sets a confirmed-read status.
"""
from app.services.mail_mdn_attribution import attribute_receipt
from app.services.mail_receipt_evidence import record_unverified_receipt


def ingest_unverified_mdn(
    db, *, mailbox_id, raw: bytes, sent_message_id: str,
    sent_message_owned: bool, expected_recipient: str, reported_recipient: str,
):
    if mailbox_id is None or not sent_message_owned or not sent_message_id or not expected_recipient or not reported_recipient:
        return None
    receipt = attribute_receipt(
        raw=raw,
        expected_original_message_id=sent_message_id,
        authenticated_sent_owner=sent_message_owned,
        expected_recipient=expected_recipient,
        reported_recipient=reported_recipient,
        source_authenticated=False,
    )
    if receipt is None:
        return None
    from app.services.mail_mdn import parse_mdn
    parsed = parse_mdn(raw)
    if parsed is None:
        return None
    return record_unverified_receipt(
        db, mailbox_id=mailbox_id,
        original_message_id=receipt.original_message_id,
        recipient=receipt.recipient,
        disposition=parsed["disposition"],
        raw_evidence=raw,
    )
