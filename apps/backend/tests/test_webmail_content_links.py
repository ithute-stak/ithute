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
    safe, has_html, blocked, total = _html_body(raw)

    assert has_html is True
    assert blocked == 1
    assert total == 1
    assert 'href="https://example.com/verify?token=abc"' in safe
    assert "Verify email address" in safe
    assert "<img" not in safe


def test_empty_safe_action_anchor_gets_visible_fallback_label() -> None:
    raw = _raw_html(
        '<p>Continue:</p>'
        '<a href="https://example.com/verify?token=abc"><img src="https://tracker.example/button.png"></a>'
    )
    safe, has_html, blocked, total = _html_body(raw)

    assert has_html is True
    assert blocked == 1
    assert total == 1
    assert 'href="https://example.com/verify?token=abc"' in safe
    assert "Open secure link" in safe
    assert "<img" not in safe


def test_remote_images_are_retained_only_after_explicit_opt_in() -> None:
    raw = _raw_html(
        '<div style="background-color:#123456;padding:18px">'
        '<img src="https://cdn.example.com/banner.png" alt="Welcome" width="640">'
        '</div>'
    )
    blocked_html, _, blocked, total = _html_body(raw)
    shown_html, _, shown_blocked, shown_total = _html_body(raw, show_images=True)

    assert blocked == 1
    assert total == 1
    assert "<img" not in blocked_html
    assert "Welcome" in blocked_html

    assert shown_blocked == 0
    assert shown_total == 1
    assert 'src="https://cdn.example.com/banner.png"' in shown_html
    assert 'width="640"' in shown_html


def test_safe_email_layout_styles_survive_but_url_css_does_not() -> None:
    raw = _raw_html(
        '<table style="width:100%;background-color:#ffffff">'
        '<tr><td style="padding:16px;color:#223344;background-image:url(https://tracker.example/bg.png)">Hello</td></tr>'
        '</table>'
    )
    safe, _, _, _ = _html_body(raw)

    assert "width:100%" in safe.replace(" ", "")
    assert "background-color:#ffffff" in safe.replace(" ", "")
    assert "padding:16px" in safe.replace(" ", "")
    assert "color:#223344" in safe.replace(" ", "")
    assert "background-image" not in safe
    assert "tracker.example" not in safe


def test_javascript_links_remain_blocked() -> None:
    raw = _raw_html('<a href="javascript:alert(1)">Bad link</a>')
    safe, _, _, _ = _html_body(raw)

    assert "javascript:" not in safe
    assert "Bad link" in safe
