from pathlib import Path

from app.schemas.platform_mail import PlatformMailboxProvisionRequest


ROOT = Path(__file__).parents[1]
API = ROOT / "app" / "api" / "v1" / "platform_mail.py"
AUTH = ROOT / "app" / "api" / "platform_service_auth.py"
ITHUTE_AUTH = ROOT / "app" / "services" / "ithute_auth.py"
MODELS = ROOT / "app" / "models" / "platform_mail.py"
MIGRATION = ROOT / "alembic" / "versions" / "0023_platform_mail_provisioning.py"
ROUTER = ROOT / "app" / "api" / "v1" / "router.py"


def test_platform_mailbox_request_defaults_to_one_gibibyte() -> None:
    payload = PlatformMailboxProvisionRequest(
        external_reference="2026/001234:official-address",
        domain_name="rsl-business.ls",
        local_part="tjekatjeka",
    )
    assert payload.domain_name == "rsl-business.ls"
    assert payload.quota_bytes == 1024**3


def test_service_tokens_are_separate_from_human_and_legacy_tokens() -> None:
    source = ITHUTE_AUTH.read_text(encoding="utf-8")
    assert "decode_ithute_service_token" in source
    assert 'claims.get("token_use") != "service"' in source
    assert 'claims.get("service_auth") != "managed"' in source
    assert 'audience=audience' in source
    assert 'client_id = str(claims.get("azp")' in source
    assert 'str(claims.get("sub") or "") != f"service:{client_id}"' in source
    assert '"scope"' in source
    assert '"jti"' in source


def test_platform_mail_requires_ithute_mail_scope_and_uses_azp_identity() -> None:
    source = AUTH.read_text(encoding="utf-8")
    assert 'audience: str = "ithute-mail"' in source
    assert "require_platform_service_scope" in source
    assert "required_scope not in scopes" in source
    assert 'client_id=str(claims["azp"])' in source
    assert 'client_id=str(claims["sub"])' not in source


def test_provisioning_is_domain_granted_idempotent_and_credentialless() -> None:
    source = API.read_text(encoding="utf-8")
    for required in (
        'prefix="/platform/mail"',
        'require_platform_service_scope("mailbox.create")',
        "PlatformMailDomainGrant.active.is_(True)",
        "PlatformMailboxBinding.service_client_id == principal.client_id",
        "PlatformMailboxBinding.external_reference == reference",
        "External reference is already bound to another mailbox",
        "internal_password = secrets.token_urlsafe",
        "hash_mailbox_password(internal_password)",
        '"credential_mode": "platform-managed"',
        "sync_mailbox(mailbox)",
        '"/mailboxes/{binding_id}/suspend"',
        '"/mailboxes/{binding_id}/reactivate"',
    ):
        assert required in source
    assert "internal_password" not in (ROOT / "app" / "schemas" / "platform_mail.py").read_text(encoding="utf-8")


def test_platform_mail_models_enforce_service_ownership() -> None:
    source = MODELS.read_text(encoding="utf-8")
    assert "platform_mail_domain_grants" in source
    assert "uq_platform_mail_grant_client_domain" in source
    assert "platform_mailbox_bindings" in source
    assert "uq_platform_mailbox_binding_client_reference" in source
    assert "uq_platform_mailbox_binding_mailbox" in source


def test_migration_extends_current_backend_head() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "0023_platform_mail_provisioning"' in source
    assert 'down_revision = "0022_commercial_catalog"' in source
    assert "platform_mail_domain_grants" in source
    assert "platform_mailbox_bindings" in source


def test_router_mounts_platform_mail_api() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert "platform_mail," in source
    assert "api_router.include_router(platform_mail.router)" in source
