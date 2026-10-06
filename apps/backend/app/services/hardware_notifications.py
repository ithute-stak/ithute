from __future__ import annotations

import smtplib
import ssl
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    HardwareIncident,
    HardwareIncidentDelivery,
    InfrastructureServer,
    User,
)


@dataclass
class _CachedServiceToken:
    value: str = ""
    expires_at: float = 0.0


_push_token = _CachedServiceToken()


def _service_token() -> str:
    now = time.time()
    if _push_token.value and _push_token.expires_at - 30 > now:
        return _push_token.value
    secret = (settings.hardware_notification_client_secret or "").strip()
    if not secret:
        raise RuntimeError("hardware notification Push client secret is not configured")
    with httpx.Client(timeout=10.0, trust_env=False) as client:
        response = client.post(
            settings.hardware_notification_auth_token_url,
            json={
                "client_id": settings.hardware_notification_client_id,
                "client_secret": secret,
                "audience": "ithute-push",
                "scope": "push.send.delegated",
            },
        )
        response.raise_for_status()
        payload = response.json()
    token = str(payload.get("access_token") or "")
    if not token:
        raise RuntimeError("Ithute Auth returned an empty notification service token")
    _push_token.value = token
    _push_token.expires_at = now + max(60, int(payload.get("expires_in") or 300))
    return token


def _send_push(
    *,
    recipient_user_id,
    incident: HardwareIncident,
    server: InfrastructureServer,
) -> None:
    token = _service_token()
    with httpx.Client(timeout=10.0, trust_env=False) as client:
        response = client.post(
            f"{settings.hardware_notification_push_url.rstrip('/')}/v1/platform/messages",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": f"hardware:{incident.id}:{recipient_user_id}",
            },
            json={
                "source_client_id": "mailbox-dns",
                "recipient_sub": str(recipient_user_id),
                "title": incident.title[:160],
                "body": incident.summary[:500],
                "route": f"/system-owner/hardware-intelligence?server={server.id}",
                "sound": "default",
                "data": {
                    "type": "hardware.incident",
                    "incident_id": str(incident.id),
                    "server_id": str(server.id),
                    "severity": incident.severity,
                    "predictive_state": incident.predictive_state,
                    "risk_score": incident.predictive_risk_score,
                },
                "ttl_seconds": 3600,
            },
        )
        response.raise_for_status()


def _send_email(
    *,
    recipient: str,
    incident: HardwareIncident,
    server: InfrastructureServer,
) -> None:
    sender = (settings.system_email_from or "").strip()
    host = (settings.system_smtp_host or "").strip()
    if not sender or not host:
        raise RuntimeError("system SMTP is not configured")

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = f"[Ithute Hardware] {incident.title}"
    message.set_content(
        "\n".join(
            [
                incident.title,
                "",
                incident.summary,
                "",
                f"Server: {server.name} ({server.hostname})",
                f"Severity: {incident.severity}",
                f"Health status: {incident.health_status}",
                f"Predictive state: {incident.predictive_state}",
                f"Risk score: {incident.predictive_risk_score if incident.predictive_risk_score is not None else 'n/a'}",
                "",
                f"Open Hardware Intelligence: {settings.frontend_url.rstrip('/')}/system-owner/hardware-intelligence?server={server.id}",
            ]
        )
    )

    timeout = 15
    if settings.system_smtp_ssl:
        context = ssl.create_default_context()
        smtp = smtplib.SMTP_SSL(host, settings.system_smtp_port, timeout=timeout, context=context)
    else:
        smtp = smtplib.SMTP(host, settings.system_smtp_port, timeout=timeout)

    with smtp:
        smtp.ehlo()
        if settings.system_smtp_starttls and not settings.system_smtp_ssl:
            context = ssl.create_default_context()
            smtp.starttls(context=context)
            smtp.ehlo()
        if settings.system_smtp_username and settings.system_smtp_password:
            smtp.login(settings.system_smtp_username, settings.system_smtp_password)
        smtp.send_message(message)


def dispatch_hardware_incident_deliveries(db: Session, limit: int = 50) -> dict:
    now = datetime.now(timezone.utc)
    rows = list(
        db.scalars(
            select(HardwareIncidentDelivery)
            .where(
                HardwareIncidentDelivery.status.in_(["queued", "retry"]),
                or_(
                    HardwareIncidentDelivery.next_attempt_at.is_(None),
                    HardwareIncidentDelivery.next_attempt_at <= now,
                ),
            )
            .order_by(HardwareIncidentDelivery.created_at.asc())
            .limit(max(1, min(limit, 500)))
        ).all()
    )

    delivered = retried = failed = skipped = 0
    for row in rows:
        if row.channel == "email" and not settings.hardware_notification_email_enabled:
            skipped += 1
            continue
        if row.channel == "push" and not settings.hardware_notification_push_enabled:
            skipped += 1
            continue

        incident = db.get(HardwareIncident, row.incident_id)
        recipient = db.get(User, row.recipient_user_id)
        server = db.get(InfrastructureServer, incident.server_id) if incident else None
        if incident is None or recipient is None or server is None:
            row.status = "failed"
            row.last_error = "incident, recipient or server no longer exists"
            row.attempts += 1
            failed += 1
            continue

        try:
            row.attempts += 1
            if row.channel == "email":
                _send_email(recipient=recipient.email, incident=incident, server=server)
            elif row.channel == "push":
                _send_push(recipient_user_id=recipient.id, incident=incident, server=server)
            else:
                raise RuntimeError(f"unsupported hardware notification channel: {row.channel}")
            row.status = "delivered"
            row.delivered_at = now
            row.next_attempt_at = None
            row.last_error = None
            delivered += 1
        except Exception as exc:
            row.last_error = f"{exc.__class__.__name__}: {exc}"[:2000]
            if row.attempts >= settings.hardware_notification_max_attempts:
                row.status = "failed"
                row.next_attempt_at = None
                failed += 1
            else:
                row.status = "retry"
                backoff = min(
                    3600,
                    settings.hardware_notification_retry_seconds * (2 ** max(0, row.attempts - 1)),
                )
                row.next_attempt_at = now + timedelta(seconds=backoff)
                retried += 1

    db.commit()
    return {
        "checked": len(rows),
        "delivered": delivered,
        "retried": retried,
        "failed": failed,
        "skipped_disabled": skipped,
    }
