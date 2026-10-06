from app.services.mail_intelligence import analyze_mail_message


def _message(**overrides):
    payload = {
        "from": "Alice <alice@example.com>",
        "to": "user@ithute.co.ls",
        "cc": "",
        "reply_to": "",
        "subject": "Monthly update",
        "body_text": "Hello, here is the monthly update for your records.",
        "attachments": [],
    }
    payload.update(overrides)
    return payload


def test_normal_business_message_stays_low_risk():
    result = analyze_mail_message(_message(), mailbox_address="user@ithute.co.ls")

    assert result["security"]["phishing_probability"] < 0.30
    assert result["security"]["bec_probability"] < 0.30
    assert result["security"]["recommended_action"] == "allow"
    assert result["governance"]["automatic_blocking"] is False
    assert result["governance"]["training_use"] is False


def test_reply_to_domain_mismatch_is_explained():
    result = analyze_mail_message(
        _message(
            reply_to="payments@lookalike.invalid",
            subject="Urgent payment",
            body_text="Please make the payment today.",
        ),
        mailbox_address="user@ithute.co.ls",
    )

    names = {signal["signal"] for signal in result["security"]["signals"]}
    assert "reply_to_domain_mismatch" in names
    assert result["security"]["bec_probability"] > 0.30


def test_bank_change_request_scores_as_bec_risk():
    result = analyze_mail_message(
        _message(
            subject="URGENT: new bank details",
            body_text="Please change account and transfer payment to our new bank account immediately.",
        )
    )

    assert result["security"]["bec_probability"] >= 0.55
    assert result["business"]["intent"]["label"] == "payment"
    assert result["security"]["recommended_action"] in {"review", "warn_and_verify"}


def test_risky_attachment_is_reported():
    result = analyze_mail_message(
        _message(
            attachments=[
                {"filename": "invoice.pdf", "content_type": "application/pdf"},
                {"filename": "payment-update.exe", "content_type": "application/octet-stream"},
            ]
        )
    )

    signal = next(item for item in result["security"]["signals"] if item["signal"] == "risky_attachment_type")
    assert "payment-update.exe" in signal["evidence"]


def test_business_entities_and_deadline_are_extracted():
    result = analyze_mail_message(
        _message(
            subject="Quotation INV-2026-104",
            body_text="Please send the quotation by tomorrow. Budget is M14,500.00 and meeting is 2026-10-09.",
        )
    )

    entities = result["business"]["entities"]
    assert "M14,500.00" in entities["money"]
    assert "2026-10-09" in entities["dates"]
    assert "tomorrow" in entities["deadline_terms"]
    assert result["business"]["reply_needed"] is True
    assert result["business"]["intent"]["label"] == "quotation"


def test_external_link_domain_is_visible_in_evidence():
    result = analyze_mail_message(
        _message(
            body_text="Please review https://evil.example.net/verify before today.",
        )
    )

    signal = next(item for item in result["security"]["signals"] if item["signal"] == "external_link_domain")
    assert "evil.example.net" in signal["evidence"]


def test_question_marks_message_as_reply_needed():
    result = analyze_mail_message(
        _message(body_text="Can you confirm whether the service is available?")
    )

    assert result["business"]["reply_needed"] is True
    assert result["business"]["reply_evidence"]["question_mark"] is True


def test_internal_mail_is_not_blindly_trusted():
    result = analyze_mail_message(
        _message(
            from="Boss <boss@ithute.co.ls>",
            subject="Urgent verify your account",
            body_text="Verify your account password immediately.",
        ),
        mailbox_address="user@ithute.co.ls",
    )

    assert result["security"]["phishing_probability"] > 0.10
    assert any(signal["signal"] == "credential_request" for signal in result["security"]["signals"])
