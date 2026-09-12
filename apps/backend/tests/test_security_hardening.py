import json

import pytest

from app.api.v1.webmail import _safe_attachment_name
from app.services.security_audit import assert_redacted_metadata
from app.services.webmail_polish import sanitize_html


def test_sanitize_html_strips_active_content_and_event_handlers():
    raw = '<p onclick="steal()">Hello<script>alert(1)</script><a href="javascript:alert(1)">bad</a><img src="https://tracker.example/pixel">ok</p>'
    safe = sanitize_html(raw)
    lowered = safe.lower()
    assert '<script' not in lowered
    assert 'onclick' not in lowered
    assert 'javascript:' not in lowered
    assert '<img' not in lowered
    assert 'hello' in lowered
    assert 'ok' in lowered


def test_sanitize_html_allows_safe_links_only():
    safe = sanitize_html('<a href="https://example.test/a">web</a><a href="mailto:user@example.test">mail</a>')
    assert 'https://example.test/a' in safe
    assert 'mailto:user@example.test' in safe


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        ('../../etc/passwd', '_.._etc_passwd'),
        ('..\\..\\evil.html', '_.._evil.html'),
        ('report\r\nX-Evil: yes.pdf', 'report X-Evil: yes.pdf'),
        ('', 'attachment.bin'),
    ],
)
def test_attachment_filename_is_path_and_header_safe(value, expected):
    assert _safe_attachment_name(value) == expected


def test_security_audit_redaction_helper_rejects_secret_values():
    metadata = json.dumps({'client_ip': '127.0.0.1', 'outcome': 'failed'})
    assert_redacted_metadata(metadata, ['password-that-is-not-present', 'session-token-not-present'])
    with pytest.raises(ValueError):
        assert_redacted_metadata('{"note":"super-secret-password"}', ['super-secret-password'])
