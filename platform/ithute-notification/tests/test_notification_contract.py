from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas import NotificationRequest


ROOT = Path(__file__).parents[1]
AUTH = ROOT / "app" / "auth.py"
MAIN = ROOT / "app" / "main.py"
MODELS = ROOT / "app" / "models.py"
PROVIDERS = ROOT / "app" / "providers.py"
WORKER = ROOT / "app" / "worker.py"
MIGRATION = ROOT / "alembic" / "versions" / "0001_notifications.py"
REPO = ROOT.parent.parent
AUTH_MIGRATION = REPO / "platform" / "ithute-auth" / "alembic" / "versions" / "0008_notification_gateway_client.py"
PUSH_AUTH = REPO / "platform" / "ithute-push" / "app" / "auth.py"
PUSH_PLATFORM = REPO / "platform" / "ithute-push" / "app" / "platform_api.py"
PUSH_CONFIG = REPO / "platform" / "ithute-push" / "app" / "config.py"


def test_notification_requires_target_for_each_selected_channel() -> None:
    with pytest.raises(ValidationError):
        NotificationRequest(source_client_id="business-digital-address", channels=["push"], title="Notice", body="Body")
    request = NotificationRequest(
        source_client_id="business-digital-address",
        recipient_phone="+26662000000",
        channels=["sms", "sms"],
        title="Notice",
        body="Body",
    )
    assert request.channels == ["sms"]


def test_gateway_requires_managed_notification_send_token_and_prevents_namespace_impersonation() -> None:
    auth = AUTH.read_text(encoding="utf-8")
    main = MAIN.read_text(encoding="utf-8")
    assert 'audience="ithute-notification"' in auth
    assert 'claims.get("service_auth") != "managed"' in auth
    assert 'verifier().service(credentials.credentials, "notification.send")' in main
    assert "source_client_id must match authenticated service identity" in main


def test_notification_queue_is_idempotent_and_per_channel() -> None:
    models = MODELS.read_text(encoding="utf-8")
    main = MAIN.read_text(encoding="utf-8")
    assert 'UniqueConstraint("source_client_id", "idempotency_key"' in models
    assert 'UniqueConstraint("notification_id", "channel"' in models
    assert "request_fingerprint" in main
    assert "Idempotency-Key was already used for a different notification" in main

    # The unique-key race can be raised by flush, not only commit. Both must
    # live inside the same IntegrityError boundary so concurrent retries return
    # the winning row instead of an internal server error.
    creation = main.split("item = Notification(", 1)[1]
    assert creation.index("try:") < creation.index("db.flush()")
    assert creation.index("db.flush()") < creation.index("db.commit()")
    assert creation.index("db.commit()") < creation.index("except IntegrityError:")


def test_worker_has_retry_backoff_and_crash_safe_processing_state() -> None:
    source = WORKER.read_text(encoding="utf-8")
    assert "with_for_update(skip_locked=True)" in source
    assert "delivery.status = \"processing\"" in source
    segment = source.split('delivery.status = "processing"', 1)[1].split("try:", 1)[0]
    assert "db.commit()" not in segment
    assert "_backoff" in source
    assert "settings.max_attempts" in source


def test_worker_serializes_and_recomputes_aggregate_status() -> None:
    source = WORKER.read_text(encoding="utf-8")
    assert "select(Notification)" in source
    assert ".with_for_update()" in source
    assert "db.flush()" in source
    assert "select(NotificationDelivery.status)" in source
    assert "_refresh_notification_status(notification, statuses)" in source
    assert "selectinload" not in source


def test_gateway_delegates_push_instead_of_reimplementing_fcm() -> None:
    source = PROVIDERS.read_text(encoding="utf-8")
    assert '"audience": "ithute-push"' in source
    assert '"scope": "push.send.delegated"' in source
    assert "settings.push_url" in source
    assert "fcm" not in source.lower()


def test_auth_registers_notification_gateway_without_a_default_secret() -> None:
    source = AUTH_MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "0008_notification_gateway_client"' in source
    assert 'down_revision = "0007_identity_invites"' in source
    assert '"ithute-notification"' in source
    assert '"ithute-push"' in source
    assert '"push.send.delegated"' in source
    assert "managed_service_credentials" not in source


def test_push_accepts_only_managed_notification_gateway_delegation() -> None:
    auth = PUSH_AUTH.read_text(encoding="utf-8")
    platform = PUSH_PLATFORM.read_text(encoding="utf-8")
    config = PUSH_CONFIG.read_text(encoding="utf-8")
    assert "managed: bool = False" in auth
    assert 'claims.get("service_auth") == "managed"' in auth
    assert 'principal.client_id == "ithute-notification" and not principal.managed' in platform
    assert "ithute-notification" in config
    assert "business-digital-address" in config


def test_notification_database_has_durable_delivery_state() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    for value in (
        'revision = "0001_notifications"',
        '"notifications"',
        '"notification_deliveries"',
        '"attempt_count"',
        '"next_attempt_at"',
        '"provider_reference"',
        '"last_error"',
    ):
        assert value in source
