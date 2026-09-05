import os
import time
import uuid

import pytest
from cryptography.fernet import Fernet

os.environ.setdefault("PUSH_DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("PUSH_ENDPOINT_ENCRYPTION_KEY", Fernet.generate_key().decode())

from app.auth import AuthError, AuthVerifier
from app.config import Settings
from app.server import app


def _verifier() -> AuthVerifier:
    return AuthVerifier(
        Settings(
            database_url="sqlite://",
            endpoint_encryption_key=Fernet.generate_key().decode(),
        )
    )


def _claims(*, seconds: int = 120, client: str = "mailbox-dns") -> dict[str, object]:
    now = int(time.time())
    return {
        "iss": "https://auth.ithute.co.ls",
        "sub": str(uuid.uuid4()),
        "aud": "ithute-push",
        "azp": client,
        "sid": str(uuid.uuid4()),
        "scope": "push.admin",
        "token_use": "push_admin",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "nbf": now,
        "exp": now + seconds,
    }


def test_push_admin_token_is_human_bound_and_console_scoped() -> None:
    verifier = _verifier()
    claims = _claims()
    verifier._decode = lambda token, required: claims
    principal = verifier.admin("ignored")
    assert principal.client_id == "mailbox-dns"
    assert principal.sub == claims["sub"]
    assert principal.session_id == claims["sid"]


def test_product_and_service_tokens_cannot_be_used_as_admin_tokens() -> None:
    verifier = _verifier()
    for token_use, scope in (("push_access", "push.device"), ("service", "push.send")):
        claims = {**_claims(), "token_use": token_use, "scope": scope}
        verifier._decode = lambda token, required, claims=claims: claims
        with pytest.raises(AuthError):
            verifier.admin("ignored")


def test_only_mailbox_console_may_receive_push_admin_authority() -> None:
    verifier = _verifier()
    claims = _claims(client="ithute-tutor")
    verifier._decode = lambda token, required: claims
    with pytest.raises(AuthError, match="unapproved"):
        verifier.admin("ignored")


def test_push_admin_token_lifetime_is_strictly_capped() -> None:
    verifier = _verifier()
    claims = _claims(seconds=181)
    verifier._decode = lambda token, required: claims
    with pytest.raises(AuthError, match="lifetime"):
        verifier.admin("ignored")


def test_production_server_registers_privileged_routes() -> None:
    paths = {path for route in app.routes if (path := getattr(route, "path", None)) is not None}
    assert "/v1/admin/overview" in paths
    assert "/v1/admin/applications" in paths
    assert "/v1/admin/messages" in paths
