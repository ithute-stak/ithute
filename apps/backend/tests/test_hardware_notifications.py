from app.services import hardware_notifications


def test_push_auto_mode_requires_managed_secret(monkeypatch):
    monkeypatch.setenv("HARDWARE_NOTIFICATION_PUSH_ENABLED", "auto")
    monkeypatch.delenv("HARDWARE_NOTIFICATION_CLIENT_SECRET", raising=False)
    assert hardware_notifications._push_enabled() is False

    monkeypatch.setenv(
        "HARDWARE_NOTIFICATION_CLIENT_SECRET",
        "ithute_svc_test_notification_secret_0123456789abcdef",
    )
    assert hardware_notifications._push_enabled() is True


def test_notification_retry_bounds(monkeypatch):
    monkeypatch.setenv("HARDWARE_NOTIFICATION_RETRY_SECONDS", "1")
    monkeypatch.setenv("HARDWARE_NOTIFICATION_MAX_ATTEMPTS", "999")
    assert hardware_notifications._retry_seconds() == 10
    assert hardware_notifications._max_attempts() == 20

    monkeypatch.setenv("HARDWARE_NOTIFICATION_RETRY_SECONDS", "120")
    monkeypatch.setenv("HARDWARE_NOTIFICATION_MAX_ATTEMPTS", "6")
    assert hardware_notifications._retry_seconds() == 120
    assert hardware_notifications._max_attempts() == 6
