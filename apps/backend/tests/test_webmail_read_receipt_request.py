"""Read receipt requests are opt-in and not proof a message was opened."""
from app.api.v1.webmail import WebmailSend


def test_receipt_request_defaults_off():
    payload = WebmailSend(to=["recipient@example.com"])
    assert payload.request_read_receipt is False


def test_receipt_request_can_be_enabled():
    payload = WebmailSend(to=["recipient@example.com"], request_read_receipt=True)
    assert payload.request_read_receipt is True
