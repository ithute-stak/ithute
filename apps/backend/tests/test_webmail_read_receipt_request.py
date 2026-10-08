"""Read receipt requests are opt-in and not proof a message was opened."""
from unittest.mock import MagicMock, patch

from app.api.v1.webmail import WebmailRichSend, WebmailSend
from app.services.webmail import send_message


def test_receipt_request_defaults_off():
    payload = WebmailSend(to=["recipient@example.com"])
    assert payload.request_read_receipt is False


def test_receipt_request_can_be_enabled():
    payload = WebmailSend(to=["recipient@example.com"], request_read_receipt=True)
    assert payload.request_read_receipt is True


def test_rich_receipt_request_defaults_off():
    assert WebmailRichSend(to=["recipient@example.com"]).request_read_receipt is False


def test_rich_receipt_request_enabled():
    assert WebmailRichSend(to=["recipient@example.com"], request_read_receipt=True).request_read_receipt is True


@patch("app.services.webmail._imap")
@patch("app.services.webmail.smtplib.SMTP")
@patch("app.services.webmail._mail_transport")
def test_standard_mdn_header_only_when_opted_in(transport, smtp_class, imap):
    transport.return_value = {"smtp_host": "localhost", "smtp_port": 587}
    smtp = MagicMock()
    smtp_class.return_value.__enter__.return_value = smtp
    imap.return_value.append.return_value = ("OK", [b"ok"])

    send_message("sender@example.com", "password", ["recipient@example.com"], [], [],
                 "Subject", "Body", request_read_receipt=True)
    message = smtp.send_message.call_args.args[0]
    assert message["Disposition-Notification-To"] == "sender@example.com"

    send_message("sender@example.com", "password", ["recipient@example.com"], [], [],
                 "Subject", "Body", request_read_receipt=False)
    message = smtp.send_message.call_args.args[0]
    assert message.get("Disposition-Notification-To") is None
