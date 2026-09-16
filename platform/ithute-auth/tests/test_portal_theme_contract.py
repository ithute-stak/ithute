from pathlib import Path


THEME = Path(__file__).parents[1] / "app" / "portal_theme.py"
MAIN = Path(__file__).parents[1] / "app" / "main.py"


def _theme_source() -> str:
    return THEME.read_text(encoding="utf-8")


def test_auth_theme_keeps_approved_brand_and_mfa_guidance() -> None:
    source = _theme_source()
    for required in (
        "Ithute Auth",
        "Secure Access. A Brighter Tomorrow.",
        "One identity. Total control.",
        "for a brighter Lesotho",
        "Where do I get the authenticator or recovery code?",
        "How to enable MFA",
        "Account → Multi-factor authentication",
        "Use a passkey",
        "Forgot password?",
        "#1475d1",
        "#249716",
    ):
        assert required in source


def test_auth_theme_preserves_login_field_contract() -> None:
    source = _theme_source()
    assert 'action="/account/login"' in source
    assert 'name="csrf_token"' in source
    assert 'name="identifier"' in source
    assert 'name="password"' in source
    assert 'name="mfa_code"' in source


def test_main_applies_auth_theme_before_router_registration() -> None:
    source = MAIN.read_text(encoding="utf-8")
    assert "from .portal_theme import apply_portal_theme" in source
    assert source.index("apply_portal_theme()") < source.index("app.include_router(portal_router)")
