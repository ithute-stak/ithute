from __future__ import annotations

import smtplib
from email.message import EmailMessage

import httpx

from .config import Settings


class ProviderUnavailable(RuntimeError):
    pass


def send_email(settings: Settings, *, recipient: str, title: str, body: str) -> str:
    if not settings.smtp_host or not settings.smtp_from:
        raise ProviderUnavailable("email provider is not configured")
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = recipient
    message["Subject"] = title
    message.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.provider_timeout_seconds) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)
    return str(message.get("Message-ID") or "smtp-accepted")


def send_sms(settings: Settings, *, phone: str, body: str) -> str:
    if not settings.sms_webhook_url:
        raise ProviderUnavailable("SMS provider is not configured")
    headers = {"content-type": "application/json"}
    if settings.sms_webhook_token:
        headers["authorization"] = f"Bearer {settings.sms_webhook_token}"
    response = httpx.post(
        settings.sms_webhook_url,
        json={"phone": phone, "message": body},
        headers=headers,
        timeout=settings.provider_timeout_seconds,
    )
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    return str(payload.get("id") or payload.get("message_id") or "sms-accepted")


def _push_service_token(settings: Settings) -> str:
    if not settings.auth_client_secret:
        raise ProviderUnavailable("notification-to-push service credential is not configured")
    response = httpx.post(
        settings.auth_token_url,
        json={
            "client_id": settings.auth_client_id,
            "client_secret": settings.auth_client_secret,
            "audience": "ithute-push",
            "scope": "push.send.delegated",
        },
        timeout=settings.provider_timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise ProviderUnavailable("Ithute Auth did not return a Push service token")
    return token


def send_push(
    settings: Settings,
    *,
    source_client_id: str,
    recipient_sub: str,
    title: str,
    body: str,
    route: str | None,
    sound: str | None,
    data: dict,
    ttl_seconds: int,
    idempotency_key: str,
) -> str:
    token = _push_service_token(settings)
    response = httpx.post(
        settings.push_url,
        json={
            "source_client_id": source_client_id,
            "recipient_sub": recipient_sub,
            "title": title,
            "body": body[:500],
            "route": route,
            "sound": sound,
            "data": data,
            "ttl_seconds": ttl_seconds,
        },
        headers={
            "authorization": f"Bearer {token}",
            "Idempotency-Key": idempotency_key,
        },
        timeout=settings.provider_timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    message_id = payload.get("id")
    if not message_id:
        raise ProviderUnavailable("Ithute Push did not return a message id")
    return str(message_id)
