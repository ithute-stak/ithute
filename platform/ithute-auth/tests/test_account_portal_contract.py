from pathlib import Path


PORTAL = Path(__file__).parents[1] / "app" / "portal.py"


def _source() -> str:
    return PORTAL.read_text(encoding="utf-8")


def test_account_portal_keeps_security_routes_and_csrf_contract() -> None:
    source = _source()
    for route in (
        '/account/password/change',
        '/account/verification/request',
        '/account/verification/confirm',
        '/account/mfa/start',
        '/account/mfa/confirm',
        '/account/mfa/recovery-codes',
        '/account/mfa/disable',
        '/account/sessions/{session_id}/revoke',
        '/account/sessions/revoke-all',
    ):
        assert route in source
    assert "_require_csrf(request, csrf_token, settings)" in source
    assert "revoke_sessions(db, user_id=user.id" in source


def test_account_portal_requires_password_confirmation() -> None:
    source = _source()
    assert "confirm_new_password: str = Form(...)" in source
    assert 'detail="new passwords do not match"' in source


def test_account_portal_distinguishes_missing_from_unverified_contacts() -> None:
    source = _source()
    assert 'return \'<span class="badge neutral">Not set</span>\'' in source
    assert "Verification needed" in source
    assert "available_channels" in source


def test_account_portal_exposes_security_navigation_and_session_controls() -> None:
    source = _source()
    assert 'href="/account/passkeys"' in source
    assert "Product sessions" in source
    assert "Security activity" in source
    assert "Sign out everywhere" in source
    assert "Review passkeys" in source


def test_login_screen_explains_central_identity_and_mfa_setup() -> None:
    source = _source()
    assert "One identity, separate product permissions" in source
    assert "Where do I get the authenticator or recovery code?" in source
    assert "If you never enabled MFA" in source
    assert "How to enable MFA" in source
    assert "Account → Multi-factor authentication" in source
    assert "Set up authenticator" in source
    assert "Ithute will then show one-time recovery codes" in source


def test_account_portal_exposes_secure_recovery_code_regeneration() -> None:
    source = _source()
    assert 'action="/account/mfa/recovery-codes"' in source
    assert "Regenerate recovery codes" in source
    assert "All previous recovery codes will stop working" in source
    assert 'password: str = Form(...)' in source
    assert 'code: str = Form(...)' in source
    assert 'event_type="mfa_recovery_codes_regenerated"' in source
    assert "db.execute(delete(MfaRecoveryCode)" in source
    assert "new_recovery_codes()" in source
    assert "Your previous recovery codes are now invalid" in source
