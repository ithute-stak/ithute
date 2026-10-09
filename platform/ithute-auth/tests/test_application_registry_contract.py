"""OAuth callback safety: the DB allowlist is authoritative when present."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OAUTH = (ROOT / "app/oauth.py").read_text()
REGISTRY = (ROOT / "app/application_registry.py").read_text()
MODELS = (ROOT / "app/models.py").read_text()


def test_exact_db_redirect_enforcement_precedes_legacy_fallback():
    segment = OAUTH.split("def _require_client_redirect(", 1)[1].split("def _validate_authorization_request(", 1)[0]
    assert "ApplicationRedirectURI.application_id == client.id" in segment
    assert "approved = managed if managed else settings.redirect_uris.get(client_id, ())" in segment
    assert "redirect_uri not in approved" in segment


def test_registration_is_inactive_and_has_unique_callbacks():
    assert "is_active=False" in REGISTRY
    assert "validate_redirect_uris(redirect_uris)" in REGISTRY
    assert 'UniqueConstraint("application_id", "redirect_uri"' in MODELS
