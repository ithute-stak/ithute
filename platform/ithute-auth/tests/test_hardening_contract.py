import json
import os
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import ValidationError

# security_service imports the ORM models, whose database module initializes a
# SQLAlchemy engine. Unit/contract tests use an isolated in-memory configuration
# and must never depend on production database environment variables.
os.environ.setdefault("AUTH_DATABASE_URL", "sqlite://")

from app.config import Settings
from app.schemas import MfaEnrollRequest
from app.security import (
    create_access_token,
    decode_access_token,
    decrypt_totp_secret,
    encrypt_totp_secret,
    hash_recovery_code,
    new_recovery_codes,
    new_totp_secret,
    public_jwk,
    public_jwks,
    verify_totp,
)
from app.security_service import client_ip


def _rsa_settings(tmp_path, **overrides) -> Settings:
    tmp_path.mkdir(parents=True, exist_ok=True)
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_path = tmp_path / "private.pem"
    public_path = tmp_path / "public.pem"
    private_path.write_bytes(
        private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        private.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    values = {
        "database_url": "sqlite://",
        "jwt_private_key_file": str(private_path),
        "jwt_public_key_file": str(public_path),
        "issuer": "https://auth.ithute.co.ls",
    }
    values.update(overrides)
    return Settings(**values)


def test_ithute_tutor_is_a_first_party_client() -> None:
    settings = Settings(database_url="sqlite://")
    assert settings.client_map["ithute-tutor"] == "Ithute Tutor"


def test_recovery_codes_are_high_entropy_one_time_material() -> None:
    codes = new_recovery_codes()
    assert len(codes) == 10
    assert len(set(codes)) == 10
    assert all(len(code) >= 25 for code in codes)
    assert len({hash_recovery_code(code) for code in codes}) == 10


def test_totp_secret_is_encrypted_at_rest(tmp_path) -> None:
    key = Fernet.generate_key().decode("ascii")
    settings = _rsa_settings(tmp_path, totp_encryption_key=key)
    secret = new_totp_secret()
    encrypted = encrypt_totp_secret(secret, settings)
    assert secret not in encrypted
    assert decrypt_totp_secret(encrypted, settings) == secret


def test_totp_rejects_malformed_codes() -> None:
    secret = new_totp_secret()
    assert verify_totp(secret, "abc") is False
    assert verify_totp(secret, "12345") is False


def test_mfa_enrollment_requires_fresh_password_proof() -> None:
    with pytest.raises(ValidationError):
        MfaEnrollRequest()
    assert MfaEnrollRequest(password="correct horse battery staple").password


def test_mfa_enrollment_explicitly_blocks_replacing_active_mfa() -> None:
    source = (Path(__file__).parents[1] / "app" / "account.py").read_text(encoding="utf-8")
    assert "context.user.totp_enabled" in source
    assert "MFA is already enabled" in source
    assert "verify_password(payload.password" in source


def test_browser_recovery_routes_are_wired_into_auth() -> None:
    main_source = (Path(__file__).parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    recovery_source = (Path(__file__).parents[1] / "app" / "recovery_portal.py").read_text(encoding="utf-8")
    assert "recovery_portal_router" in main_source
    assert '@router.get("/forgot-password"' in recovery_source
    assert '@router.get("/reset-password"' in recovery_source
    assert '@router.post("/reset-password")' in recovery_source
    assert "Referrer-Policy" in recovery_source
    assert "Cache-Control" in recovery_source


def test_jwks_keeps_previous_public_keys_during_rotation(tmp_path) -> None:
    old_settings = _rsa_settings(tmp_path / "old", jwt_key_id="retired-key")
    old_jwk = public_jwk(old_settings)
    settings = _rsa_settings(
        tmp_path / "new",
        jwt_key_id="current-key",
        previous_jwks_json=json.dumps([old_jwk]),
    )
    keys = public_jwks(settings)
    assert keys[0]["kid"] == "current-key"
    assert any(key["kid"] == "retired-key" for key in keys)


def test_access_tokens_signed_by_retired_key_remain_verifiable_during_rollover(tmp_path) -> None:
    old_settings = _rsa_settings(tmp_path / "old-access", jwt_key_id="retired-key")
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    token = create_access_token(
        settings=old_settings,
        user_id=user_id,
        client_id="ithute-tutor",
        session_id=session_id,
        email="user@example.com",
        phone=None,
    )
    new_settings = _rsa_settings(
        tmp_path / "new-access",
        jwt_key_id="current-key",
        previous_jwks_json=json.dumps([public_jwk(old_settings)]),
    )
    claims = decode_access_token(token, new_settings)
    assert claims["sub"] == str(user_id)
    assert claims["sid"] == str(session_id)
    assert claims["aud"] == "ithute-tutor"


def test_untrusted_peer_cannot_spoof_forwarded_client_ip() -> None:
    settings = Settings(database_url="sqlite://", trusted_proxy_cidrs="10.0.0.0/8")
    request = SimpleNamespace(
        headers={"x-forwarded-for": "203.0.113.10"},
        client=SimpleNamespace(host="198.51.100.7"),
    )
    assert client_ip(request, settings) == "198.51.100.7"


def test_trusted_proxy_chain_returns_original_untrusted_client() -> None:
    settings = Settings(database_url="sqlite://", trusted_proxy_cidrs="10.0.0.0/8,127.0.0.1/32")
    request = SimpleNamespace(
        headers={"x-forwarded-for": "203.0.113.10, 10.20.30.40"},
        client=SimpleNamespace(host="10.1.2.3"),
    )
    assert client_ip(request, settings) == "203.0.113.10"
