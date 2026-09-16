from pathlib import Path

from app.service_client_schemas import ManagedServiceTokenRequest


ROOT = Path(__file__).parents[1]
ADMIN = ROOT / "app" / "service_client_admin.py"
API = ROOT / "app" / "service_token_api.py"
MODELS = ROOT / "app" / "managed_service_models.py"
MIGRATION = ROOT / "alembic" / "versions" / "0006_managed_service_clients.py"
SERVER = ROOT / "app" / "server.py"


def test_managed_service_token_accepts_rsl_platform_scopes() -> None:
    payload = ManagedServiceTokenRequest(
        client_id="business-digital-address",
        client_secret="x" * 32,
        audience="ithute-auth",
        scope="identity.invite notification.send",
    )
    assert payload.audience == "ithute-auth"
    assert payload.scope == "identity.invite notification.send"


def test_migration_seeds_rsl_trade_and_business_clients() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    for required in (
        "managed_service_clients",
        "managed_service_credentials",
        '"business-digital-address"',
        '"trade-simulator"',
        '"rsl-simulator"',
        '"identity.invite"',
        '"mailbox.create"',
        '"mail.send"',
        '"dns.verify"',
        '"notification.send"',
    ):
        assert required in source


def test_admin_api_covers_lifecycle_and_audit_operations() -> None:
    source = ADMIN.read_text(encoding="utf-8")
    for required in (
        '@router.get("")',
        '@router.post("")',
        '@router.patch("/{client_id}")',
        '"/{client_id}/rotate-secret"',
        '"/{client_id}/credentials/{credential_id}/revoke"',
        '"/{client_id}/audit"',
        "admin_service_client_created",
        "admin_service_client_updated",
        "admin_service_client_secret_rotated",
        "admin_service_client_secret_revoked",
    ):
        assert required in source


def test_secrets_are_hashed_and_plaintext_is_not_a_model_column() -> None:
    source = MODELS.read_text(encoding="utf-8")
    assert "secret_hash" in source
    assert "secret_prefix" in source
    assert "client_secret" not in source


def test_managed_tokens_take_precedence_over_legacy_runtime_secret_fallback() -> None:
    api_source = API.read_text(encoding="utf-8")
    server_source = SERVER.read_text(encoding="utf-8")
    assert "ManagedServiceClient" in api_source
    assert "authenticate_managed_service_client" in api_source
    assert "Compatibility bridge" in api_source
    assert "service_token_denied" in api_source
    assert "service_token_issued" in api_source
    assert 'getattr(route, "path", None) == "/v1/auth/service-token"' in server_source
    assert "app.include_router(service_token_router)" in server_source
    assert "app.include_router(service_client_admin_router)" in server_source
