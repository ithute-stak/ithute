import os
import uuid
from datetime import timedelta

import jwt

os.environ.setdefault("AUTH_DATABASE_URL", "sqlite+pysqlite:///:memory:")

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import Base
from app.models import Application, AuthEventOutbox, AuthSession, User, utcnow
from app.security import create_push_access_token


def _settings(tmp_path) -> Settings:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    private_path = tmp_path / "private.pem"
    public_path = tmp_path / "public.pem"
    private_path.write_bytes(private_pem)
    public_path.write_bytes(public_pem)
    return Settings(
        database_url="sqlite://",
        jwt_private_key_file=str(private_path),
        jwt_public_key_file=str(public_path),
        push_user_token_minutes=3,
    )


def test_push_access_token_is_resource_scoped_and_session_bound(tmp_path) -> None:
    settings = _settings(tmp_path)
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    token = create_push_access_token(
        settings=settings,
        user_id=user_id,
        client_id="ithute-tutor",
        session_id=session_id,
    )
    claims = jwt.decode(token, options={"verify_signature": False})
    assert claims["sub"] == str(user_id)
    assert claims["sid"] == str(session_id)
    assert claims["aud"] == "ithute-push"
    assert claims["azp"] == "ithute-tutor"
    assert claims["scope"] == "push.device"
    assert claims["token_use"] == "push_access"
    assert claims["exp"] - claims["iat"] == 180


def test_auth_status_and_session_changes_enter_same_database_outbox() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = utcnow()
    with Session(engine) as db:
        user = User(
            email="push-contract@example.test",
            display_name="Push Contract",
            password_hash="not-used",
        )
        app = Application(client_id="ithute-tutor", name="Ithute Tutor", is_active=True)
        db.add_all([user, app])
        db.flush()
        auth_session = AuthSession(
            user_id=user.id,
            client_id=app.client_id,
            refresh_token_hash=uuid.uuid4().hex,
            expires_at=now + timedelta(days=1),
        )
        db.add(auth_session)
        db.commit()

        user.is_active = False
        app.is_active = False
        auth_session.revoked_at = utcnow()
        auth_session.revoked_reason = "contract test"
        db.commit()

        rows = db.scalars(select(AuthEventOutbox)).all()
        assert {row.event_type for row in rows} == {
            "account.disabled",
            "application.disabled",
            "session.revoked",
        }
        revoked = next(row for row in rows if row.event_type == "session.revoked")
        assert revoked.subject_user_id == user.id
        assert revoked.session_id == auth_session.id
        assert revoked.client_id == "ithute-tutor"
