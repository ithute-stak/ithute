from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.requests import Request

from utils import central_auth


ISSUER = "https://auth.ithute.co.ls"
AUDIENCE = "ithute-tutor"
SUBJECT = uuid.uuid4()


@pytest.fixture
def rsa_keys():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def make_token(private_key, **overrides):
    now = datetime.now(timezone.utc)
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": str(SUBJECT),
        "token_use": "access",
        "iat": now,
        "exp": now + timedelta(minutes=10),
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})


def use_test_key(monkeypatch, public_key):
    class FakeJwksClient:
        def __init__(self, url: str):
            self.url = url

        def get_signing_key_from_jwt(self, token: str):
            return SimpleNamespace(key=public_key)

    monkeypatch.setattr(central_auth.jwt, "PyJWKClient", FakeJwksClient)


def test_accepts_valid_central_tutor_access_token(monkeypatch, rsa_keys):
    private_key, public_key = rsa_keys
    use_test_key(monkeypatch, public_key)

    claims = central_auth.validate_central_access_token(make_token(private_key))

    assert claims["iss"] == ISSUER
    assert claims["aud"] == AUDIENCE
    assert claims["token_use"] == "access"
    assert claims["sub"] == str(SUBJECT)


def test_rejects_token_for_another_product(monkeypatch, rsa_keys):
    private_key, public_key = rsa_keys
    use_test_key(monkeypatch, public_key)

    with pytest.raises(central_auth.CentralAuthError):
        central_auth.validate_central_access_token(make_token(private_key, aud="mailbox-dns"))


def test_rejects_service_token(monkeypatch, rsa_keys):
    private_key, public_key = rsa_keys
    use_test_key(monkeypatch, public_key)

    with pytest.raises(central_auth.CentralAuthError):
        central_auth.validate_central_access_token(make_token(private_key, token_use="service"))


def test_rejects_non_uuid_subject(monkeypatch, rsa_keys):
    private_key, public_key = rsa_keys
    use_test_key(monkeypatch, public_key)

    with pytest.raises(central_auth.CentralAuthError):
        central_auth.validate_central_access_token(make_token(private_key, sub="not-a-uuid"))


def test_require_claims_reuses_middleware_verified_claims(monkeypatch):
    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/auth/me",
            "raw_path": b"/auth/me",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 443),
        }
    )
    expected = {"sub": str(SUBJECT), "aud": AUDIENCE, "token_use": "access"}
    request.state.central_claims = expected

    def should_not_validate(token: str):
        raise AssertionError("JWT should not be validated twice within one request")

    monkeypatch.setattr(central_auth, "validate_central_access_token", should_not_validate)

    assert central_auth.require_central_claims(request) is expected
