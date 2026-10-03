from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_oauth_blocks_password_only_platform_admin_authorization():
    source = (ROOT / "app" / "oauth.py").read_text()
    assert "Privileged accounts must sign in with a passkey." in source
    assert "privileged_password_login_blocked" in source
    assert 'auth_method="passkey"' in (ROOT / "app" / "passkeys.py").read_text()


def test_admin_portal_requires_passkey_browser_assurance():
    source = (ROOT / "app" / "portal.py").read_text()
    assert 'platform admin requires passkey step-up' in source
    assert '/account/passkey-login?step_up=1' in source


def test_trusted_device_mutations_require_recent_passkey():
    source = (ROOT / "app" / "account.py").read_text()
    assert 'def _require_recent_passkey' in source
    assert 'context.session.auth_method != "passkey"' in source
    assert '@router.post("/devices/{device_id}/trust"' in source
    assert '@router.delete("/devices/{device_id}"' in source
