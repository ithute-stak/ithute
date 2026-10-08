from email.message import EmailMessage

from app.services.mail_mdn import parse_mdn


def make_mdn(disposition="manual-action/MDN-sent-manually; displayed"):
    message = EmailMessage()
    message.set_type("multipart/report")
    message.set_param("report-type", "disposition-notification")
    body = EmailMessage()
    body.set_content("The message was displayed.")
    message.attach(body)
    report = EmailMessage()
    report.set_type("message/disposition-notification")
    fields = EmailMessage()
    fields["Original-Message-ID"] = "<original@example.com>"
    fields["Disposition"] = disposition
    report.set_payload([fields])
    message.attach(report)
    return message.as_bytes()


def test_mdn_is_unverified_not_confirmed_read():
    result = parse_mdn(make_mdn())
    assert result == {
        "original_message_id": "<original@example.com>",
        "disposition": "displayed",
        "evidence": "unverified_external_mdn",
    }


def test_rejects_non_receipt_message():
    assert parse_mdn(b"Subject: Hello\r\n\r\nHi") is None


def test_rejects_unsupported_disposition():
    assert parse_mdn(make_mdn("automatic-action/MDN-sent-automatically; suspicious")) is None
