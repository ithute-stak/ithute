from __future__ import annotations

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Mailbox, MailboxStatus, Tenant, TransactionalMessage
from app.services.system_mailboxes import SYSTEM_DOMAIN, SYSTEM_TENANT_SLUG
from app.services.transactional_mail import send_message

SENDER = f"info@{SYSTEM_DOMAIN}"
RECIPIENT = f"thekoetlisi@{SYSTEM_DOMAIN}"
SUBJECT = "!thute Mail production self-test"


def main() -> None:
    with SessionLocal() as db:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == SYSTEM_TENANT_SLUG))
        if tenant is None:
            raise SystemExit("!thute system tenant is missing")

        addresses = set(
            db.scalars(
                select(Mailbox.address).where(
                    Mailbox.tenant_id == tenant.id,
                    Mailbox.status == MailboxStatus.active,
                )
            ).all()
        )
        required = {SENDER, RECIPIENT, f"supperadmin@{SYSTEM_DOMAIN}"}
        missing = sorted(required - addresses)
        if missing:
            raise SystemExit("Missing active !thute system mailbox(es): " + ", ".join(missing))

        prior = db.scalar(
            select(TransactionalMessage).where(
                TransactionalMessage.tenant_id == tenant.id,
                TransactionalMessage.sender == SENDER,
                TransactionalMessage.subject == SUBJECT,
                TransactionalMessage.status == "queued",
            )
        )
        if prior is not None:
            print(f"System mailbox SMTP submission already verified: {SENDER} -> {RECIPIENT}")
            return

        row = send_message(
            db,
            tenant_id=tenant.id,
            api_key_id=None,
            sender=SENDER,
            recipients=[RECIPIENT],
            subject=SUBJECT,
            text_body="Automated production SMTP self-test for the built-in !thute system mailboxes.",
            html_body=None,
        )
        db.commit()
        if row.status != "queued":
            raise SystemExit(f"System mailbox SMTP submission failed with status={row.status}")
        print(f"System mailbox SMTP submission passed: {SENDER} -> {RECIPIENT}")


if __name__ == "__main__":
    main()
