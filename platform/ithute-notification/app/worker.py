from __future__ import annotations

import json
import time
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .config import get_settings
from .db import SessionLocal
from .models import Notification, NotificationDelivery, utcnow
from .providers import send_email, send_push, send_sms


def _backoff(attempt: int) -> timedelta:
    seconds = min(900, 5 * (2 ** max(0, attempt - 1)))
    return timedelta(seconds=seconds)


def _refresh_notification_status(notification: Notification) -> None:
    statuses = {delivery.status for delivery in notification.deliveries}
    if statuses and statuses <= {"delivered"}:
        notification.status = "delivered"
        notification.completed_at = utcnow()
    elif "pending" in statuses or "retry" in statuses or "processing" in statuses:
        notification.status = "queued"
        notification.completed_at = None
    elif "delivered" in statuses:
        notification.status = "partial"
        notification.completed_at = utcnow()
    else:
        notification.status = "failed"
        notification.completed_at = utcnow()


def _deliver(notification: Notification, delivery: NotificationDelivery) -> str:
    settings = get_settings()
    meta = json.loads(notification.data_json or "{}")
    data = meta.get("data") if isinstance(meta.get("data"), dict) else {}
    sound = meta.get("sound") if isinstance(meta.get("sound"), str) else "default"
    ttl_seconds = int(meta.get("ttl_seconds") or 3600)

    if delivery.channel == "email":
        if not notification.recipient_email:
            raise RuntimeError("email target is missing")
        return send_email(settings, recipient=notification.recipient_email, title=notification.title, body=notification.body)
    if delivery.channel == "sms":
        if not notification.recipient_phone:
            raise RuntimeError("SMS target is missing")
        return send_sms(settings, phone=notification.recipient_phone, body=notification.body)
    if delivery.channel == "push":
        if not notification.recipient_sub:
            raise RuntimeError("Push recipient identity is missing")
        return send_push(
            settings,
            source_client_id=notification.source_client_id,
            recipient_sub=notification.recipient_sub,
            title=notification.title,
            body=notification.body,
            route=notification.route,
            sound=sound,
            data=data,
            ttl_seconds=ttl_seconds,
            idempotency_key=f"notification:{notification.id}:push",
        )
    raise RuntimeError(f"unsupported notification channel: {delivery.channel}")


def process_one() -> bool:
    settings = get_settings()
    with SessionLocal() as db:
        delivery = db.scalar(
            select(NotificationDelivery)
            .where(
                NotificationDelivery.status.in_(["pending", "retry"]),
                NotificationDelivery.next_attempt_at <= utcnow(),
            )
            .order_by(NotificationDelivery.created_at)
            .with_for_update(skip_locked=True)
        )
        if delivery is None:
            return False
        notification = db.scalar(
            select(Notification)
            .options(selectinload(Notification.deliveries))
            .where(Notification.id == delivery.notification_id)
        )
        if notification is None:
            delivery.status = "failed"
            delivery.last_error = "notification record missing"
            db.commit()
            return True

        # Keep the selected delivery row locked until the provider attempt has
        # been recorded. If the worker crashes, the transaction rolls back to
        # pending/retry rather than leaving a permanent "processing" record.
        delivery.status = "processing"
        delivery.attempt_count += 1
        delivery.last_attempt_at = utcnow()

        try:
            reference = _deliver(notification, delivery)
        except Exception as exc:
            delivery.last_error = f"{type(exc).__name__}: {str(exc)}"[:255]
            if delivery.attempt_count >= settings.max_attempts:
                delivery.status = "failed"
            else:
                delivery.status = "retry"
                delivery.next_attempt_at = utcnow() + _backoff(delivery.attempt_count)
        else:
            delivery.status = "delivered"
            delivery.provider_reference = reference[:255]
            delivery.last_error = None
            delivery.delivered_at = utcnow()
        _refresh_notification_status(notification)
        db.commit()
        return True


def main() -> None:
    settings = get_settings()
    while True:
        worked = process_one()
        if not worked:
            time.sleep(max(0.2, settings.worker_poll_seconds))


if __name__ == "__main__":
    main()
