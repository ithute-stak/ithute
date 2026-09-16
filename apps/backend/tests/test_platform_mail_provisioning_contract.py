from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.platform_mail import (
    PlatformMailDomainGrantCreate,
    PlatformMailSendRequest,
    PlatformMailboxForwardingRequest,
    PlatformMailboxProvisionRequest,
)


ROOT = Path(__file__).parents[1]
REPO = ROOT.parents[1]
API = ROOT / "app" / "api" / "v1" / "platform_mail.py"
FORWARDING_API = ROOT / "app" / "api" / "v1" / "platform_mail_forwarding.py"
AUTH = ROOT / "app" / "api" / "platform_service_auth.py"
ITHUTE_AUTH = ROOT / "app" / "services" / "ithute_auth.py"
ACCOUNT_SYNC = ROOT / "app" / "services" / "mail_account_sync.py"
MODELS = ROOT / "app" / "models" / "platform_mail.py"
MIGRATION = ROOT / "alembic" / "versions" / "0023_platform_mail_provisioning.py"
NAMESPACE_MIGRATION = ROOT / "alembic" / "versions" / "0024_platform_mail_namespace_grants.py"
SEND_MIGRATION = ROOT / "alembic" / "versions" / "0025_platform_mail_send.py"
FORWARDING_MIGRATION = ROOT / "alembic" / "versions" / "0026_platform_mail_inbound_forwarding.py"
ROUTER = ROOT / "app" / "api" / "v1" / "router.py"
BOOTSTRAP_MAIL = REPO / "scripts" / "bootstrap-mail.sh"
MAIL_COMPOSE = REPO / "mail" / "compose.yml"


def test_platform_mailbox_request_defaults_to_one_gibibyte() -> None:
    payload = PlatformMailboxProvisionRequest(
        external_reference="2026/001234:official-address",
        domain_name="rsl-business.ls",
        local_part="bda-tjekatjeka",
    )
    assert payload.domain_name == "rsl-business.ls"
    assert payload.quota_bytes == 1024**3


def test_domain_grant_requires_explicit_reserved_namespace_prefix() -> None:
    payload = PlatformMailDomainGrantCreate(
        service_client_id="business-digital-address",
        domain_name="ithute.co.ls",
        local_part_prefix=" BDA- ",
    )
    assert payload.local_part_prefix == "bda-"

    for invalid in ("", "b-", "admin", "bda_", "-bda-", "bda.*-"):
        with pytest.raises(ValidationError):
            PlatformMailDomainGrantCreate(
                service_client_id="business-digital-address",
                domain_name="ithute.co.ls",
                local_part_prefix=invalid,
            )


def test_platform_mail_send_request_is_single_recipient_and_idempotent_reference_ready() -> None:
    payload = PlatformMailSendRequest(
        external_reference="bda-delivery:123",
        recipient=" Accounts@Example.COM ",
        subject="Official communication",
        text="Retained in the official inbox first.",
    )
    assert payload.external_reference == "bda-delivery:123"
    assert payload.recipient == "accounts@example.com"
    assert payload.subject == "Official communication"


def test_platform_mail_forwarding_request_normalizes_destination() -> None:
    payload = PlatformMailboxForwardingRequest(destination=" Business@Gmail.COM ")
    assert payload.destination == "business@gmail.com"
    with pytest.raises(ValidationError):
        PlatformMailboxForwardingRequest(destination="not-an-email")


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


def test_platform_mail_uses_canonical_authorized_party_as_client_identity() -> None:
    source = AUTH.read_text(encoding="utf-8")
    assert 'audience: str = "ithute-mail"' in source
    assert "require_platform_service_scope" in source
    assert "required_scope not in scopes" in source
    assert 'client_id=str(claims["azp"])' in source
    assert 'client_id=str(claims["sub"])' not in source


def test_provisioning_is_domain_granted_namespaced_idempotent_and_credentialless() -> None:
    source = API.read_text(encoding="utf-8")
    for required in (
        'prefix="/platform/mail"',
        'require_platform_service_scope("mailbox.create")',
        "PlatformMailDomainGrant.active.is_(True)",
        "grant.local_part_prefix",
        "local_part.startswith(grant.local_part_prefix)",
        "Mailbox local part is outside the service client namespace",
        "PlatformMailboxBinding.service_client_id == principal.client_id",
        "PlatformMailboxBinding.external_reference == reference",
        "External reference is already bound to another mailbox",
        "internal_password = secrets.token_urlsafe",
        "hash_mailbox_password(internal_password)",
        '"credential_mode": "platform-managed"',
        "sync_mailbox(mailbox)",
        '"/mailboxes/{binding_id}/suspend"',
        '"/mailboxes/{binding_id}/reactivate"',
        "_require_grant_namespace(grant, mailbox.local_part)",
    ):
        assert required in source
    assert "internal_password" not in (ROOT / "app" / "schemas" / "platform_mail.py").read_text(encoding="utf-8")


