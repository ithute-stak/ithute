from pathlib import Path


def test_http_security_headers_remain_enabled() -> None:
    source = (Path(__file__).parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    for header in (
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
        "Permissions-Policy",
        "Content-Security-Policy",
        "Cache-Control",
        "Strict-Transport-Security",
    ):
        assert header in source
    assert "no-store" in source
    assert "frame-ancestors 'none'" in source


def test_login_exposes_recovery_and_passkey_paths() -> None:
    source = (Path(__file__).parents[1] / "app" / "portal.py").read_text(encoding="utf-8")
    assert 'href="/forgot-password"' in source
    assert 'href="/account/passkey-login"' in source


def test_api_and_portal_throttle_verification_code_guesses() -> None:
    account_source = (Path(__file__).parents[1] / "app" / "account.py").read_text(encoding="utf-8")
    portal_source = (Path(__file__).parents[1] / "app" / "portal.py").read_text(encoding="utf-8")
    for source in (account_source, portal_source):
        assert "verification_confirmation_rate_limited" in source
        assert "verification_failed" in source
        assert "too many verification attempts" in source
