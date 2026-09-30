import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import make_msgid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decrypt_secret
from app.models.finance import FinanceSenderConfiguration


def get_finance_sender_configuration(db: Session) -> FinanceSenderConfiguration | None:
    return db.scalar(select(FinanceSenderConfiguration).order_by(FinanceSenderConfiguration.created_at.asc()).limit(1))


def finance_sender_out(config: FinanceSenderConfiguration | None) -> dict:
    if config is None:
        return {
            "configured": False,
            "sender_email": "",
            "smtp_username": "",
            "smtp_host": "",
            "smtp_port": 587,
            "security_mode": "starttls",
            "has_password": False,
            "verified": False,
            "verified_at": None,
            "last_verification_error": None,
        }
    return {
        "configured": True,
        "sender_email": config.sender_email,
        "smtp_username": config.smtp_username,
        "smtp_host": config.smtp_host,
        "smtp_port": config.smtp_port,
        "security_mode": config.security_mode,
        "has_password": bool(config.smtp_password_encrypted),
        "verified": config.verified_at is not None,
        "verified_at": config.verified_at.isoformat() if config.verified_at else None,
        "last_verification_error": config.last_verification_error,
    }


def _smtp_session(config: FinanceSenderConfiguration, password: str):
    context = ssl.create_default_context()
    if config.security_mode == "ssl":
        return smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=20, context=context)
    smtp = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=20)
    smtp.ehlo()
    if config.security_mode == "starttls":
        smtp.starttls(context=context)
        smtp.ehlo()
    return smtp


def verify_finance_sender(config: FinanceSenderConfiguration) -> None:
    password = decrypt_secret(config.smtp_password_encrypted)
    smtp = None
    try:
        smtp = _smtp_session(config, password)
        smtp.login(config.smtp_username, password)
        config.verified_at = datetime.now(timezone.utc)
        config.last_verification_error = None
    except Exception as exc:
        config.verified_at = None
        config.last_verification_error = str(exc)[:1000]
        raise
    finally:
        if smtp is not None:
            try:
                smtp.quit()
            except Exception:
                try:
                    smtp.close()
                except Exception:
                    pass


def send_finance_message(
    db: Session,
    *,
    recipient: str,
    subject: str,
    text_body: str,
    html_body: str | None,
    attachment_filename: str | None = None,
    attachment_data: bytes | None = None,
) -> dict:
    config = get_finance_sender_configuration(db)
    if config is None:
        raise ValueError("Configure and verify the Finance sending email before sending invoices")
    if config.verified_at is None:
        raise ValueError("Verify the Finance sending email before sending invoices")

    password = decrypt_secret(config.smtp_password_encrypted)
    msg = EmailMessage()
    msg["From"] = config.sender_email
    msg["To"] = recipient
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain=config.sender_email.split("@")[-1])
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    if attachment_filename and attachment_data is not None:
        msg.add_attachment(attachment_data, maintype="application", subtype="pdf", filename=attachment_filename)

    smtp = None
    refused = {}
    try:
        smtp = _smtp_session(config, password)
        smtp.login(config.smtp_username, password)
        refused = smtp.send_message(msg) or {}
        if recipient in refused:
            code, response = refused[recipient]
            raise RuntimeError(f"SMTP rejected recipient {recipient}: {code} {response!r}")
        return {"provider_message_id": str(msg["Message-ID"]), "accepted": True, "refused": refused}
    finally:
        if smtp is not None:
            try:
                smtp.quit()
            except Exception:
                try:
                    smtp.close()
                except Exception:
                    pass
