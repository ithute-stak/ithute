"""Scheduled mail must preserve an explicitly requested MDN preference."""
from app.api.v1.webmail_productivity import ScheduleIn
from app.models.webmail_next import ScheduledMail


def test_scheduled_receipt_defaults_to_disabled():
    payload = ScheduleIn(to=["someone@example.com"], delay_seconds=25)
    assert payload.request_read_receipt is False


def test_scheduled_receipt_is_explicit():
    payload = ScheduleIn(to=["someone@example.com"], delay_seconds=25, request_read_receipt=True)
    assert payload.request_read_receipt is True


def test_scheduled_record_includes_receipt_preference():
    assert "request_read_receipt" in ScheduledMail.__table__.columns
