from app.oauth import _login_html


def _fields() -> dict[str, str]:
    return {
        "response_type": "code",
        "client_id": "nbros",
        "redirect_uri": "https://nbro.ithute.co.ls/api/auth/oidc/callback",
        "code_challenge": "x" * 43,
        "code_challenge_method": "S256",
        "state": "state-value",
        "nonce": "nonce-value-123456",
        "scope": "openid profile email phone",
    }


def test_login_form_renders_friendly_error_without_echoing_password() -> None:
    rendered = _login_html(
        _fields(),
        identifier="justy@ithute.co.ls",
        error="The email or password is incorrect.",
    )

    assert 'value="justy@ithute.co.ls"' in rendered
    assert 'role="alert"' in rendered
    assert "The email or password is incorrect." in rendered
    assert 'type="password"' in rendered
    assert 'name="password"' in rendered
    assert 'autocomplete="current-password"' in rendered
    assert "Ithute Digital Solutions" in rendered
    assert "Protected sign-in" in rendered
    assert "#123a38" in rendered
    assert "#d8c56a" in rendered
    assert "#790d29" not in rendered


def test_login_form_preserves_oauth_fields_and_html_escapes_values() -> None:
    rendered = _login_html(
        _fields(),
        identifier='person@example.com"><script>alert(1)</script>',
        error='<script>alert("error")</script>',
    )

    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "&quot;&gt;&lt;script&gt;" in rendered
    for name in _fields():
        assert f'name="{name}"' in rendered
