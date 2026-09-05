import json
import secrets
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import make_msgid
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decrypt_secret, encrypt_secret
from app.db.session import SessionLocal
from app.models import Domain, DomainStatus, SmtpCredential, TransactionalMessage
from app.services.mailboxes import hash_mailbox_password, normalize_destination


def _strong_secret() -> str:
    return "Tx!" + secrets.token_urlsafe(36) + "aA9"


def _provision_system_credential(tenant_id: UUID) -> tuple[UUID, str]:
    """Persist the internal SMTP credential before another service authenticates it.

    Dovecot checks smtp_credentials through its own PostgreSQL connection. A mere
    flush in the caller's transaction is therefore insufficient: the credential
    must be committed before SMTP AUTH can see it. Use a dedicated short-lived
    transaction so we do not commit unrelated work in the caller's session.
    """
    username = f"api_{tenant_id.hex}"
    for attempt in range(2):
        with SessionLocal() as provisioning_db:
            row = provisioning_db.scalar(select(SmtpCredential).where(SmtpCredential.username == username))
            if row and row.secret_encrypted:
                return row.id, decrypt_secret(row.secret_encrypted)

            raw = _strong_secret()
            if row is None:
                row = SmtpCredential(
                    tenant_id=tenant_id,
                    username=username,
                    password_hash=hash_mailbox_password(raw),
                    secret_encrypted=encrypt_secret(raw),
                    name="Transactional API system credential",
                    system_managed=True,
                    daily_limit=settings.transactional_default_daily_limit,
                    active=True,
                )
                provisioning_db.add(row)
            else:
                row.password_hash = hash_mailbox_password(raw)
                row.secret_encrypted = encrypt_secret(raw)
                row.system_managed = True
                row.active = True

            try:
                provisioning_db.flush()
                credential_id = row.id
                provisioning_db.commit()
                return credential_id, raw
            except IntegrityError:
                provisioning_db.rollback()
                if attempt == 0:
                    # Another first-use request may have created the same
                    # deterministic system credential concurrently. Reload it.
                    continue
                raise

    raise RuntimeError("Unable to provision transactional SMTP credential")


def ensure_system_credential(db: Session, tenant_id: UUID) -> tuple[SmtpCredential, str]:
    username = f"api_{tenant_id.hex}"
    row = db.scalar(select(SmtpCredential).where(SmtpCredential.username == username))
    if row and row.secret_encrypted:
        return row, decrypt_secret(row.secret_encrypted)

    credential_id, raw = _provision_system_credential(tenant_id)

    # The caller remains in its existing transaction. Under PostgreSQL's default
    # READ COMMITTED isolation a new statement can see the independently
    # committed credential. Expire a stale identity-map row if one was loaded.
    if row is not None:
        db.expire(row)
        credential = row
    else:
        credential = db.get(SmtpCredential, credential_id)
    if credential is None or not credential.secret_encrypted:
        raise RuntimeError("Committed transactional SMTP credential is not visible to the caller")
    return credential, raw


def validate_sender(db: Session, tenant_id: UUID, sender: str) -> str:
    clean = normalize_destination(sender)
    domain = clean.rsplit("@", 1)[1]
    exists = db.scalar(
        select(Domain.id).where(
            Domain.tenant_id == tenant_id,
            Domain.ascii_name == domain,
            Domain.status == DomainStatus.verified,
            Domain.mail_enabled.is_(True),
        )
    )
    if not exists:
        raise ValueError("Sender domain must be verified and mail-enabled for this tenant")
    return clean


def send_message(
    db: Session,
    *,
    tenant_id: UUID,
    api_key_id: UUID | None,
    sender: str,
    recipients: list[str],
    subject: str,
    text_body: str | None,
    html_body: str | None,
) -> TransactionalMessage:
    clean_sender = validate_sender(db, tenant_id, sender)
    clean_recipients = [normalize_destination(x) for x in recipients]
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
        msg.set_content("This message contains an HTML part.")
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    row = TransactionalMessage(
        tenant_id=tenant_id,
        api_key_id=api_key_id,
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
