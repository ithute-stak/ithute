from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.models import MailNodeCommand
from app.models.mail import Mailbox, MailboxStorageType


def queue_mailbox_sync(db: Session, mailbox: Mailbox) -> MailNodeCommand | None:
    """Queue the mailbox's desired state for its external mail node.

    Internal mailboxes are synchronized by the local Docker Mailserver hook.
    External mailboxes are reconciled by the Ithute Mail Node Agent.
    """
    if mailbox.storage_type != MailboxStorageType.external or mailbox.mail_node_id is None:
        return None

    payload = {
        "mailbox_id": str(mailbox.id),
        "address": mailbox.address,
        "password_hash": mailbox.password_hash,
        "quota_bytes": mailbox.quota_bytes,
        "status": mailbox.status.value,
        "storage_path": mailbox.storage_path,
    }
    command = MailNodeCommand(
        node_id=mailbox.mail_node_id,
        tenant_id=mailbox.tenant_id,
        mailbox_id=mailbox.id,
        operation="sync",
        payload_json=json.dumps(payload, sort_keys=True),
        status="queued",
    )
    db.add(command)
    return command
