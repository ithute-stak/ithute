from pathlib import Path

import pytest
from pydantic import ValidationError

from app.identity_invitation_schemas import TrustedIdentityInvitationRequest


ROOT = Path(__file__).parents[1]
INVITATIONS = ROOT / "app" / "identity_invitations.py"
AUTHZ = ROOT / "app" / "service_authorization.py"
PORTAL = ROOT / "app" / "identity_invitation_portal.py"
MODELS = ROOT / "app" / "identity_invitation_models.py"
MIGRATION = ROOT / "alembic" / "versions" / "0007_trusted_identity_invitations.py"
SERVER = ROOT / "app" / "server.py"


def test_invitation_requires_matching_delivery_target() -> None:
    request = TrustedIdentityInvitationRequest(
        external_reference="2026/001234:owner",
        display_name="Business Owner",
        email="owner@example.com",
        phone="+26662000000",
        preferred_channel="phone",
    )
    assert request.phone == "+26662000000"
    assert request.email is None

    email_request = TrustedIdentityInvitationRequest(
        external_reference="2026/001235:owner",
        display_name="Business Owner",
        email="owner@example.com",
        phone="+26662000001",
        preferred_channel="email",
    )
    assert str(email_request.email) == "owner@example.com"
    assert email_request.phone is None

    with pytest.raises(ValidationError):
        TrustedIdentityInvitationRequest(
            external_reference="2026/001234:owner",
            display_name="Business Owner",
            phone="+26662000000",
            preferred_channel="email",
        )


def test_migration_creates_durable_pending_invitation_state() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    for required in (
        'revision = "0007_identity_invites"',
        'down_revision = "0006_managed_service_clients"',
        '"identity_invitations"',
        '"source_client_id"',
        '"external_reference"',
        '"challenge_token_hash"',
        '"challenge_code_hash"',
        '"activation_attempts"',
        '"consumed_at"',
        '"cancelled_at"',
        '"user_id"',
    ):
        assert required in source


def test_new_platform_api_requires_managed_identity_invite_scope() -> None:
    source = AUTHZ.read_text(encoding="utf-8")
    assert 'claims.get("token_use") != "service"' in source
    assert 'claims.get("service_auth") != "managed"' in source
    assert 'token_audience != audience' in source
    assert "ManagedServiceClient" in source
    assert "Legacy" in source
    assert "required_scope not in scopes" in source
    assert "required_scope not in allowed_scopes" in source


def test_invitation_lifecycle_is_idempotent_audited_and_rate_limited() -> None:
    source = INVITATIONS.read_text(encoding="utf-8")
    for required in (
        'prefix="/v1/platform/identity-invitations"',
        'Depends(require_managed_service_scope("identity.invite"))',
        "source_client_id == context.client_id",
        "external_reference == reference",
        '"/{invitation_id}/resend"',
        '"/{invitation_id}/cancel"',
        "RESEND_COOLDOWN",
        "MAX_ACTIVATION_ATTEMPTS",
        "trusted_identity_invitation_created",
        "trusted_identity_invitation_delivery_failed",
        "trusted_identity_invitation_activation_failed",
        "trusted_identity_invitation_activated",
        'event_type="identity.invitation_activated"',
    ):
        assert required in source


def test_existing_identity_can_only_be_invited_through_its_registered_contact() -> None:
    source = INVITATIONS.read_text(encoding="utf-8")
    assert "_validate_existing_identity_target" in source
    assert "existing Ithute identity must be invited through its registered phone" in source
    assert "existing Ithute identity must be invited through its registered email" in source
    assert source.count("_validate_existing_identity_target(") >= 4


def test_invitation_never_uses_phone_as_password_and_creates_credentials_only_after_activation() -> None:
    source = INVITATIONS.read_text(encoding="utf-8")
    assert "password_hash=hash_password(payload.password)" in source
    assert "password_hash=hash_password(invitation.phone" not in source
    assert "password_hash=invitation.phone" not in source
    assert "challenge_code_hash=hash_password" in source
    assert "verify_password(payload.code.strip(), invitation.challenge_code_hash)" in source


def test_activation_portal_explains_credential_boundary() -> None:
    source = PORTAL.read_text(encoding="utf-8")
    assert "Trade or another trusted service can invite you" in source
    assert "it never receives your password" in source
    assert "If you already have an Ithute identity" in source
    assert "/account/activate" in source


def test_models_store_only_challenge_hashes() -> None:
    source = MODELS.read_text(encoding="utf-8")
    assert "challenge_token_hash" in source
    assert "challenge_code_hash" in source
    assert "activation_code:" not in source
    assert "activation_token:" not in source


def test_server_mounts_platform_public_and_browser_activation_routes() -> None:
    source = SERVER.read_text(encoding="utf-8")
    assert "identity_invitation_platform_router" in source
    assert "identity_invitation_public_router" in source
    assert "identity_invitation_portal_router" in source
