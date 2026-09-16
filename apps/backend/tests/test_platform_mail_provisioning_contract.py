from pathlib import Path


ROOT = Path(__file__).parents[1]
API = ROOT / "app" / "api" / "v1" / "platform_mail.py"
MODELS = ROOT / "app" / "models" / "mail.py"
AUTH = ROOT / "app" / "services" / "ithute_auth.py"
MIGRATION = ROOT / "alembic" / "versions" / "0023_platform_mail_provisioning.py"
ROUTER = ROOT / "app" / "api" / "v1" / "router.py"
AUTH_ROOT = ROOT.parent.parent / "platform" / "ithute-auth"
AUTH_SCOPE_MIGRATION = AUTH_ROOT / "alembic" / "versions" / "0008_platform_mail_management_scope.py"
MANAGED_TOKEN = AUTH_ROOT / "app" / "managed_service_token.py"
TOKEN_API = AUTH_ROOT / "app" / "service_token_api.py"


def test_platform_mail_api_uses_exact_machine_audience_and_scopes() -> None:
    source = API.read_text(encoding="utf-8")
    assert 'audience="ithute-mail"' in source
    assert '_require_service_scope("mailbox.create")' in source
    assert '_require_service_scope("mailbox.manage")' in source
    assert "created_by_service_client_id=context.client_id" in source


def test_machine_mailbox_secret_is_not_returned_to_calling_service() -> None:
    source = API.read_text(encoding="utf-8")
    assert "generated_secret" in source
    assert "hash_mailbox_password(generated_secret)" in source
    assert "password" not in source.split("class MailboxProvisionResponse", 1)[1].split("def _require_service_scope", 1)[0]


def test_service_clients_are_restricted_to_explicit_domain_bindings() -> None:
    source = API.read_text(encoding="utf-8")
    assert "PlatformMailDomainBinding.service_client_id == client_id" in source
    assert "PlatformMailDomainBinding.domain_id == domain.id" in source
    assert "Service client is not authorized for this mail domain" in source
    assert "allow_manage" in source


def test_provisioning_is_idempotent_by_service_client_and_external_reference() -> None:
    source = MODELS.read_text(encoding="utf-8")
    assert 'UniqueConstraint("service_client_id", "external_reference"' in source
    api = API.read_text(encoding="utf-8")
    assert "External reference is already bound to another mailbox" in api


def test_mail_schema_supports_machine_actor_without_fake_human_user() -> None:
    source = MODELS.read_text(encoding="utf-8")
    assert "created_by_user_id: Mapped[uuid.UUID | None]" in source
    assert "created_by_service_client_id" in source
    migration = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "0023_platform_mail_provisioning"' in migration
    assert 'down_revision = "0022_commercial_catalog"' in migration
    assert '"platform_mail_domain_bindings"' in migration
    assert '"platform_mailbox_provisioning"' in migration


def test_ithute_auth_validates_managed_machine_tokens_separately_from_human_and_legacy_tokens() -> None:
    source = AUTH.read_text(encoding="utf-8")
    assert "def decode_ithute_service_token" in source
    assert 'claims.get("managed_service_client") is not True' in source
    assert "required_scope not in scopes" in source
    managed = MANAGED_TOKEN.read_text(encoding="utf-8")
    token_api = TOKEN_API.read_text(encoding="utf-8")
    assert '"managed_service_client": True' in managed
    assert "create_managed_service_token" in token_api
    assert "create_service_token" in token_api


def test_platform_mail_router_is_mounted() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert "platform_mail," in source
    assert "api_router.include_router(platform_mail.router)" in source


def test_business_digital_address_gets_manage_scope_but_trade_does_not() -> None:
    source = AUTH_SCOPE_MIGRATION.read_text(encoding="utf-8")
    assert '"business-digital-address"' in source
    assert '"mailbox.manage"' in source
    assert '"trade-simulator"' not in source