def test_service_send_is_owned_scoped_namespaced_rate_limited_and_idempotent() -> None:
    source = API.read_text(encoding="utf-8")
    for required in (
        '"/mailboxes/{binding_id}/send"',
        'require_platform_service_scope("mail.send")',
        "binding.service_client_id != principal.client_id",
        "mailbox.status != MailboxStatus.active",
        "grant.service_client_id != principal.client_id",
        "_require_grant_namespace(grant, mailbox.local_part)",
        "PlatformMailOutboundDelivery.service_client_id == principal.client_id",
        "PlatformMailOutboundDelivery.external_reference == payload.external_reference",
        "Outbound external reference was already used for different content",
        "payload_hash",
        'status="submitting"',
        "db.commit()",
        "send_message(",
        "sender=mailbox.address",
        "recipients=[recipient]",
        "settings.transactional_tenant_daily_limit",
        'action="platform_mail.message.submitted"',
        'action="platform_mail.message.failed"',
    ):
        assert required in source
    assert "payload.sender" not in source


def test_inbound_forwarding_is_owned_scoped_namespaced_and_runtime_synced() -> None:
    source = FORWARDING_API.read_text(encoding="utf-8")
    for required in (
        '"/mailboxes/{binding_id}/inbound-forwarding"',
        'require_platform_service_scope("mail.forward")',
        "_owned_binding",
        "_active_binding_grant",
        "mailbox.status != MailboxStatus.active",
        "normalize_destination(payload.destination)",
        "destination == mailbox.address.lower()",
        "binding.inbound_forward_to = destination",
        "sync_mailbox_forwarding(mailbox, destination)",
        "sync_mailbox_forwarding(mailbox, None)",
        'action="platform_mail.inbound_forwarding.configured"',
        'action="platform_mail.inbound_forwarding.disabled"',
        'action="platform_mail.inbound_forwarding.sync_failed"',
        'settings.environment.lower() == "production" and not synced',
    ):
        assert required in source


def test_runtime_forwarding_keeps_original_mailbox_and_uses_recipient_bcc_map() -> None:
    source = ACCOUNT_SYNC.read_text(encoding="utf-8")
    bootstrap = BOOTSTRAP_MAIL.read_text(encoding="utf-8")
    mail_compose = MAIL_COMPOSE.read_text(encoding="utf-8")
    for required in (
        "def sync_mailbox_forwarding(",
        'postfix-recipient-bcc.cf',
        'platform-forwarding-revision:',
        "Mailbox cannot forward to itself",
    ):
        assert required in source
    assert "recipient_bcc_maps = texthash:/mail-accounts/postfix-recipient-bcc.cf" in bootstrap
    assert 'DMS_CONFIG_POLL: "2"' in mail_compose


def test_platform_mail_models_enforce_service_ownership_namespace_and_outbound_idempotency() -> None:
    source = MODELS.read_text(encoding="utf-8")
    assert "platform_mail_domain_grants" in source
    assert "uq_platform_mail_grant_client_domain" in source
    assert "local_part_prefix" in source
    assert "platform_mailbox_bindings" in source
    assert "uq_platform_mailbox_binding_client_reference" in source
    assert "uq_platform_mailbox_binding_mailbox" in source
    assert "inbound_forward_to" in source
    assert "platform_mail_outbound_deliveries" in source
    assert "uq_platform_mail_outbound_client_reference" in source
    assert "transactional_message_id" in source
    assert "payload_hash" in source


def test_initial_platform_mail_migration_extends_commercial_catalog() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "0023_platform_mail_provisioning"' in source
    assert 'down_revision = "0022_commercial_catalog"' in source
    assert "platform_mail_domain_grants" in source
    assert "platform_mailbox_bindings" in source


def test_namespace_migration_disables_legacy_whole_domain_grants() -> None:
    source = NAMESPACE_MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "0024_mail_namespace"' in source
    assert 'down_revision = "0023_platform_mail_provisioning"' in source
    assert 'sa.Column("local_part_prefix", sa.String(length=32), nullable=True)' in source
    assert '"SET active = false, local_part_prefix = :prefix"' in source
    assert '_LEGACY_DISABLED_PREFIX = "legacy-disabled-"' in source
    assert '"local_part_prefix"' in source
    assert "nullable=False" in source


def test_send_migration_extends_namespaced_platform_mail() -> None:
    source = SEND_MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "0025_platform_mail_send"' in source
    assert 'down_revision = "0024_mail_namespace"' in source
    assert "platform_mail_outbound_deliveries" in source
    assert "uq_platform_mail_outbound_client_reference" in source
    assert "platform_mailbox_bindings.id" in source
    assert "transactional_messages.id" in source


def test_forwarding_migration_extends_managed_platform_mail() -> None:
    source = FORWARDING_MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "0026_mail_forwarding"' in source
    assert 'down_revision = "0025_platform_mail_send"' in source
    assert '"platform_mailbox_bindings"' in source
    assert '"inbound_forward_to"' in source
    assert "String(length=320)" in source


def test_router_mounts_platform_mail_api() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert "platform_mail," in source
    assert "platform_mail_forwarding," in source
    assert "api_router.include_router(platform_mail.router)" in source
    assert "api_router.include_router(platform_mail_forwarding.router)" in source
