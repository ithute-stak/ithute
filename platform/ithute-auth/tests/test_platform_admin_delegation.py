import uuid

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.admin_delegation import PUSH_ADMIN_CLIENT_ID, PUSH_ADMIN_TOKEN_MINUTES, create_push_admin_token
from app.config import Settings


def _settings(tmp_path) -> Settings:
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
    )


def test_push_admin_delegation_is_human_session_bound_and_short_lived(tmp_path) -> None:
    settings = _settings(tmp_path)
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    token = create_push_admin_token(
        settings=settings,
        user_id=user_id,
        client_id=PUSH_ADMIN_CLIENT_ID,
        session_id=session_id,
    )
    claims = jwt.decode(
        token,
        settings.public_key,
        algorithms=["RS256"],
        issuer=settings.issuer.rstrip("/"),
        audience="ithute-push",
    )
    assert claims["sub"] == str(user_id)
    assert claims["sid"] == str(session_id)
    assert claims["azp"] == "mailbox-dns"
    assert claims["token_use"] == "push_admin"
    assert claims["scope"] == "push.admin"
    assert claims["exp"] - claims["iat"] == PUSH_ADMIN_TOKEN_MINUTES * 60
    assert claims["exp"] - claims["iat"] <= 120


def test_non_console_clients_cannot_mint_push_admin_delegation(tmp_path) -> None:
    settings = _settings(tmp_path)
    with pytest.raises(ValueError, match="not approved"):
        create_push_admin_token(
            settings=settings,
            user_id=uuid.uuid4(),
            client_id="ithute-tutor",
            session_id=uuid.uuid4(),
        )
