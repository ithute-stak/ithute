import json

from app.config import Settings
from app.schemas import ServiceTokenRequest


def test_service_secret_configuration_is_runtime_only(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_DATABASE_URL", "postgresql+psycopg://unused:unused@localhost/unused")
    monkeypatch.setenv("AUTH_SERVICE_CLIENT_SECRETS_JSON", json.dumps({"loanhub": "x" * 32}))
    settings = Settings()
    assert settings.service_client_secrets == {"loanhub": "x" * 32}


def test_push_service_token_contract() -> None:
    payload = ServiceTokenRequest(client_id="loanhub", client_secret="x" * 32)
    assert payload.audience == "ithute-push"
    assert payload.scope == "push.send"
