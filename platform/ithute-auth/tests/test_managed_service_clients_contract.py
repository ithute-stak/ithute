from pathlib import Path

from app.service_client_schemas import ManagedServiceTokenRequest


ROOT = Path(__file__).parents[1]
ADMIN = ROOT / "app" / "service_client_admin.py"
API = ROOT / "app" / "service_token_api.py"
MANAGED_TOKEN = ROOT / "app" / "managed_service_token_security.py"
MODELS = ROOT / "app" / "managed_service_models.py"
SERVICE_CLIENTS = ROOT / "app" / "service_clients.py"
MIGRATION = ROOT / "alembic" / "versions" / "0006_managed_service_clients.py"
BDA_GRANTS_MIGRATION = ROOT / "alembic" / "versions" / "0008_bda_service_grants.py"
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


def test_bda_integration_grants_are_least_privilege_and_migration_safe() -> None:
    source = BDA_GRANTS_MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "0008_bda_service_grants"' in source
    assert 'down_revision = "0007_identity_invites"' in source
    assert len("0008_bda_service_grants") <= 32
    assert '"trade-simulator"' in source
    assert '"rsl-simulator"' in source
    assert source.count('"audience": "business-digital-address"') == 2
    assert '"scope": "business.register"' in source
    assert '"scope": "official-message.send"' in source
    assert "identity.invite" not in source
    assert "mailbox.create" not in source
    assert "mail.send" not in source
    assert "notification.send" not in source


def test_admin_api_covers_lifecycle_and_audit_operations() -> None:
    source = ADMIN.read_text(encoding="utf-8")
    for required in (
        '@router.get(""',
        '@router.post(""',
        '@router.patch("/{client_id}"',
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


def test_machine_authentication_happens_before_scope_authorization() -> None:
    source = SERVICE_CLIENTS.read_text(encoding="utf-8")
    credential_lookup = source.index("ManagedServiceCredential.secret_hash == hash_service_secret(client_secret)")
    audience_check = source.index("allowed_audiences = set(decode_capabilities")
    scope_check = source.index("allowed_scopes = set(decode_capabilities")
    assert credential_lookup < audience_check < scope_check
    assert source.count('ServiceClientAuthError(401, "invalid service credentials")') >= 4


def test_managed_tokens_are_cryptographically_distinguishable_from_legacy_tokens() -> None:
    api_source = API.read_text(encoding="utf-8")
    token_source = MANAGED_TOKEN.read_text(encoding="utf-8")
    assert "create_managed_service_token" in api_source
    assert '"service_auth": "managed"' in token_source
    assert '"azp": client_id' in token_source
    assert '"sub": f"service:{client_id}"' in token_source
    assert "create_service_token(" in api_source
    managed_call = api_source.index("create_managed_service_token(")
    legacy_call = api_source.rindex("create_service_token(")
    assert managed_call < legacy_call


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
