from email.message import EmailMessage

from app.api.v1.webmail_content import _html_body


def _raw_html(body: str) -> bytes:
    message = EmailMessage()
    message["From"] = "sender@example.com"
    message["To"] = "user@example.com"
    message["Subject"] = "Verify account"
    message.set_content("Plain fallback")
    message.add_alternative(body, subtype="html")
    return message.as_bytes()


def test_remote_image_button_keeps_safe_alt_text_and_link() -> None:
    raw = _raw_html(
        '<p>Please verify below.</p>'
        '<a href="https://example.com/verify?token=abc">'
        '<img src="https://tracker.example/pixel-button.png" alt="Verify email address">'
        '</a>'
    )
    safe, has_html, blocked = _html_body(raw)

    assert has_html is True
    assert blocked == 1
    assert 'href="https://example.com/verify?token=abc"' in safe
    assert "Verify email address" in safe
    assert "<img" not in safe


def test_empty_safe_action_anchor_gets_visible_fallback_label() -> None:
    raw = _raw_html(
        '<p>Continue:</p>'
        '<a href="https://example.com/verify?token=abc"><img src="https://tracker.example/button.png"></a>'
    )
    safe, has_html, blocked = _html_body(raw)

    assert has_html is True
    assert blocked == 1
    assert 'href="https://example.com/verify?token=abc"' in safe
    assert "Open secure link" in safe
    assert "<img" not in safe


def test_javascript_links_remain_blocked() -> None:
    raw = _raw_html('<a href="javascript:alert(1)">Bad link</a>')
    safe, _, _ = _html_body(raw)

    assert "javascript:" not in safe
    assert "Bad link" in safe
