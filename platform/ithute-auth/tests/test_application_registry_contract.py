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


def test_app_activation_requires_approved_redirects():
    source = (ROOT / "app/admin.py").read_text()
    assert 'if payload.is_active is True:' in source
    assert 'ApplicationRedirectURI.application_id == application.id' in source
    assert 'Register at least one approved callback URL before activation' in source


def test_online_session_endpoint_checks_client_activation():
    source = (ROOT / "app/account.py").read_text()
    assert '@router.get("/session-status")' in source
    assert "Depends(authenticated_context)" in source
    assert "Application.is_active" in source
    sdk = (ROOT.parent.parent / "packages/ithute-auth-nextjs/src/index.ts").read_text()
    assert "/v1/account/session-status" in sdk
    assert 'cache: "no-store"' in sdk
    assert "if (!active.ok) return null" in sdk


def test_current_session_revocation_route_is_authenticated():
    source = (ROOT / "app/account.py").read_text()
    assert '@router.post("/sessions/revoke-current", status_code=204)' in source
    assert "def revoke_current_session(" in source
    assert "context.session.revoked_at = utcnow()" in source
    assert "context: AuthContext = Depends(authenticated_context)" in source
