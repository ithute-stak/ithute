import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import get_settings
from .hub import hub
from .models import EventRecipient, RealtimeEvent, utcnow
from .push import push_bridge


class EventConflict(ValueError):
    pass


def event_cursor(now: datetime | None = None) -> str:
    instant = now or datetime.now(timezone.utc)
    micros = int(instant.timestamp() * 1_000_000)
    return f"{micros:020d}-{uuid.uuid4().hex}"


def _fingerprint(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def event_wire(event: RealtimeEvent) -> dict:
    try:
        payload = json.loads(event.payload_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    # Product payload is intentionally flattened for convenient clients, but
    # protocol-owned fields always win so an application cannot spoof another
    # product, cursor, recipient set or event identity.
    return {
        **payload,
        "type": event.event_type,
        "version": event.version,
        "event_id": str(event.id),
        "cursor": event.cursor,
        "application_id": event.application_id,
        "priority": event.priority,
        "audience_label": event.audience_label,
        "recipients": [str(item.auth_user_id) for item in event.recipients],
        "broadcast_connected": event.broadcast_connected,
        "created_at": event.created_at.isoformat(),
        "expires_at": event.expires_at.isoformat(),
    }


def _existing_idempotent_event(
    db: Session,
    *,
    application_id: str,
    idempotency_key: str,
    fingerprint: str,
) -> RealtimeEvent | None:
    existing = db.scalar(
        select(RealtimeEvent).where(
            RealtimeEvent.application_id == application_id,
            RealtimeEvent.idempotency_key == idempotency_key,
        )
    )
    if existing is not None and existing.request_fingerprint != fingerprint:
        raise EventConflict("Idempotency-Key was already used for a different event")
    return existing


def queue_event(
    db: Session,
    *,
    application_id: str,
    source_client_id: str,
    event_type: str,
    version: int,
    priority: str,
    recipients: list[uuid.UUID],
    payload: dict,
    ttl_seconds: int,
    deliver_at: datetime | None = None,
    push_enabled: bool = False,
    broadcast_connected: bool = False,
    audience_label: str | None = None,
    idempotency_key: str | None = None,
) -> RealtimeEvent:
    settings = get_settings()
    if len(recipients) > settings.max_event_recipients:
        raise ValueError("event recipient limit exceeded")
    now = utcnow()
    scheduled = deliver_at or now
    if scheduled.tzinfo is None:
        scheduled = scheduled.replace(tzinfo=timezone.utc)
    fingerprint_payload = {
        "application_id": application_id,
        "event_type": event_type,
        "version": version,
        "priority": priority,
        "recipients": sorted(str(item) for item in recipients),
        "payload": payload,
        "ttl_seconds": ttl_seconds,
        "deliver_at": deliver_at.isoformat() if deliver_at is not None else None,
        "push_enabled": push_enabled,
        "broadcast_connected": broadcast_connected,
        "audience_label": audience_label,
    }
    fingerprint = _fingerprint(fingerprint_payload)
    if idempotency_key:
        existing = _existing_idempotent_event(
            db,
            application_id=application_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
        )
        if existing is not None:
            return existing
    event = RealtimeEvent(
        cursor=event_cursor(now),
        application_id=application_id,
        source_client_id=source_client_id,
        event_type=event_type,
        version=version,
        priority=priority,
        audience_label=audience_label,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint if idempotency_key else None,
        payload_json=json.dumps(payload, separators=(",", ":"), ensure_ascii=False, default=str),
        broadcast_connected=broadcast_connected,
        push_enabled=push_enabled,
        status="scheduled" if scheduled > now else "queued",
        max_attempts=settings.event_max_attempts,
        deliver_at=scheduled,
        expires_at=scheduled + timedelta(seconds=ttl_seconds),
    )
    db.add(event)
    try:
        db.flush()
        for recipient in dict.fromkeys(recipients):
            db.add(EventRecipient(event_id=event.id, auth_user_id=recipient))
        db.commit()
    except IntegrityError:
        db.rollback()
        if not idempotency_key:
            raise
        existing = _existing_idempotent_event(
            db,
            application_id=application_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
        )
        if existing is None:
            raise
        return existing
    db.refresh(event)
    return event


async def deliver_event(db: Session, event: RealtimeEvent) -> RealtimeEvent:
    settings = get_settings()
    now = utcnow()
    if event.expires_at <= now:
        event.status = "expired"
        event.last_error = "event TTL expired before delivery"
        db.commit()
        return event
    if event.deliver_at > now:
        event.status = "scheduled"
        db.commit()
        return event
    event.status = "publishing"
    event.attempts += 1
    db.commit()
    try:
        await hub.publish(event.application_id, event_wire(event))
        if event.push_enabled:
            try:
                payload = json.loads(event.payload_json or "{}")
            except json.JSONDecodeError:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            for recipient in event.recipients:
                if await hub.is_online(event.application_id, str(recipient.auth_user_id)):
                    continue
                await asyncio.to_thread(
                    push_bridge.notify_event,
                    source_client_id=event.application_id,
                    recipient_sub=recipient.auth_user_id,
                    event_id=event.id,
                    event_type=event.event_type,
                    title=str(payload.get("title") or "Ithute notification"),
                    body=str(payload.get("body") or "You have a new update"),
                    route=payload.get("route"),
                    data=payload.get("data") if isinstance(payload.get("data"), dict) else {},
                    ttl_seconds=max(60, int((event.expires_at - now).total_seconds())),
                    priority=event.priority,
                )
                recipient.push_requested_at = utcnow()
        event.status = "delivered"
        event.delivered_at = utcnow()
        event.last_error = None
    except Exception as exc:
        event.last_error = str(exc)[:1000]
        if event.attempts >= event.max_attempts:
            event.status = "dead_letter"
        else:
            event.status = "retry"
            event.deliver_at = utcnow() + timedelta(seconds=settings.event_retry_seconds * event.attempts)
    db.commit()
    db.refresh(event)
    return event


async def process_due_events(db: Session, limit: int = 100) -> int:
    now = utcnow()
    rows = list(
        db.scalars(
            select(RealtimeEvent)
            .where(
                RealtimeEvent.status.in_(["queued", "scheduled", "retry"]),
                RealtimeEvent.deliver_at <= now,
            )
            .order_by(RealtimeEvent.deliver_at.asc())
            .limit(limit)
        )
    )
    count = 0
    for event in rows:
        await deliver_event(db, event)
        count += 1
    return count


def replay_events(
    db: Session,
    *,
    application_id: str,
    auth_user_id: uuid.UUID,
    after: str | None,
    limit: int,
) -> list[RealtimeEvent]:
    now = utcnow()
    stmt = (
        select(RealtimeEvent)
        .join(EventRecipient, EventRecipient.event_id == RealtimeEvent.id)
        .where(
            RealtimeEvent.application_id == application_id,
            EventRecipient.auth_user_id == auth_user_id,
            RealtimeEvent.expires_at > now,
            RealtimeEvent.status.in_(["delivered", "publishing", "retry"]),
        )
    )
    if after:
        stmt = stmt.where(RealtimeEvent.cursor > after)
    return list(db.scalars(stmt.order_by(RealtimeEvent.cursor.asc()).limit(limit)))


def pending_or_dead_counts(db: Session, application_id: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for status in ("queued", "scheduled", "retry", "dead_letter", "expired", "delivered"):
        rows = list(
            db.scalars(
                select(RealtimeEvent.id).where(
                    RealtimeEvent.application_id == application_id,
                    RealtimeEvent.status == status,
                )
            )
        )
        result[status] = len(rows)
    return result
