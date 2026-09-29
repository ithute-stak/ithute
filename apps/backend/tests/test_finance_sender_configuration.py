from sqlalchemy import delete

from app.core.security import decrypt_secret, encrypt_secret
from app.models import FinanceSenderConfiguration
from app.services import finance_mail


def test_finance_sender_is_encrypted_verified_and_used(db, platform_owner, monkeypatch):
    raw_password = "Finance-SMTP-Test-Password!"
    config = FinanceSenderConfiguration(
        sender_email="invoices@example.com",
        smtp_username="invoices@example.com",
        smtp_password_encrypted=encrypt_secret(raw_password),
        smtp_host="smtp.example.com",
        smtp_port=587,
        security_mode="starttls",
        created_by_user_id=platform_owner.id,
        updated_by_user_id=platform_owner.id,
    )
    db.add(config)
    db.commit()
    db.refresh(config)

    assert config.smtp_password_encrypted != raw_password
    assert decrypt_secret(config.smtp_password_encrypted) == raw_password
    public = finance_mail.finance_sender_out(config)
    assert public["has_password"] is True
    assert "smtp_password" not in public
    assert "smtp_password_encrypted" not in public

    observed = {"starttls": False, "login": None, "message": None}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ("smtp.example.com", 587, 20)

        def ehlo(self):
            return 250, b"ok"

        def starttls(self, context=None):
            observed["starttls"] = True
            return 220, b"ready"

        def login(self, username, password):
            observed["login"] = (username, password)
            return 235, b"authenticated"

        def send_message(self, message):
            observed["message"] = message
            return {}

        def quit(self):
            return 221, b"bye"

        def close(self):
            return None

    monkeypatch.setattr(finance_mail.smtplib, "SMTP", FakeSMTP)

    finance_mail.verify_finance_sender(config)
    db.commit()
    assert config.verified_at is not None
    assert observed["starttls"] is True
    assert observed["login"] == ("invoices@example.com", raw_password)

    finance_mail.send_finance_message(
        db,
        recipient="client@example.com",
        subject="Invoice test",
        text_body="Attached invoice",
        html_body="<p>Attached invoice</p>",
        attachment_filename="IM-TEST.pdf",
        attachment_data=b"%PDF-test",
    )
    assert observed["message"] is not None
    assert observed["message"]["From"] == "invoices@example.com"
    assert observed["message"]["To"] == "client@example.com"

    db.execute(delete(FinanceSenderConfiguration).where(FinanceSenderConfiguration.id == config.id))
    db.commit()


def test_unverified_finance_sender_cannot_send(db, platform_owner):
    config = FinanceSenderConfiguration(
        sender_email="invoices@example.com",
        smtp_username="invoices@example.com",
        smtp_password_encrypted=encrypt_secret("Finance-SMTP-Test-Password!"),
        smtp_host="smtp.example.com",
        smtp_port=587,
        security_mode="starttls",
        created_by_user_id=platform_owner.id,
        updated_by_user_id=platform_owner.id,
    )
    db.add(config)
    db.commit()
    try:
        try:
            finance_mail.send_finance_message(
                db,
                recipient="client@example.com",
                subject="Invoice test",
                text_body="Attached invoice",
                html_body=None,
                attachment_filename="IM-TEST.pdf",
                attachment_data=b"%PDF-test",
            )
            raise AssertionError("Expected unverified Finance sender to be rejected")
        except ValueError as exc:
            assert "Verify the Finance sending email" in str(exc)
    finally:
        db.execute(delete(FinanceSenderConfiguration).where(FinanceSenderConfiguration.id == config.id))
        db.commit()
