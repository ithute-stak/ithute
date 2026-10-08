"""Parse RFC 8098 message disposition notifications without overstating evidence.

Parsing alone never marks a sent message as read. Callers must authenticate the
mailbox, match the original message ID to an owned sent message, and validate
the origin of an external notification before persisting any status.
"""
from email.message import Message
from email.parser import BytesParser
from email import policy
import re

_MESSAGE_ID = re.compile(r"^<[^<>\r\n]{1,998}>$")
_DISPOSITIONS = {"displayed", "deleted", "dispatched", "processed", "denied", "failed"}


def parse_mdn(raw: bytes) -> dict[str, str] | None:
    if len(raw) > 2_000_000:
        return None
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    if msg.get_content_type() != "multipart/report":
        return None
    if (msg.get_param("report-type", header="content-type") or "").lower() != "disposition-notification":
        return None

    for part in msg.walk():
        if part.get_content_type() != "message/disposition-notification":
            continue
        data = part.get_payload(decode=True)
        if data is None:
            payload = part.get_payload()
            if isinstance(payload, list) and payload:
                fields: Message = payload[0]
            elif isinstance(payload, Message):
                fields = payload
            else:
                continue
        else:
            if len(data) > 16_384:
                return None
            fields = BytesParser(policy=policy.default).parsebytes(data, headersonly=True)
        original = str(fields.get("Original-Message-ID", "")).strip()
        raw_disposition = str(fields.get("Disposition", "")).lower()
        disposition = raw_disposition.split(";", 1)[-1].split("/", 1)[0].strip()
        if not _MESSAGE_ID.fullmatch(original) or disposition not in _DISPOSITIONS:
            return None
        return {"original_message_id": original, "disposition": disposition, "evidence": "unverified_external_mdn"}
    return None
