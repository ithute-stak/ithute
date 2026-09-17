from __future__ import annotations

import base64
import binascii
import hashlib
import json
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import make_msgid
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import TransactionalMessage
from app.services.mailboxes import normalize_destination
from app.services.transactional_mail import ensure_system_credential, validate_sender


ALLOWED_ATTACHMENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "text/plain",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
MAX_TOTAL_ATTACHMENT_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class DecodedAttachment:
    filename: str
    content_type: str
    content: bytes

    @property
    def sha256_hex(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


def decode_attachments(items) -> list[DecodedAttachment]:
    decoded: list[DecodedAttachment] = []
    total = 0
    for item in items:
        content_type = item.content_type.strip().lower()
        if content_type not in ALLOWED_ATTACHMENT_TYPES:
            raise ValueError("attachment content type is not allowed")
        try:
            content = base64.b64decode(item.content_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("attachment content is not valid base64") from exc
        if not content:
            raise ValueError("attachment cannot be empty")
        if len(content) > MAX_ATTACHMENT_BYTES:
            raise ValueError("attachment exceeds the 5 MB limit")
        total += len(content)
        if total > MAX_TOTAL_ATTACHMENT_BYTES:
            raise ValueError("attachments exceed the 10 MB total limit")
        decoded.append(DecodedAttachment(filename=item.filename, content_type=content_type, content=content))
    return decoded


def attachment_fingerprint(attachments: list[DecodedAttachment]) -> list[dict[str, str | int]]:
    return [
        {
            "filename": item.filename,
            "content_type": item.content_type,
            "size_bytes": len(item.content),
            "sha256": item.sha256_hex,
        }
        for item in attachments
    ]


def send_message_with_attachments(
    db: Session,
    *,
    tenant_id: UUID,
    sender: str,
    recipients: list[str],
    subject: str,
    text_body: str | None,
    html_body: str | None,
    attachments: list[DecodedAttachment],
) -> TransactionalMessage:
    clean_sender = validate_sender(db, tenant_id, sender)
    clean_recipients = [normalize_destination(value) for value in recipients]
    if not clean_recipients or len(clean_recipients) > settings.transactional_max_recipients:
        raise ValueError(f"Recipient count must be between 1 and {settings.transactional_max_recipients}")

    credential, password = ensure_system_credential(db, tenant_id)
    msg = EmailMessage()
    msg["From"] = clean_sender
    msg["To"] = ", ".join(clean_recipients)
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain=clean_sender.rsplit("@", 1)[1])
    if text_body:
        msg.set_content(text_body)
    else:
        msg.set_content("This message contains an HTML part or attachments.")
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    for item in attachments:
        maintype, subtype = item.content_type.split("/", 1)
        msg.add_attachment(item.content, maintype=maintype, subtype=subtype, filename=item.filename)

    row = TransactionalMessage(
        tenant_id=tenant_id,
        api_key_id=None,
        credential_id=credential.id,
        message_id=msg["Message-ID"],
        sender=clean_sender,
        recipients_json=json.dumps(clean_recipients),
        subject=subject,
        status="submitting",
    )
    db.add(row)
    db.flush()
    try:
        context = ssl.create_default_context()
        if not settings.transactional_smtp_verify_tls:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        with smtplib.SMTP(settings.transactional_smtp_host, settings.transactional_smtp_port, timeout=20) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
            smtp.login(credential.username, password)
            smtp.send_message(msg)
        row.status = "queued"
        credential.last_used_at = datetime.now(timezone.utc)
    except Exception as exc:
        row.status = "failed"
        row.error = str(exc)[:4000]
        db.flush()
        raise
    return row
