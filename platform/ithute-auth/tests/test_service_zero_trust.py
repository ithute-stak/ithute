import os
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("AUTH_DATABASE_URL", "sqlite://")

from app.models import utcnow
from app.service_clients import create_service_credential


class FakeDb:
    def __init__(self):
        self.added = []

    def add(self, value):
        self.added.append(value)

    def flush(self):
        return None


def test_managed_service_credentials_expire_by_default():
    db = FakeDb()
    client = SimpleNamespace(id="client-id")
    before = utcnow()

    credential, secret = create_service_credential(db, client=client)

    assert secret.startswith("ithute_svc_")
    assert credential.expires_at is not None
    assert before + timedelta(days=29) < credential.expires_at <= before + timedelta(days=31)


def test_production_disables_legacy_service_secret_fallback():
    compose = (Path(__file__).parents[3] / "compose.production.yml").read_text(encoding="utf-8")
    assert 'AUTH_ALLOW_LEGACY_SERVICE_SECRETS: "false"' in compose

    source = (Path(__file__).parents[1] / "app" / "service_token_api.py").read_text(encoding="utf-8")
    assert "managed service credentials required" in source
    assert "allow_legacy_service_secrets" in source
