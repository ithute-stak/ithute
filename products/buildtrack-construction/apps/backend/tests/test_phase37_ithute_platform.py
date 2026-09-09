from pathlib import Path

from app.core.config import Settings


BACKEND = Path(__file__).resolve().parents[1]
PRODUCT = BACKEND.parents[1]
REPO = PRODUCT.parents[1]


def test_phase37_central_identity_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.auth_audience == "buildtrack-construction"
    assert settings.auth_issuer == "https://auth.ithute.co.ls"
    assert settings.superadmin_email == "justy@ithute.co.ls"


def test_phase37_migration_links_stable_auth_subject() -> None:
    migration = (BACKEND / "alembic/versions/0037_phase37_ithute_identity.py").read_text()
    assert 'down_revision = "0036_phase35_automation"' in migration
    assert '"auth_user_id"' in migration
    assert '"uq_user_auth_user_id"' in migration


def test_production_disables_second_password_system() -> None:
    compose = (REPO / "docker-compose.buildtrack.yml").read_text()
    assert 'AUTH_AUDIENCE: buildtrack-construction' in compose
    assert 'LEGACY_AUTH_ENABLED: "false"' in compose
    assert 'SUPERADMIN_EMAIL: ${ITHUTE_BUILDTRACK_SUPERADMIN_EMAIL:-justy@ithute.co.ls}' in compose
    assert 'command: ["python", "-m", "scripts.bootstrap_production"]' in compose


def test_frontend_public_vendor_and_manual_routes_are_not_session_gated() -> None:
    proxy = (PRODUCT / "apps/frontend/proxy.ts").read_text()
    assert '"/index"' in proxy
    assert '"/documentation"' in proxy
    assert 'pathname.startsWith("/vendor-submissions/")' in proxy


def test_edge_contains_nthane_hostname() -> None:
    edge = (REPO / "infrastructure/ithute-edge/default.conf.template").read_text()
    assert "server_name nbro.ithute.co.ls;" in edge
    assert "buildtrack-backend:8000" in edge
    assert "buildtrack-frontend:3000" in edge
