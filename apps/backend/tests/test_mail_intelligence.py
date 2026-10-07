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



def test_mail_authentication_failures_raise_risk():
    result = analyze_mail_message(
        _message(
            authentication_results="mx.example; spf=fail smtp.mailfrom=evil.example; dkim=fail; dmarc=fail",
            received_spf="fail (example)",
        )
    )

    signal = next(item for item in result["security"]["signals"] if item["signal"] == "mail_authentication_failure")
    assert set(signal["evidence"]) == {"spf", "dkim", "dmarc"}
    assert result["security"]["phishing_probability"] >= 0.4



def test_verified_ithute_password_reset_is_classified_as_account_recovery():
    result = analyze_mail_message(
        _message(
            from="Ithute Security <auth@ithute.co.ls>",
            subject="Reset your Ithute password",
            body_text="Open https://ithute.co.ls/reset-password#token=abc to choose a new password.",
            authentication_results=(
                "mx.ithute.co.ls; spf=pass smtp.mailfrom=ithute.co.ls; "
                "dkim=pass header.d=ithute.co.ls; dmarc=pass header.from=ithute.co.ls"
            ),
            received_spf="pass (authorized)",
        ),
        mailbox_address="user@ithute.co.ls",
    )

    assert result["trust"]["verified"] is True
    assert result["business"]["intent"]["label"] == "account_recovery"
    assert result["business"]["reply_needed"] is False
    assert result["security"]["recommended_action"] == "allow"
    assert result["security"]["phishing_probability"] < 0.10
    assert "Verified Ithute Identity & Account Security message" in result["business"]["summary"]


def test_spoofed_registered_sender_is_more_suspicious_not_more_trusted():
    result = analyze_mail_message(
        _message(
            from="Ithute Security <auth@ithute.co.ls>",
            subject="Reset your Ithute password",
            body_text="Open https://evil.example/reset-password now.",
            authentication_results="mx; spf=fail; dkim=fail; dmarc=fail",
            received_spf="fail (not authorized)",
        )
    )

    names = {signal["signal"] for signal in result["security"]["signals"]}
    assert result["trust"]["verified"] is False
    assert result["trust"]["state"] == "registry_sender_auth_failed"
    assert "registered_sender_authentication_mismatch" in names
    assert result["security"]["phishing_probability"] >= 0.55



def test_verified_tenant_registry_sender_gets_bounded_trust_credit():
    result = analyze_mail_message(
        _message(
            from="Alerts <alerts@partner.example>",
            subject="Account update",
            body_text="Review https://secure.partner.example/account today.",
            authentication_results="mx; spf=pass; dkim=pass; dmarc=pass",
            received_spf="pass",
        ),
        mailbox_address="user@ithute.co.ls",
        trusted_sender_registry=[{
            "name": "Example Partner",
            "category": "business_partner",
            "sender_domains": ["partner.example"],
            "allowed_link_domains": ["partner.example"],
            "require_spf": True,
            "require_dkim": True,
            "require_dmarc": True,
        }],
    )

    assert result["trust"]["verified"] is True
    assert result["trust"]["registry_source"] == "tenant_registry"
    assert result["trust"]["explainable_score"]["verified_trust_credit"] == 28
    assert result["security"]["recommended_action"] == "allow"


def test_registry_sender_with_unapproved_link_is_not_verified():
    result = analyze_mail_message(
        _message(
            from="Alerts <alerts@partner.example>",
            body_text="Review https://outside.example/account immediately.",
            authentication_results="mx; spf=pass; dkim=pass; dmarc=pass",
            received_spf="pass",
        ),
        trusted_sender_registry=[{
            "name": "Example Partner",
            "category": "business_partner",
            "sender_domains": ["partner.example"],
            "allowed_link_domains": ["partner.example"],
            "require_spf": True,
            "require_dkim": True,
            "require_dmarc": True,
        }],
    )

    assert result["trust"]["verified"] is False
    assert result["trust"]["url_intelligence"]["suspicious_count"] == 1
    assert result["trust"]["explainable_score"]["verified_trust_credit"] == 0



def test_poor_reputation_amplifies_message_risk():
    result = analyze_mail_message(
        _message(subject="Routine notice", body_text="Please review this notice."),
        reputation={
            "available": True,
            "combined_score": 20,
            "confidence": 0.8,
            "risk_adjustment": 20,
            "sender": {"state": "poor"},
            "domain": {"state": "watch"},
        },
    )

    assert result["reputation"]["applied_risk_adjustment"] == 20
    assert any(signal["signal"] == "sender_reputation_risk" for signal in result["security"]["signals"])
    assert result["security"]["phishing_probability"] >= 0.20


def test_strong_reputation_credit_is_suppressed_by_current_auth_failure():
    result = analyze_mail_message(
        _message(
            subject="Routine notice",
            body_text="Please review this notice.",
            authentication_results="mx; spf=fail; dkim=fail; dmarc=fail",
            received_spf="fail",
        ),
        reputation={
            "available": True,
            "combined_score": 95,
            "confidence": 0.9,
            "risk_adjustment": -10,
            "sender": {"state": "strong"},
            "domain": {"state": "strong"},
        },
    )

    assert result["reputation"]["requested_risk_adjustment"] == -10
    assert result["reputation"]["applied_risk_adjustment"] == 0
    assert result["reputation"]["negative_credit_suppressed"] is True
    assert any(signal["signal"] == "mail_authentication_failure" for signal in result["security"]["signals"])


def test_strong_reputation_can_reduce_only_generic_risk():
    result = analyze_mail_message(
        _message(subject="Monthly update", body_text="Here is the monthly update."),
        reputation={
            "available": True,
            "combined_score": 90,
            "confidence": 0.85,
            "risk_adjustment": -10,
            "sender": {"state": "strong"},
            "domain": {"state": "strong"},
        },
    )

    assert result["reputation"]["applied_risk_adjustment"] == -10
    assert result["reputation"]["negative_credit_suppressed"] is False
    assert any(signal["signal"] == "sender_reputation_credit" for signal in result["security"]["signals"])
