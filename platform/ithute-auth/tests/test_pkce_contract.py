import uuid

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import Settings
from app.security import (
    create_browser_session_token,
    create_id_token,
    decode_browser_session_token,
    hash_authorization_code,
    new_authorization_code,
    pkce_s256,
)


def test_pkce_s256_matches_rfc7636_example() -> None:
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert pkce_s256(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_authorization_codes_are_random_and_only_hashes_need_persisting() -> None:
    first = new_authorization_code()
    second = new_authorization_code()
    assert first != second
    assert len(first) >= 43
    assert len(hash_authorization_code(first)) == 64
    assert hash_authorization_code(first) != first


def test_redirect_uri_allowlist_is_exact_and_rejects_insecure_remote_http() -> None:
    settings = Settings(
        database_url="sqlite://",
        redirect_uris_json=(
            '{"loanhub":['
            '"https://loanhub.example/auth/callback",'
            '"http://localhost:3000/auth/callback",'
            '"http://127.0.0.1:3000/auth/callback",'
            '"http://unsafe.example/auth/callback",'
            '"http://localhost.evil.example/auth/callback",'
            '"https://loanhub.example/auth/callback#fragment",'
            '"https://loanhub.example/auth/callback"'
            "]}"
        ),
    )
    assert settings.redirect_uris["loanhub"] == (
        "https://loanhub.example/auth/callback",
        "http://localhost:3000/auth/callback",
        "http://127.0.0.1:3000/auth/callback",
    )
    assert "https://loanhub.example/auth/callback/extra" not in settings.redirect_uris["loanhub"]
    assert "http://localhost.evil.example/auth/callback" not in settings.redirect_uris["loanhub"]


def _rsa_settings(tmp_path) -> Settings:
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
    return Settings(
        database_url="sqlite://",
        jwt_private_key_file=str(private_path),
        jwt_public_key_file=str(public_path),
        issuer="https://auth.ithute.co.ls",
    )


def test_browser_sso_token_is_signed_for_auth_browser_audience(tmp_path) -> None:
    settings = _rsa_settings(tmp_path)
    user_id = uuid.uuid4()
    token = create_browser_session_token(settings=settings, user_id=user_id, security_version=7)
    claims = decode_browser_session_token(token, settings)
    assert claims["sub"] == str(user_id)
    assert claims["aud"] == "ithute-auth-browser"
    assert claims["token_use"] == "browser_session"
    assert claims["sv"] == 7


def test_id_token_is_nonce_bound_and_product_audience_scoped(tmp_path) -> None:
    settings = _rsa_settings(tmp_path)
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    nonce = "nonce-value-1234567890"
    token = create_id_token(
        settings=settings,
        user_id=user_id,
        client_id="loanhub",
        session_id=session_id,
        nonce=nonce,
        email="user@example.com",
        phone="+26650000000",
        display_name="Example User",
        email_verified=True,
        phone_verified=False,
    )
    claims = jwt.decode(
        token,
        settings.public_key,
        algorithms=["RS256"],
        issuer="https://auth.ithute.co.ls",
        audience="loanhub",
    )
    assert claims["sub"] == str(user_id)
    assert claims["sid"] == str(session_id)
    assert claims["nonce"] == nonce
    assert claims["token_use"] == "id"
    assert claims["email_verified"] is True
    assert claims["phone_number_verified"] is False
