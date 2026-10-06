from __future__ import annotations

import os
import smtplib
import ssl
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

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


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _email_enabled() -> bool:
    return _env_bool("HARDWARE_NOTIFICATION_EMAIL_ENABLED", True)


def _push_enabled() -> bool:
    raw = os.getenv("HARDWARE_NOTIFICATION_PUSH_ENABLED", "auto").strip().lower()
    if raw == "auto":
        return bool(_notification_client_secret())
    return raw in {"1", "true", "yes", "on"}


def _notification_client_id() -> str:
    return os.getenv("HARDWARE_NOTIFICATION_CLIENT_ID", "ithute-notification").strip()


def _notification_client_secret() -> str:
    return os.getenv("HARDWARE_NOTIFICATION_CLIENT_SECRET", "").strip()


def _auth_token_url() -> str:
    return os.getenv(
        "HARDWARE_NOTIFICATION_AUTH_TOKEN_URL",
        "http://ithute-auth:8080/v1/auth/service-token",
    ).rstrip("/")


def _push_url() -> str:
    return os.getenv("HARDWARE_NOTIFICATION_PUSH_URL", "http://ithute-push:8080").rstrip("/")


def _retry_seconds() -> int:
    try:
        return max(10, min(int(os.getenv("HARDWARE_NOTIFICATION_RETRY_SECONDS", "60")), 3600))
    except ValueError:
        return 60


def _max_attempts() -> int:
    try:
        return max(1, min(int(os.getenv("HARDWARE_NOTIFICATION_MAX_ATTEMPTS", "5")), 20))
    except ValueError:
        return 5


def _front_end_url() -> str:
    return os.getenv("FRONTEND_URL", "https://ithute.co.ls").rstrip("/")


def _smtp_port() -> int:
    try:
        return max(1, min(int(os.getenv("SYSTEM_SMTP_PORT", "587")), 65535))
    except ValueError:
        return 587


def _service_token() -> str:
    now = time.time()
    if _push_token.value and _push_token.expires_at - 30 > now:
        return _push_token.value
    secret = (_notification_client_secret() or "").strip()
    if not secret:
        raise RuntimeError("hardware notification Push client secret is not configured")
    with httpx.Client(timeout=10.0, trust_env=False) as client:
        response = client.post(
            _auth_token_url(),
            json={
                "client_id": _notification_client_id(),
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
            f"{_push_url()}/v1/platform/messages",
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
    sender = (os.getenv("SYSTEM_EMAIL_FROM") or "").strip()
    host = (os.getenv("SYSTEM_SMTP_HOST") or "").strip()
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
                f"Open Hardware Intelligence: {_front_end_url()}/system-owner/hardware-intelligence?server={server.id}",
            ]
        )
    )

    timeout = 15
    if _env_bool("SYSTEM_SMTP_SSL", False):
        context = ssl.create_default_context()
        smtp = smtplib.SMTP_SSL(host, _smtp_port(), timeout=timeout, context=context)
    else:
        smtp = smtplib.SMTP(host, _smtp_port(), timeout=timeout)

    with smtp:
        smtp.ehlo()
        if _env_bool("SYSTEM_SMTP_STARTTLS", True) and not _env_bool("SYSTEM_SMTP_SSL", False):
            context = ssl.create_default_context()
            smtp.starttls(context=context)
            smtp.ehlo()
        if os.getenv("SYSTEM_SMTP_USERNAME") and os.getenv("SYSTEM_SMTP_PASSWORD"):
            smtp.login(os.getenv("SYSTEM_SMTP_USERNAME"), os.getenv("SYSTEM_SMTP_PASSWORD"))
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
        if row.channel == "email" and not _email_enabled():
            skipped += 1
            continue
        if row.channel == "push" and not _push_enabled():
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
            if row.attempts >= _max_attempts():
                row.status = "failed"
                row.next_attempt_at = None
                failed += 1
            else:
                row.status = "retry"
                backoff = min(
                    3600,
                    _retry_seconds() * (2 ** max(0, row.attempts - 1)),
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
