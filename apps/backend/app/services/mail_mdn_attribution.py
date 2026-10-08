"""Guardrails for interpreting untrusted message-disposition notifications."""
from dataclasses import dataclass
from email.utils import parseaddr
import re

_ADDRESS = re.compile(r"^[^\s<>@,;]+@[^\s<>@,;]+$")

from app.services.mail_mdn import parse_mdn


@dataclass(frozen=True)
class ReceiptAttribution:
    status: str
    original_message_id: str
    recipient: str


def attribute_receipt(
    *,
    raw: bytes,
    expected_original_message_id: str,
    authenticated_sent_owner: bool,
    expected_recipient: str,
    reported_recipient: str,
    source_authenticated: bool,
) -> ReceiptAttribution | None:
    """Classify an MDN only after matching it to an authenticated owner's sent item.

    Matching is necessary but never sufficient proof of reading: external reports
    can be spoofed. Only verified delivery/authentication evidence can promote
    an acknowledgment to an authenticated status.
    """
    event = parse_mdn(raw)
    if not event or not authenticated_sent_owner:
        return None
    if not expected_original_message_id or event["original_message_id"] != expected_original_message_id:
        return None
    target = parseaddr(expected_recipient)[1].strip().casefold()
    reporter = parseaddr(reported_recipient)[1].strip().casefold()
    if not _ADDRESS.fullmatch(expected_recipient.strip()) or not _ADDRESS.fullmatch(reported_recipient.strip()):
        return None
    if not target or target != reporter:
        return None
    if event["disposition"] != "displayed":
        return ReceiptAttribution("non_read_disposition", event["original_message_id"], target)
    return ReceiptAttribution(
        "authenticated_read_acknowledgment" if source_authenticated else "unverified_read_claim",
        event["original_message_id"],
        target,
    )
