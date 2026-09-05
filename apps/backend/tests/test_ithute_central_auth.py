from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.services.ithute_auth import IthuteAuthSettings, decode_ithute_access_token


class _SigningKey:
    def __init__(self, key):
        self.key = key


class _JwksClient:
    def __init__(self, key):
        self.key = key

    def get_signing_key_from_jwt(self, _token):
        return _SigningKey(self.key)


def _keys():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = public_key.public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def _token(private_key: bytes, *, audience: str = "mailbox-dns", token_use: str = "access") -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "iss": "https://auth.ithute.co.ls",
            "sub": str(uuid4()),
            "aud": audience,
            "sid": str(uuid4()),
            "iat": now,
            "nbf": now - timedelta(seconds=1),
            "exp": now + timedelta(minutes=5),
            "token_use": token_use,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )


def test_mailbox_accepts_only_its_central_audience():
    private_key, public_key = _keys()
    config = IthuteAuthSettings(enabled=True, audience="mailbox-dns")
    claims = decode_ithute_access_token(
        _token(private_key),
        config=config,
        jwks_client=_JwksClient(public_key),
    )
    assert claims["aud"] == "mailbox-dns"

    with pytest.raises(jwt.InvalidAudienceError):
        decode_ithute_access_token(
            _token(private_key, audience="loanhub"),
            config=config,
            jwks_client=_JwksClient(public_key),
        )


def test_mailbox_rejects_non_access_central_token():
    private_key, public_key = _keys()
    config = IthuteAuthSettings(enabled=True, audience="mailbox-dns")
    with pytest.raises(jwt.InvalidTokenError):
        decode_ithute_access_token(
            _token(private_key, token_use="service"),
            config=config,
            jwks_client=_JwksClient(public_key),
        )
