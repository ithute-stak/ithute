from pathlib import Path

from app.config import Settings


ROOT = Path(__file__).resolve().parents[1]


def test_legacy_service_secrets_are_disabled_by_default():
    settings = Settings(database_url="sqlite://")
    assert settings.allow_legacy_service_secrets is False
    assert settings.service_credential_max_days == 90


def test_managed_service_tokens_are_bound_to_credential_identity():
    source = (ROOT / "app" / "managed_service_token_security.py").read_text()
    assert '"credential_id": str(credential_id)' in source

    authz = (ROOT / "app" / "service_authorization.py").read_text()
    assert 'ManagedServiceCredential.id == credential_id' in authz
    assert 'ManagedServiceCredential.revoked_at.is_(None)' in authz
    assert 'service credential revoked' in authz


def test_new_managed_service_credentials_have_bounded_lifetime():
    source = (ROOT / "app" / "service_client_admin.py").read_text()
    assert 'service_credential_max_days' in source
    assert 'service credential lifetime cannot exceed' in source
    assert '_credential_expiry(payload.expires_at, settings)' in source
