from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select

from app.core.security import decrypt_secret
from app.db.session import SessionLocal
from app.models import ConnectedMailAccount, Mailbox, MailboxStatus, ScheduledMail
from app.services.connected_mail import ConnectedMailError, config_for_account, send_message as send_connected
from app.services.webmail_polish import send_rich_message


_worker_started = False
_worker_lock = threading.Lock()


def _claim_one() -> str | None:
    now = datetime.now(timezone.utc)
    stale = now - timedelta(minutes=15)
    with SessionLocal() as db:
        row = db.scalar(
            select(ScheduledMail)
            .where(
                ScheduledMail.scheduled_at <= now,
                or_(
                    ScheduledMail.status == "queued",
                    (ScheduledMail.status == "sending") & (ScheduledMail.updated_at < stale),
                ),
            )
            .order_by(ScheduledMail.scheduled_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if row is None:
            return None
        row.status = "sending"
        row.error = None
        db.commit()
        return str(row.id)


def _deliver(job_id: str) -> None:
    from uuid import UUID

    with SessionLocal() as db:
        row = db.get(ScheduledMail, UUID(job_id))
        if row is None or row.status != "sending":
            return
        mailbox = db.get(Mailbox, row.mailbox_id)
        if mailbox is None or mailbox.status != MailboxStatus.active:
            row.status = "failed"
            row.error = "The sending Ithute mailbox is no longer active"
            row.auth_secret_encrypted = None
            db.commit()
            return

        try:
            if row.connected_account_id:
                account = db.get(ConnectedMailAccount, row.connected_account_id)
                if account is None or account.mailbox_id != mailbox.id:
                    raise RuntimeError("The connected sending account is no longer available")
                config = config_for_account(account, db)
                send_connected(
                    config,
                    to=list(row.to_json or []),
                    cc=list(row.cc_json or []),
                    bcc=list(row.bcc_json or []),
                    subject=row.subject,
                    body_text=row.body_text,
                    body_html=row.body_html,
                    attachments=list(row.attachments_json or []),
                )
            else:
                if not row.auth_secret_encrypted:
                    raise RuntimeError("Scheduled hosted-mail authorization expired")
                password = decrypt_secret(row.auth_secret_encrypted)
                send_rich_message(
                    mailbox.address,
                    password,
                    list(row.to_json or []),
                    list(row.cc_json or []),
                    list(row.bcc_json or []),
                    row.subject,
                    row.body_text,
                    row.body_html,
                    attachments=list(row.attachments_json or []),
                )
            row.status = "sent"
            row.sent_at = datetime.now(timezone.utc)
            row.error = None
            row.auth_secret_encrypted = None
        except (ConnectedMailError, RuntimeError, ValueError, Exception) as exc:
            row.status = "failed"
            row.error = str(exc)[:5000]
            row.auth_secret_encrypted = None
        db.commit()


def process_due_scheduled_mail(max_jobs: int = 20) -> int:
    processed = 0
    for _ in range(max(1, min(max_jobs, 100))):
        job_id = _claim_one()
        if not job_id:
            break
        _deliver(job_id)
        processed += 1
    return processed


def _worker_loop() -> None:
    while True:
        try:
            process_due_scheduled_mail()
        except Exception:
            # A scheduler problem must not crash the API process. The next loop
            # retries queued jobs, and stale `sending` claims are recovered.
            pass
        time.sleep(15)


def start_scheduled_mail_worker() -> None:
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        thread = threading.Thread(target=_worker_loop, name="ithute-scheduled-mail", daemon=True)
        thread.start()
        _worker_started = True
