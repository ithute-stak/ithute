import uuid

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import Settings
from app.security import create_access_token, create_id_token


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
        system_owner_email="supperadmin@ithute.co.ls",
    )


def _decode(token: str, settings: Settings, audience: str) -> dict:
    return jwt.decode(
        token,
        settings.public_key,
        algorithms=["RS256"],
        issuer=settings.issuer.rstrip("/"),
        audience=audience,
    )


def test_system_owner_access_token_carries_platform_admin_claim(tmp_path) -> None:
    settings = _settings(tmp_path)
    token = create_access_token(
        settings=settings,
        user_id=uuid.uuid4(),
        client_id="loanhub",
        session_id=uuid.uuid4(),
        email="SUPPERADMIN@ITHUTE.CO.LS",
        phone=None,
    )
    claims = _decode(token, settings, "loanhub")
    assert claims["is_platform_admin"] is True


def test_ordinary_user_does_not_receive_platform_admin_claim(tmp_path) -> None:
    settings = _settings(tmp_path)
    token = create_access_token(
        settings=settings,
        user_id=uuid.uuid4(),
        client_id="ithute-pay",
        session_id=uuid.uuid4(),
        email="person@example.com",
        phone=None,
    )
    claims = _decode(token, settings, "ithute-pay")
    assert claims["is_platform_admin"] is False


def test_system_owner_id_token_carries_same_signed_claim(tmp_path) -> None:
    settings = _settings(tmp_path)
    token = create_id_token(
        settings=settings,
        user_id=uuid.uuid4(),
        client_id="ithute-tutor",
        session_id=uuid.uuid4(),
        nonce="nonce",
        email="supperadmin@ithute.co.ls",
        phone=None,
        display_name="Ithute System Owner",
        email_verified=True,
        phone_verified=False,
    )
    claims = _decode(token, settings, "ithute-tutor")
    assert claims["is_platform_admin"] is True
