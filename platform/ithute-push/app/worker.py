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


def _delivery_groups(message: Message) -> dict[str, list[Delivery]]:
    groups: dict[str, list[Delivery]] = {}
    for delivery in message.deliveries:
        groups.setdefault(str(delivery.endpoint.device_key), []).append(delivery)
    return groups


def _promote_next_transport(item: Delivery) -> None:
    siblings = sorted(
        (
            delivery
            for delivery in item.message.deliveries
            if delivery.endpoint.device_key == item.endpoint.device_key
            and delivery.status == "standby"
        ),
        key=lambda delivery: delivery.transport_rank,
    )
    if siblings:
        siblings[0].status = "queued"
        siblings[0].next_attempt_at = utcnow()


def _supersede_fallbacks(item: Delivery) -> None:
    for delivery in item.message.deliveries:
        if (
            delivery.endpoint.device_key == item.endpoint.device_key
            and delivery.id != item.id
            and delivery.status == "standby"
        ):
            delivery.status = "superseded"


def refresh_message_status(message: Message) -> None:
    groups = _delivery_groups(message)
    if not groups:
        message.status = "no_endpoints"
        return

    states: list[str] = []
    for deliveries in groups.values():
        statuses = {delivery.status for delivery in deliveries}
        if "delivered" in statuses:
            states.append("delivered")
        elif statuses & {"queued", "retry", "standby"}:
            states.append("processing")
        else:
            states.append("failed")

    if all(state == "delivered" for state in states):
        message.status = "delivered"
    elif all(state == "failed" for state in states):
        message.status = "failed"
    elif "processing" in states:
        message.status = "processing"
    else:
        message.status = "partial"


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
                for sibling in message.deliveries:
                    if sibling.endpoint.device_key == endpoint.device_key and sibling.status == "standby":
                        sibling.status = "expired"
                refresh_message_status(message)
                processed += 1
                continue
            if not endpoint.active:
                item.status = "failed"
                item.last_error = "endpoint inactive"
                _promote_next_transport(item)
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
                _promote_next_transport(item)
            except InvalidEndpointError as exc:
                item.status = "failed"
                item.last_error = str(exc)[:500]
                endpoint.active = False
                _promote_next_transport(item)
            except PermanentProviderError as exc:
                item.status = "failed"
                item.last_error = str(exc)[:500]
                _promote_next_transport(item)
            except RetryableProviderError as exc:
                item.last_error = str(exc)[:500]
                if item.attempts >= settings.max_attempts:
                    item.status = "failed"
                    _promote_next_transport(item)
                else:
                    item.status = "retry"
                    delay = BACKOFF_SECONDS[min(item.attempts - 1, len(BACKOFF_SECONDS) - 1)]
                    item.next_attempt_at = utcnow() + timedelta(seconds=delay)
            except Exception as exc:
                item.last_error = f"unexpected provider failure: {type(exc).__name__}"[:500]
                if item.attempts >= settings.max_attempts:
                    item.status = "failed"
                    _promote_next_transport(item)
                else:
                    item.status = "retry"
                    item.next_attempt_at = utcnow() + timedelta(seconds=BACKOFF_SECONDS[0])
            else:
                item.status = "delivered"
                item.provider_message_id = result.provider_message_id
                item.delivered_at = utcnow()
                item.last_error = None
                _supersede_fallbacks(item)
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
