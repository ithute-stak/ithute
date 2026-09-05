#!/usr/bin/env python3
import imaplib
import json
import os
import smtplib
import ssl
import time
import urllib.error
import urllib.request
import uuid
from email.message import EmailMessage
from http.cookiejar import CookieJar

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import MembershipRole, MembershipStatus, Tenant, TenantMembership, TenantStatus, User
from app.models.domains import Domain, DomainDnsMode, DomainStatus
from app.models.mail import Mailbox

API_BASE = os.getenv("PHASE7_API_BASE", "http://backend:8000/api/v1")
SMTP_HOST = os.getenv("PHASE7_SMTP_HOST", "postfix")
SMTP_PORT = int(os.getenv("PHASE7_SMTP_PORT", "587"))
SMTP_INBOUND_PORT = int(os.getenv("PHASE7_SMTP_INBOUND_PORT", "25"))
IMAP_HOST = os.getenv("PHASE7_IMAP_HOST", "dovecot")
IMAP_PORT = int(os.getenv("PHASE7_IMAP_PORT", "993"))
TEST_PASSWORD = "Phase7Smoke!Pass2026"
ADMIN_PASSWORD = "Phase7Admin!Pass2026"
TENANT_SLUG = "phase7-live-smoke"
DOMAIN_NAME = "phase7.test"
# Use a syntactically valid non-special-use domain because Pydantic's EmailStr
# rejects RFC-reserved suffixes such as .invalid for login request validation.
ADMIN_EMAIL = "phase7-admin@phase7-smoke.co.ls"


def seed_control_plane():
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == ADMIN_EMAIL))
        if not user:
            user = User(
                email=ADMIN_EMAIL,
                password_hash=hash_password(ADMIN_PASSWORD),
                full_name="Phase 7 Smoke Admin",
                is_active=True,
                is_platform_owner=False,
            )
            db.add(user)
            db.flush()
        else:
            user.password_hash = hash_password(ADMIN_PASSWORD)
            user.is_active = True
            user.mfa_enabled = False
            user.mfa_secret = None

        tenant = db.scalar(select(Tenant).where(Tenant.slug == TENANT_SLUG))
        if not tenant:
            tenant = Tenant(name="Phase 7 Live Smoke", slug=TENANT_SLUG, status=TenantStatus.active)
            db.add(tenant)
            db.flush()
        else:
            tenant.status = TenantStatus.active

        membership = db.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant.id,
                TenantMembership.user_id == user.id,
            )
        )
        if not membership:
            db.add(TenantMembership(
                tenant_id=tenant.id,
                user_id=user.id,
                role=MembershipRole.tenant_admin,
                status=MembershipStatus.active,
            ))
        else:
            membership.role = MembershipRole.tenant_admin
            membership.status = MembershipStatus.active

        domain = db.scalar(select(Domain).where(Domain.ascii_name == DOMAIN_NAME))
        if not domain:
            domain = Domain(
                tenant_id=tenant.id,
                ascii_name=DOMAIN_NAME,
                unicode_name=DOMAIN_NAME,
                status=DomainStatus.verified,
                dns_mode=DomainDnsMode.external,
                mail_enabled=True,
                verification_token_hash="7" * 64,
                verification_token_hint="phase7-smoke",
                verification_record_name=f"_mailbox-dns-verification.{DOMAIN_NAME}",
                created_by_user_id=user.id,
            )
            db.add(domain)
        else:
            domain.tenant_id = tenant.id
            domain.status = DomainStatus.verified
            domain.mail_enabled = True
        db.commit()
        db.refresh(tenant)
        db.refresh(domain)
        return str(tenant.id), str(domain.id)
    finally:
        db.close()


def api_client():
    jar = CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def request_json(opener, method, path, payload=None, expected=(200,)):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with opener.open(req, timeout=10) as response:
            body = response.read()
            if response.status not in expected:
                raise RuntimeError(f"{method} {path}: unexpected {response.status}: {body.decode()}")
            return json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(f"{method} {path}: HTTP {exc.code}: {body}") from exc


