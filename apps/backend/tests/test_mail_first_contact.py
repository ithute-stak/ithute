from app.services.mail_first_contact import (
    FirstContactPlan,
    decorate_first_contact_html,
    decorate_first_contact_text,
)


def _plan(*, badge=True, authenticated=True):
    return FirstContactPlan(
        first_contact_recipients=("new@example.com",),
        established_recipients=(),
        visible_badge=badge,
        sender_domain_verified=authenticated,
        dkim_configured=authenticated,
    )


def test_verified_first_contact_badge_is_security_claim_not_safety_claim():
    plan = _plan()
    text = decorate_first_contact_text("Hello", plan)
    html = decorate_first_contact_html("<p>Hello</p>", plan)

    assert "Ithute Verified First Contact" in text
    assert "Sender domain authenticated by Ithute" in text
    assert "does not guarantee that message content is safe" in text
    assert "Ithute Verified First Contact" in html
    assert "does not guarantee that message content is safe" in html
    assert plan.public_dict()["claims_message_safe"] is False
    assert plan.public_dict()["separate_advert_sent"] is False


def test_badge_is_suppressed_for_mixed_or_established_visible_recipients():
    plan = _plan(badge=False)
    assert decorate_first_contact_text("Hello", plan) == "Hello"
    assert decorate_first_contact_html("<p>Hello</p>", plan) == "<p>Hello</p>"


def test_unverified_domain_does_not_claim_domain_authentication():
    plan = _plan(authenticated=False)
    text = decorate_first_contact_text("Hello", plan)
    assert "Sender domain authenticated by Ithute" not in text
    assert "Sender identity is managed by Ithute Mail" in text
