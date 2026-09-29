import uuid

from sqlalchemy import delete, select

from app.core.security import decrypt_secret
from app.db.session import SessionLocal
from app.models import Domain, DomainDnsMode, DomainStatus, SmtpCredential, TransactionalMessage
from app.services import transactional_mail
from app.services.mailboxes import hash_mailbox_password


def _create_verified_domain(db, tenant_admin):
    user, tenant, _membership = tenant_admin
    domain_name = f"tx-{uuid.uuid4().hex[:12]}.example.com"
    domain = Domain(
        tenant_id=tenant.id,
        ascii_name=domain_name,
        unicode_name=domain_name,
        status=DomainStatus.verified,
        dns_mode=DomainDnsMode.platform,
        mail_enabled=True,
        verification_token_hash="a" * 64,
        verification_token_hint="tx-test",
        verification_record_name=f"_verify.{domain_name}",
        created_by_user_id=user.id,
    )
    db.add(domain)
    db.commit()
    return tenant, domain_name, domain


def _cleanup(db, tenant_id, domain_id):
    db.rollback()
    db.execute(delete(TransactionalMessage).where(TransactionalMessage.tenant_id == tenant_id))
    db.execute(delete(SmtpCredential).where(SmtpCredential.tenant_id == tenant_id))
    db.execute(delete(Domain).where(Domain.id == domain_id))
    db.commit()


def test_system_smtp_credential_is_committed_before_external_auth(db, tenant_admin, monkeypatch):
    tenant, domain_name, domain = _create_verified_domain(db, tenant_admin)
    observed = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            observed["endpoint"] = (host, port, timeout)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def ehlo(self):
            return 250, b"ok"

        def starttls(self, context=None):
            return 220, b"ready"

        def login(self, username, password):
            # Model Dovecot: authentication is performed through another
            # PostgreSQL connection, not through the request's SQLAlchemy
            # transaction. The system credential must already be committed and
            # its password_hash must describe the same raw secret being sent.
            with SessionLocal() as auth_db:
                credential = auth_db.scalar(select(SmtpCredential).where(SmtpCredential.username == username))
                assert credential is not None
                assert credential.active is True
                assert credential.system_managed is True
                assert credential.secret_encrypted is not None
                assert decrypt_secret(credential.secret_encrypted) == password
                assert transactional_mail._secret_matches_password_hash(credential, password)
                observed["credential_id"] = credential.id
            return 235, b"authenticated"

        def send_message(self, message):
            observed["message_id"] = message["Message-ID"]
            return {}

    monkeypatch.setattr(transactional_mail.smtplib, "SMTP", FakeSMTP)

    try:
        row = transactional_mail.send_message(
            db,
            tenant_id=tenant.id,
            api_key_id=None,
            sender=f"sender@{domain_name}",
            recipients=[f"recipient@{domain_name}"],
            subject="Credential visibility regression",
            text_body="SMTP auth must see the committed system credential.",
            html_body=None,
        )
        assert row.status == "queued"
        assert row.credential_id == observed["credential_id"]
        assert observed["message_id"] == row.message_id
        db.commit()
    finally:
        _cleanup(db, tenant.id, domain.id)


def test_mismatched_encrypted_secret_and_password_hash_are_rotated(db, tenant_admin):
    tenant, _domain_name, domain = _create_verified_domain(db, tenant_admin)

    try:
        credential, original_secret = transactional_mail.ensure_system_credential(db, tenant.id)
        original_id = credential.id

        # Reproduce the production failure: the application can decrypt one raw
        # secret while Dovecot's password_hash represents a different password.
        different_secret = "DifferentSecret!A9-transactional"
        credential.password_hash = hash_mailbox_password(different_secret)
        db.commit()
        assert not transactional_mail._secret_matches_password_hash(credential, original_secret)

        repaired, repaired_secret = transactional_mail.ensure_system_credential(db, tenant.id)
        assert repaired.id == original_id
        assert repaired_secret != original_secret
        assert decrypt_secret(repaired.secret_encrypted) == repaired_secret
        assert transactional_mail._secret_matches_password_hash(repaired, repaired_secret)
        assert repaired.active is True
        assert repaired.system_managed is True
    finally:
        _cleanup(db, tenant.id, domain.id)