def smtp_auth_works(address, password):
    context = ssl._create_unverified_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        smtp.login(address, password)


def send_and_retrieve(address, password, marker):
    context = ssl._create_unverified_context()
    message = EmailMessage()
    message["From"] = address
    message["To"] = address
    message["Subject"] = f"Phase 7 live smoke {marker}"
    message.set_content(f"phase7-live-smoke-marker={marker}")

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        smtp.login(address, password)
        refused = smtp.send_message(message)
        if refused:
            raise RuntimeError(f"SMTP refused recipients: {refused}")

    deadline = time.time() + 20
    while time.time() < deadline:
        with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=context, timeout=10) as imap:
            imap.login(address, password)
            imap.select("INBOX")
            status, data = imap.search(None, "ALL")
            if status == "OK" and data and data[0]:
                for msg_id in reversed(data[0].split()):
                    status, parts = imap.fetch(msg_id, "(RFC822)")
                    if status == "OK" and parts and isinstance(parts[0], tuple):
                        raw = parts[0][1].decode(errors="replace")
                        if marker in raw:
                            return
        time.sleep(1)
    raise RuntimeError("Message was not visible through IMAPS before timeout")


def assert_suspended(address, password):
    try:
        smtp_auth_works(address, password)
    except smtplib.SMTPAuthenticationError:
        pass
    else:
        raise RuntimeError("Suspended mailbox still authenticated through SMTP submission")

    with smtplib.SMTP(SMTP_HOST, SMTP_INBOUND_PORT, timeout=10) as smtp:
        smtp.ehlo()
        smtp.mail("external@example.net")
        code, _ = smtp.rcpt(address)
        if code < 400:
            raise RuntimeError(f"Suspended mailbox still accepted inbound RCPT with SMTP {code}")


def main():
    tenant_id, domain_id = seed_control_plane()
    opener = api_client()
    request_json(opener, "POST", "/auth/login", {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, expected=(200,))

    local_part = f"live-{uuid.uuid4().hex[:10]}"
    address = f"{local_part}@{DOMAIN_NAME}"
    created = request_json(
        opener,
        "POST",
        f"/tenants/{tenant_id}/mailboxes",
        {
            "domain_id": domain_id,
            "local_part": local_part,
            "display_name": "Phase 7 Live Smoke",
            "password": TEST_PASSWORD,
            "quota_bytes": 1024**3,
        },
        expected=(201,),
    )
    mailbox_id = created["id"]
    if created["address"] != address:
        raise RuntimeError("API returned an unexpected mailbox address")

    marker = uuid.uuid4().hex
    send_and_retrieve(address, TEST_PASSWORD, marker)

    request_json(opener, "POST", f"/tenants/{tenant_id}/mailboxes/{mailbox_id}/suspend", {}, expected=(200,))
    assert_suspended(address, TEST_PASSWORD)

    request_json(opener, "POST", f"/tenants/{tenant_id}/mailboxes/{mailbox_id}/restore", {}, expected=(200,))
    smtp_auth_works(address, TEST_PASSWORD)

    request_json(opener, "DELETE", f"/tenants/{tenant_id}/mailboxes/{mailbox_id}", expected=(200,))
    db = SessionLocal()
    try:
        item = db.scalar(select(Mailbox).where(Mailbox.id == uuid.UUID(mailbox_id)))
        if not item or item.status.value != "archived":
            raise RuntimeError("Mailbox archive state was not persisted")
    finally:
        db.close()

    print("Phase 7 live API mailbox lifecycle smoke PASSED.")
    print("Verified API create -> immediate SMTP/IMAP use -> suspend enforcement -> restore -> archive without mail-service restart.")


if __name__ == "__main__":
    main()
