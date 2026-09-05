import os
import uuid
from datetime import datetime, timedelta, timezone

os.environ.setdefault("REALTIME_DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("REALTIME_REDIS_URL", "redis://localhost:6379/15")

import pytest

from app.auth import AuthError, AuthVerifier
from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.events import EventConflict, event_cursor, queue_event, replay_events
from app.schemas import AttachmentRef, MessageCreate, PlatformEventRequest


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


def verifier_with_claims(monkeypatch, claims):
    instance = AuthVerifier.__new__(AuthVerifier)
    instance.settings = get_settings()
    monkeypatch.setattr(instance, "_decode", lambda _token: claims)
    return instance


def test_user_tokens_are_product_scoped(monkeypatch):
    verifier = verifier_with_claims(
        monkeypatch,
        {"token_use": "access", "aud": "loanhub", "sub": "00000000-0000-0000-0000-000000000001"},
    )
    principal = verifier.user("token")
    assert principal.client_id == "loanhub"


def test_unapproved_user_audience_is_rejected(monkeypatch):
    verifier = verifier_with_claims(
        monkeypatch,
        {"token_use": "access", "aud": "unknown-product", "sub": "00000000-0000-0000-0000-000000000001"},
    )
    with pytest.raises(AuthError):
        verifier.user("token")


def test_service_token_requires_realtime_audience_and_scope(monkeypatch):
    verifier = verifier_with_claims(
        monkeypatch,
        {
            "token_use": "service",
            "aud": "ithute-realtime",
            "azp": "ithute-pay",
            "scope": "realtime.publish realtime.manage realtime.broadcast realtime.metrics",
        },
    )
    principal = verifier.service("token", "realtime.publish")
    assert principal.client_id == "ithute-pay"
    assert "realtime.manage" in principal.scopes


def test_service_token_cannot_cross_to_other_audience(monkeypatch):
    verifier = verifier_with_claims(
        monkeypatch,
        {"token_use": "service", "aud": "ithute-push", "azp": "loanhub", "scope": "realtime.publish"},
    )
    with pytest.raises(AuthError):
        verifier.service("token", "realtime.publish")


def test_attachment_references_do_not_accept_insecure_remote_urls():
    with pytest.raises(ValueError):
        AttachmentRef(url="http://example.com/file.pdf", name="file.pdf", content_type="application/pdf", size_bytes=10)
    item = AttachmentRef(url="/files/abc", name="file.pdf", content_type="application/pdf", size_bytes=10)
    assert item.url == "/files/abc"


def test_message_can_be_attachment_only():
    message = MessageCreate(
        attachments=[
            {
                "url": "https://files.ithute.co.ls/x",
                "name": "photo.jpg",
                "content_type": "image/jpeg",
                "size_bytes": 123,
            }
        ]
    )
    assert not message.body
    assert len(message.attachments) == 1


def test_namespaced_event_contract_and_broadcast_audience():
    payload = PlatformEventRequest(
        event_type="payment.updated",
        recipient_subs=[uuid.UUID("00000000-0000-0000-0000-000000000001")],
        data={"payment_id": "p1"},
    )
    assert payload.event_type == "payment.updated"

    broadcast = PlatformEventRequest(event_type="broadcast.message", broadcast_connected=True, body="Maintenance")
    assert broadcast.broadcast_connected is True

    with pytest.raises(ValueError):
        PlatformEventRequest(event_type="PaymentUpdated", broadcast_connected=True)


def test_event_cursor_sorts_by_time():
    first = event_cursor(datetime(2026, 9, 5, 1, 0, tzinfo=timezone.utc))
    second = event_cursor(datetime(2026, 9, 5, 1, 0, 1, tzinfo=timezone.utc))
    assert first < second


def test_durable_event_idempotency_and_replay():
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    with SessionLocal() as db:
        event = queue_event(
            db,
            application_id="loanhub",
            source_client_id="loanhub",
            event_type="loan.approved",
            version=1,
            priority="high",
            recipients=[user_id],
            payload={"title": "Loan approved", "body": "Approved", "data": {"loan_id": "1"}},
            ttl_seconds=3600,
            idempotency_key="loan-approved:1",
        )
        duplicate = queue_event(
            db,
            application_id="loanhub",
            source_client_id="loanhub",
            event_type="loan.approved",
            version=1,
            priority="high",
            recipients=[user_id],
            payload={"title": "Loan approved", "body": "Approved", "data": {"loan_id": "1"}},
            ttl_seconds=3600,
            idempotency_key="loan-approved:1",
        )
        assert duplicate.id == event.id

        with pytest.raises(EventConflict):
            queue_event(
                db,
                application_id="loanhub",
                source_client_id="loanhub",
                event_type="loan.rejected",
                version=1,
                priority="high",
                recipients=[user_id],
                payload={"title": "Different", "body": "Different"},
                ttl_seconds=3600,
                idempotency_key="loan-approved:1",
            )

        event.status = "delivered"
        event.delivered_at = datetime.now(timezone.utc)
        db.commit()
        replayed = replay_events(db, application_id="loanhub", auth_user_id=user_id, after=None, limit=50)
        assert [item.id for item in replayed] == [event.id]


def test_scheduled_event_is_not_immediately_queued():
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    with SessionLocal() as db:
        event = queue_event(
            db,
            application_id="ithute-pay",
            source_client_id="ithute-pay",
            event_type="broadcast.message",
            version=1,
            priority="normal",
            recipients=[user_id],
            payload={"body": "Later"},
            ttl_seconds=3600,
            deliver_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        assert event.status == "scheduled"
