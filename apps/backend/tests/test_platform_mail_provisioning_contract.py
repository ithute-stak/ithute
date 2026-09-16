from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "apps" / "backend"
PLATFORM_MAIL = BACKEND / "app" / "api" / "v1" / "platform_mail.py"
FORWARDING_API = BACKEND / "app" / "api" / "v1" / "platform_mail_forwarding.py"
PLATFORM_AUTH = BACKEND / "app" / "api" / "platform_service_auth.py"
SCHEMAS = BACKEND / "app" / "schemas" / "platform_mail.py"
MODELS = BACKEND / "app" / "models" / "platform_mail.py"
ACCOUNT_SYNC = BACKEND / "app" / "services" / "mail_account_sync.py"
MIGRATION = BACKEND / "alembic" / "versions" / "0023_platform_mail_provisioning.py"
NAMESPACE_MIGRATION = BACKEND / "alembic" / "versions" / "0024_platform_mail_namespace_grants.py"
SEND_MIGRATION = BACKEND / "alembic" / "versions" / "0025_platform_mail_send.py"
FORWARDING_MIGRATION = BACKEND / "alembic" / "versions" / "0026_platform_mail_inbound_forwarding.py"
RUNTIME_INSTALLER = ROOT / "mail" / "enable-recipient-bcc.sh"
RUNTIME_WORKFLOW = ROOT / ".github" / "workflows" / "enable-mail-inbound-forwarding.yml"
MAIL_COMPOSE = ROOT / "mail" / "compose.yml"


def test_platform_mail_provisioning_is_service_owned_and_namespace_scoped() -> None:
    source = PLATFORM_MAIL.read_text(encoding="utf-8")
    for required in (
        'router = APIRouter(prefix="/platform/mail"',
        'require_platform_service_scope("mailbox.create")',
        "_grant_for",
        "_require_grant_namespace",
        "grant.local_part_prefix",
        "service_client_id=principal.client_id",
        "external_reference=reference",
        "PlatformMailboxBinding",
        "sync_mailbox(mailbox)",
        "secrets.token_urlsafe(48)",
        '"credential_mode": "platform-managed"',
    ):
        assert required in source
    assert "payload.password" not in source


def test_domain_grants_require_platform_owner_and_explicit_namespace() -> None:
    source = PLATFORM_MAIL.read_text(encoding="utf-8")
    schemas = SCHEMAS.read_text(encoding="utf-8")
    for required in (
        '@router.post("/domain-grants"',
        "Depends(require_platform_owner)",
        "payload.local_part_prefix",
        "grant.local_part_prefix = payload.local_part_prefix",
        '@router.post("/domain-grants/{grant_id}/disable"',
    ):
        assert required in source
    for required in (
        "local_part_prefix",
        "normalize_namespace_prefix",
        "end with a hyphen",
    ):
        assert required in schemas


def test_platform_service_identity_comes_from_canonical_azp() -> None:
    source = PLATFORM_AUTH.read_text(encoding="utf-8")
    for required in (
        "decode_ithute_service_token",
        'client_id=str(claims["azp"])',
        'token_id=str(claims["jti"])',
        "required_scope not in scopes",
    ):
        assert required in source
    assert 'claims.get("client_id")' not in source


def test_platform_mail_send_uses_owned_binding_sender_and_idempotency() -> None:
    source = PLATFORM_MAIL.read_text(encoding="utf-8")
    for required in (
        '"/mailboxes/{binding_id}/send"',
        'require_platform_service_scope("mail.send")',
        "_owned_binding",
        "binding.service_client_id != principal.client_id",
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
        "_sync_runtime(mailbox, destination)",
        "_sync_runtime(mailbox, None)",
        'action="platform_mail.inbound_forwarding.configured"',
        'action="platform_mail.inbound_forwarding.disabled"',
        'action="platform_mail.inbound_forwarding.sync_failed"',
        'settings.environment.lower() == "production" and not synced',
    ):
        assert required in source


def test_runtime_forwarding_keeps_original_mailbox_and_uses_recipient_bcc_map() -> None:
    source = ACCOUNT_SYNC.read_text(encoding="utf-8")
    installer = RUNTIME_INSTALLER.read_text(encoding="utf-8")
    workflow = RUNTIME_WORKFLOW.read_text(encoding="utf-8")
    mail_compose = MAIL_COMPOSE.read_text(encoding="utf-8")
    for required in (
        "def sync_mailbox_forwarding(",
        "postfix-recipient-bcc.cf",
        "platform-forwarding-revision:",
        ".recipient-bcc-ready",
        "Mailbox cannot forward to itself",
    ):
        assert required in source
    assert "recipient_bcc_maps = texthash:/mail-accounts/postfix-recipient-bcc.cf" in installer
    assert "postconf -h recipient_bcc_maps" in installer
    assert "postconf -m" in installer
    assert ".recipient-bcc-ready" in installer
    assert "--force-recreate mailserver" in installer
    assert "mail/enable-recipient-bcc.sh" in workflow
    assert "Verify production marker and Postfix map" in workflow
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
    assert '"platform_mail_domain_grants"' in source
    assert '"platform_mailbox_bindings"' in source


def test_namespace_migration_fails_closed_for_existing_grants() -> None:
    source = NAMESPACE_MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "0024_mail_namespace"' in source
    assert 'down_revision = "0023_platform_mail_provisioning"' in source
    assert '"local_part_prefix"' in source
    assert '_LEGACY_DISABLED_PREFIX = "legacy-disabled-"' in source
    assert '"SET active = false, local_part_prefix = :prefix"' in source
    assert "nullable=False" in source


def test_send_migration_adds_idempotent_outbound_ledger() -> None:
    source = SEND_MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "0025_platform_mail_send"' in source
    assert 'down_revision = "0024_mail_namespace"' in source
    assert '"platform_mail_outbound_deliveries"' in source
    assert '"uq_platform_mail_outbound_client_reference"' in source
    assert '"payload_hash"' in source


def test_forwarding_migration_adds_destination_to_owned_binding() -> None:
    source = FORWARDING_MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "0026_mail_forwarding"' in source
    assert 'down_revision = "0025_platform_mail_send"' in source
    assert '"inbound_forward_to"' in source
