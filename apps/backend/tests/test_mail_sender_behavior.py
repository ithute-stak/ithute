from app.services.mail_sender_behavior import (
    analyze_behavior,
    empty_profile,
    updated_profile,
)


def _message(**overrides):
    row = {
        "message_id": "<msg-1@example.com>",
        "from": "Supplier <billing@supplier.example>",
        "reply_to": "billing@supplier.example",
        "date": "Tue, 6 Oct 2026 10:00:00 +0000",
        "subject": "Monthly statement",
        "body_text": "Please find the monthly statement.",
        "attachments": [],
    }
    row.update(overrides)
    return row


def test_first_seen_sender_is_visible_but_low_confidence():
    result = analyze_behavior(_message(), empty_profile())

    assert result["state"] == "watch"
    assert any(item["signal"] == "first_seen_sender" for item in result["signals"])
    assert result["confidence"] < 0.5


def test_changed_reply_domain_is_high_weight_anomaly():
    profile = {
        "observations": 15,
        "hours": {"10": 15},
        "reply_domains": ["supplier.example"],
        "attachment_messages": 3,
        "payment_messages": 4,
        "recent_message_refs": [],
    }
    result = analyze_behavior(
        _message(reply_to="payments@lookalike.invalid"),
        profile,
    )

    signal = next(item for item in result["signals"] if item["signal"] == "sender_reply_domain_changed")
    assert signal["weight"] == 24


def test_new_payment_pattern_is_detected_after_stable_history():
    profile = {
        "observations": 20,
        "hours": {"10": 20},
        "reply_domains": ["supplier.example"],
        "attachment_messages": 2,
        "payment_messages": 0,
        "recent_message_refs": [],
    }
    result = analyze_behavior(
        _message(subject="Urgent bank details", body_text="Please transfer payment to this bank account."),
        profile,
    )

    assert any(item["signal"] == "new_payment_request_pattern" for item in result["signals"])


def test_profile_update_is_idempotent_for_same_message():
    message = _message()
    first = updated_profile(message, empty_profile(), message_ref="<same@example>")
    second = updated_profile(message, first, message_ref="<same@example>")

    assert second["observations"] == first["observations"]
    assert second["recent_message_refs"] == first["recent_message_refs"]


def test_behavior_profile_never_contains_raw_body():
    message = _message(body_text="private body contents")
    profile = updated_profile(message, empty_profile(), message_ref="<private@example>")

    assert "private body contents" not in str(profile)
