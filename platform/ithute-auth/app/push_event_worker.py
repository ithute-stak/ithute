from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta

import httpx
from sqlalchemy import select

from .config import get_settings
from .db import SessionLocal
from .models import AuthEventOutbox, utcnow
from .security import create_service_token


logger = logging.getLogger("ithute.auth.push_events")
_BATCH_SIZE = 100
_MAX_BACKOFF_SECONDS = 300


@dataclass(frozen=True)
class ClaimedEvent:
    event_id: uuid.UUID
    payload: dict[str, object]
    attempts: int


def _backoff_seconds(attempts: int) -> int:
    return min(_MAX_BACKOFF_SECONDS, max(2, 2 ** min(attempts, 8)))


def _payload(row: AuthEventOutbox) -> dict[str, object]:
    try:
        details = json.loads(row.payload_json or "{}")
    except json.JSONDecodeError:
        details = {}
    if not isinstance(details, dict):
        details = {}
    return {
        "event_id": str(row.id),
        "type": row.event_type,
        "sub": str(row.subject_user_id) if row.subject_user_id else None,
        "sid": str(row.session_id) if row.session_id else None,
        "client_id": row.client_id,
        "occurred_at": row.created_at.isoformat(),
        "details": details,
    }


def _claim_next() -> ClaimedEvent | None:
    """Lease one due outbox row and release the DB lock before network I/O.

    Multiple workers may run concurrently. `FOR UPDATE SKIP LOCKED` serializes the
    short claim transaction, while `next_attempt_at` acts as a crash-safe lease.
    If a worker dies after claiming, another worker retries after the lease expires.
    """
    settings = get_settings()
    now = utcnow()
    lease_until = now + timedelta(seconds=max(5, settings.push_event_lease_seconds))
    with SessionLocal() as db:
        row = db.scalar(
            select(AuthEventOutbox)
            .where(
                AuthEventOutbox.delivered_at.is_(None),
                AuthEventOutbox.next_attempt_at <= now,
            )
            .order_by(AuthEventOutbox.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if row is None:
            return None
        row.next_attempt_at = lease_until
        claimed = ClaimedEvent(event_id=row.id, payload=_payload(row), attempts=row.attempts)
        db.commit()
        return claimed


def _settle_success(event_id: uuid.UUID) -> bool:
    with SessionLocal() as db:
        row = db.get(AuthEventOutbox, event_id)
        if row is None or row.delivered_at is not None:
            return False
        row.attempts += 1
        row.last_error = None
        row.delivered_at = utcnow()
        db.commit()
        return True


def _settle_failure(event_id: uuid.UUID, error: str) -> None:
    with SessionLocal() as db:
        row = db.get(AuthEventOutbox, event_id)
        if row is None or row.delivered_at is not None:
            return
        row.attempts += 1
        row.last_error = error[:500]
        row.next_attempt_at = utcnow() + timedelta(seconds=_backoff_seconds(row.attempts))
        db.commit()
        logger.warning(
            "Auth lifecycle event delivery failed event_id=%s type=%s attempt=%s retry_seconds=%s error=%s",
            row.id,
            row.event_type,
            row.attempts,
            _backoff_seconds(row.attempts),
            row.last_error,
        )


def run_once() -> int:
    settings = get_settings()
    token = create_service_token(
        settings=settings,
        client_id="ithute-auth",
        audience="ithute-push",
        scope="push.lifecycle",
    )
    headers = {"Authorization": f"Bearer {token}"}
    delivered = 0

    with httpx.Client(timeout=settings.push_event_request_timeout_seconds) as client:
        for _ in range(_BATCH_SIZE):
            claimed = _claim_next()
            if claimed is None:
                break
            try:
                response = client.post(settings.push_events_url, headers=headers, json=claimed.payload)
                response.raise_for_status()
            except Exception as exc:
                _settle_failure(claimed.event_id, str(exc))
            else:
                if _settle_success(claimed.event_id):
                    delivered += 1

    if delivered:
        logger.info("Delivered %s Auth lifecycle event(s) to Push", delivered)
    return delivered


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    logger.info("Starting Auth lifecycle event worker destination=%s", settings.push_events_url)
    while True:
        try:
            run_once()
        except Exception:
            # Never log bearer tokens or full event payloads. The durable outbox
            # remains authoritative and the worker retries on the next cycle.
            logger.exception("Auth lifecycle worker cycle failed")
        time.sleep(max(0.25, settings.push_event_worker_poll_seconds))


if __name__ == "__main__":
    main()
