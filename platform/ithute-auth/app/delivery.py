import smtplib
from email.message import EmailMessage

import httpx

from .config import Settings


class DeliveryUnavailable(RuntimeError):
    pass


def send_email(settings: Settings, *, recipient: str, subject: str, body: str) -> None:
    if not settings.smtp_host or not settings.smtp_from:
        raise DeliveryUnavailable("email delivery is not configured")
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


def send_sms(settings: Settings, *, phone: str, message: str) -> None:
    if not settings.sms_webhook_url:
        raise DeliveryUnavailable("SMS delivery is not configured")
    headers = {"content-type": "application/json"}
    if settings.sms_webhook_token:
        headers["authorization"] = f"Bearer {settings.sms_webhook_token}"
    response = httpx.post(
        settings.sms_webhook_url,
        json={"phone": phone, "message": message},
        headers=headers,
        timeout=10,
    )
    response.raise_for_status()
