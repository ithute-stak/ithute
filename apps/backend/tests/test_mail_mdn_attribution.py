from email.message import EmailMessage

from app.services.mail_mdn_attribution import attribute_receipt


def sample():
    mail = EmailMessage()
    mail.set_type("multipart/report")
    mail.set_param("report-type", "disposition-notification")
    part = EmailMessage()
    part.set_type("message/disposition-notification")
    fields = EmailMessage()
    fields["Original-Message-ID"] = "<sent@example.com>"
    fields["Disposition"] = "manual-action/MDN-sent-manually; displayed"
    part.set_payload([fields])
    mail.attach(part)
    return mail.as_bytes()


def check(**changes):
    args = dict(raw=sample(), expected_original_message_id="<sent@example.com>",
                authenticated_sent_owner=True, expected_recipient="recipient@example.com",
                reported_recipient="recipient@example.com", source_authenticated=False)
    args.update(changes)
    return attribute_receipt(**args)


def test_rejects_wrong_owner():
    assert check(authenticated_sent_owner=False) is None


def test_rejects_wrong_message_id():
    assert check(expected_original_message_id="<other@example.com>") is None


def test_rejects_wrong_recipient():
    assert check(reported_recipient="imposter@example.com") is None


def test_unverified_mdn_never_becomes_confirmed():
    result = check()
    assert result is not None
    assert result.status == "unverified_read_claim"


def test_authenticated_receipt_classification():
    result = check(source_authenticated=True)
    assert result is not None
    assert result.status == "authenticated_read_acknowledgment"


def test_rejects_display_name_input_not_bare_address():
    assert check(reported_recipient="Alice <recipient@example.com>") is None


def test_rejects_missing_message_id():
    assert check(expected_original_message_id="") is None
