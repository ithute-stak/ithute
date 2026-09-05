import json
import os
import uuid

os.environ.setdefault("AUTH_DATABASE_URL", "sqlite+pysqlite:///:memory:")

from webauthn import generate_authentication_options, generate_registration_options, options_to_json
from webauthn.helpers.structs import AuthenticatorSelectionCriteria, ResidentKeyRequirement, UserVerificationRequirement

from app.config import Settings
from app.passkeys import _b64url, _from_b64url


def test_passkey_defaults_are_bound_to_central_auth_domain() -> None:
    settings = Settings(database_url="sqlite://")
    assert settings.webauthn_rp_id == "auth.ithute.co.ls"
    assert settings.webauthn_origin == "https://auth.ithute.co.ls"
    assert settings.webauthn_challenge_minutes == 5


def test_passkey_binary_values_round_trip_base64url_without_padding() -> None:
    raw = uuid.uuid4().bytes + b"\x00\xff"
    encoded = _b64url(raw)
    assert "=" not in encoded
    assert _from_b64url(encoded) == raw


def test_registration_requires_discoverable_credential_and_user_verification() -> None:
    challenge = b"c" * 32
    options = generate_registration_options(
        rp_id="auth.ithute.co.ls",
        rp_name="!thute",
        user_id=uuid.uuid4().bytes,
        user_name="user@example.com",
        user_display_name="Example User",
        challenge=challenge,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    payload = json.loads(options_to_json(options))
    assert payload["rp"]["id"] == "auth.ithute.co.ls"
    assert payload["authenticatorSelection"]["residentKey"] == "required"
    assert payload["authenticatorSelection"]["requireResidentKey"] is True
    assert payload["authenticatorSelection"]["userVerification"] == "required"


def test_authentication_requires_user_verification_and_is_rp_scoped() -> None:
    options = generate_authentication_options(
        rp_id="auth.ithute.co.ls",
        challenge=b"a" * 32,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    payload = json.loads(options_to_json(options))
    assert payload["rpId"] == "auth.ithute.co.ls"
    assert payload["userVerification"] == "required"
    assert payload["allowCredentials"] == []
