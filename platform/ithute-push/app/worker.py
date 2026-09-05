import time
from datetime import timedelta

from sqlalchemy import select

from .config import get_settings
from .crypto import EndpointCipher
from .db import SessionLocal
from .models import Delivery, Message, utcnow
from .providers import (
    InvalidEndpointError,
    PermanentProviderError,
    ProviderNotConfigured,
    RetryableProviderError,
    deliver,
)


settings = get_settings()
cipher = EndpointCipher(settings.endpoint_encryption_key)
BACKOFF_SECONDS = (60, 300, 1800, 7200)


def refresh_message_status(message: Message) -> None:
    statuses = {delivery.status for delivery in message.deliveries}
    if not statuses:
        message.status = "no_endpoints"
    elif statuses <= {"delivered"}:
        message.status = "delivered"
    elif statuses <= {"failed", "configuration_error", "expired"}:
        message.status = "failed"
    elif "delivered" in statuses and not ({"queued", "retry"} & statuses):
        message.status = "partial"
    else:
        message.status = "processing"


def run_once() -> int:
    processed = 0
    with SessionLocal() as db:
        deliveries = list(
            db.scalars(
                select(Delivery)
                .where(
                    Delivery.status.in_(["queued", "retry"]),
                    Delivery.next_attempt_at <= utcnow(),
                )
                .order_by(Delivery.next_attempt_at)
                .with_for_update(skip_locked=True)
                .limit(20)
            )
        )
        for item in deliveries:
            message = item.message
            endpoint = item.endpoint
            if message.expires_at <= utcnow():
                item.status = "expired"
                refresh_message_status(message)
                processed += 1
                continue
            if not endpoint.active:
                item.status = "failed"
                item.last_error = "endpoint inactive"
                refresh_message_status(message)
                processed += 1
                continue

            item.attempts += 1
            try:
                result = deliver(
                    settings,
                    endpoint.provider,
                    cipher.decrypt(endpoint.endpoint_ciphertext),
                    message,
                    str(item.id),
                )
            except ProviderNotConfigured as exc:
                item.status = "configuration_error"
                item.last_error = str(exc)[:500]
            except InvalidEndpointError as exc:
                item.status = "failed"
                item.last_error = str(exc)[:500]
                endpoint.active = False
            except PermanentProviderError as exc:
                item.status = "failed"
                item.last_error = str(exc)[:500]
            except RetryableProviderError as exc:
                item.last_error = str(exc)[:500]
                if item.attempts >= settings.max_attempts:
                    item.status = "failed"
                else:
                    item.status = "retry"
                    delay = BACKOFF_SECONDS[min(item.attempts - 1, len(BACKOFF_SECONDS) - 1)]
                    item.next_attempt_at = utcnow() + timedelta(seconds=delay)
            except Exception as exc:
                item.last_error = f"unexpected provider failure: {type(exc).__name__}"[:500]
                if item.attempts >= settings.max_attempts:
                    item.status = "failed"
                else:
                    item.status = "retry"
                    item.next_attempt_at = utcnow() + timedelta(seconds=BACKOFF_SECONDS[0])
            else:
                item.status = "delivered"
                item.provider_message_id = result.provider_message_id
                item.delivered_at = utcnow()
                item.last_error = None
            refresh_message_status(message)
            processed += 1
        db.commit()
    return processed


def main() -> None:
    while True:
        processed = run_once()
        if processed == 0:
            time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    main()
