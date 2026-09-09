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
    assert settings.product_admin_email_list == ["justy@ithute.co.ls", "just@ithute.co.ls"]


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
    assert 'PRODUCT_ADMIN_EMAILS: ${ITHUTE_BUILDTRACK_PRODUCT_ADMIN_EMAILS:-justy@ithute.co.ls,just@ithute.co.ls}' in compose
    assert 'python -m scripts.bootstrap_production && python -m scripts.provision_central_admin' in compose


def test_central_admin_bootstrap_never_contains_a_human_password() -> None:
    provision = (BACKEND / "scripts/provision_central_admin.py").read_text()
    assert 'DEFAULT_ADMIN_EMAIL = "just@ithute.co.ls"' in provision
    assert "secrets.token_urlsafe(48)" in provision
    assert 'f"{base}/v1/users/register"' in provision
    assert 'f"{base}/v1/account/password/reset/request"' in provision
    assert "secure password setup instructions requested" in provision
    assert "no credential was changed" in provision


def test_production_admin_bootstrap_is_multi_identity_and_idempotent() -> None:
    bootstrap = (BACKEND / "scripts/bootstrap_production.py").read_text()
    sync = (REPO / "scripts/buildtrack-sync-env.py").read_text()
    assert "settings.product_admin_email_list" in bootstrap
    assert 'PRODUCT_ADMIN_EMAILS = "justy@ithute.co.ls,just@ithute.co.ls"' in sync
    assert '"ITHUTE_BUILDTRACK_PRODUCT_ADMIN_EMAILS": PRODUCT_ADMIN_EMAILS' in sync


def test_production_cert_discovery_accepts_current_certbot_inventory_format() -> None:
    deploy = (REPO / "scripts/buildtrack-deploy.sh").read_text()
    assert "Certificate Name:" in deploy
    assert "(Domains|Identifiers)" in deploy
    assert 'certbot_domains()' in deploy
    assert 'Shared TLS certificate includes ${PRODUCT_HOST}.' in deploy


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
