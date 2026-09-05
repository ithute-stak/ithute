#!/usr/bin/env python3
import hashlib
import imaplib
import smtplib
import ssl
import time
import uuid
from email import message_from_bytes
from email.message import EmailMessage

from cryptography.hazmat.primitives.serialization import load_pem_private_key
from redis import Redis
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.security import decrypt_dkim_secret
from app.db.session import SessionLocal
from app.models.deliverability import DkimKey
from app.models.domains import Domain
from app.services.deliverability import generate_dkim_material
from app.services.dkim_sync import sync_active_dkim_keys

ADDRESS = "phase6@phase6.test"
PASSWORD = "Phase6Strong!Pass"
DOMAIN = "phase6.test"
SELECTOR = "phase8"
SMTP_HOST = "postfix"
SMTP_PORT = 587
IMAP_HOST = "dovecot"
IMAP_PORT = 993


def seed_and_sync() -> None:
    expected_private_key: str | None = None
    with SessionLocal() as db:
        domain = db.scalar(select(Domain).where(Domain.ascii_name == DOMAIN))
        if not domain:
            raise RuntimeError("Phase 6 regression fixture domain is missing")

        db.execute(delete(DkimKey).where(DkimKey.domain_id == domain.id, DkimKey.selector == SELECTOR))
        for key in db.scalars(select(DkimKey).where(DkimKey.domain_id == domain.id, DkimKey.active.is_(True))).all():
            key.active = False

        encrypted, public = generate_dkim_material()
        dkim_key = DkimKey(
            tenant_id=domain.tenant_id,
            domain_id=domain.id,
            selector=SELECTOR,
            public_key_b64=public,
            private_key_encrypted=encrypted,
            created_by_user_id=domain.created_by_user_id,
            active=True,
        )
        db.add(dkim_key)
        db.commit()

        expected_private_key = decrypt_dkim_secret(dkim_key.private_key_encrypted)
        load_pem_private_key(expected_private_key.encode(), password=None)

        count = sync_active_dkim_keys(db)
        if count < 1:
            raise RuntimeError("No active DKIM domains were synchronized")

    redis = Redis.from_url(settings.rspamd_redis_url, decode_responses=True)
    selected = redis.hget("dkim_selectors", DOMAIN)
    if selected != SELECTOR:
        raise RuntimeError(f"Rspamd Redis selector mismatch: expected {SELECTOR!r}, got {selected!r}")

    key_field = f"{SELECTOR}.{DOMAIN}"
    redis_private_key = redis.hget("dkim_keys", key_field)
    if not redis_private_key:
        raise RuntimeError(f"Rspamd Redis has no DKIM private key at {key_field!r}")
    load_pem_private_key(redis_private_key.encode(), password=None)

    expected_hash = hashlib.sha256(expected_private_key.encode()).digest()
    redis_hash = hashlib.sha256(redis_private_key.encode()).digest()
    if expected_hash != redis_hash:
        raise RuntimeError("Rspamd Redis DKIM private key does not match the active control-plane key")

    print(f"DKIM Redis sync verified: domain={DOMAIN} selector={SELECTOR} key_present=yes key_parseable=yes")


def send_and_fetch() -> bytes:
    context = ssl._create_unverified_context()
    marker = f"phase8-dkim-{uuid.uuid4().hex}"
    message = EmailMessage()
    message["From"] = ADDRESS
    message["To"] = ADDRESS
    message["Subject"] = marker
    message.set_content(marker)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        smtp.login(ADDRESS, PASSWORD)
        refused = smtp.send_message(message)
        if refused:
            raise RuntimeError(f"SMTP refused recipients: {refused}")

    deadline = time.time() + 25
    while time.time() < deadline:
        with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=context, timeout=10) as imap:
            imap.login(ADDRESS, PASSWORD)
            imap.select("INBOX")
            status, data = imap.search(None, "SUBJECT", f'"{marker}"')
            if status == "OK" and data and data[0]:
                msg_id = data[0].split()[-1]
                status, parts = imap.fetch(msg_id, "(RFC822)")
                if status == "OK" and parts and isinstance(parts[0], tuple):
                    return parts[0][1]
        time.sleep(1)
    raise RuntimeError("Signed message was not visible through IMAPS before timeout")


def main() -> None:
    seed_and_sync()
    raw = send_and_fetch()
    message = message_from_bytes(raw)
    signature = message.get("DKIM-Signature")
    if not signature:
        raise RuntimeError("Authenticated outbound message has no DKIM-Signature header")
    normalized = signature.replace("\r", "").replace("\n", "").replace(" ", "")
    if f"d={DOMAIN}" not in normalized:
        raise RuntimeError(f"DKIM signature used unexpected domain: {signature}")
    if f"s={SELECTOR}" not in normalized:
        raise RuntimeError(f"DKIM signature used unexpected selector: {signature}")
    if "a=rsa-sha256" not in normalized.lower():
        raise RuntimeError(f"DKIM signature is not rsa-sha256: {signature}")

    print("Phase 8 Rspamd DKIM signing smoke PASSED.")
    print("Verified authenticated submission receives a DKIM-Signature using the active encrypted control-plane key without restarting Rspamd.")


if __name__ == "__main__":
    main()
