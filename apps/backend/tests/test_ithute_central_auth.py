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


def test_central_security_center_redirects_to_auth_portal(client, monkeypatch):
    from app.api.v1 import ithute_auth as ithute_auth_api

    monkeypatch.setattr(
        ithute_auth_api,
        "get_ithute_auth_settings",
        lambda: IthuteAuthSettings(enabled=True, issuer="https://auth.ithute.co.ls", audience="mailbox-dns"),
    )

    response = client.get("/api/v1/auth/ithute/account", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "https://auth.ithute.co.ls/account"


def test_enforce_central_auth_is_irreversible_and_persisted(client, db, platform_owner):
    from app.api.deps import get_current_local_user
    from app.models import User

    user = db.get(User, platform_owner.id)
    user.auth_user_id = uuid4()
    db.commit()

    client.app.dependency_overrides[get_current_local_user] = lambda: user
    try:
        response = client.post(
            "/api/v1/auth/ithute/enforce",
            json={"current_password": "Phase1-Test-Password!"},
        )
        assert response.status_code == 200
        assert response.json()["enforced"] is True

        db.expire_all()
        persisted = db.get(User, platform_owner.id)
        assert persisted.central_auth_enforced is True
        assert persisted.central_auth_enforced_at is not None

        status = client.get("/api/v1/auth/ithute/status")
        assert status.status_code == 200
        assert status.json()["enforced"] is True

        unlink = client.post(
            "/api/v1/auth/ithute/unlink",
            json={"current_password": "Phase1-Test-Password!"},
        )
        assert unlink.status_code == 409
        assert unlink.json()["detail"]["code"] == "CENTRAL_AUTH_PERMANENTLY_ENFORCED"
    finally:
        client.app.dependency_overrides.pop(get_current_local_user, None)
