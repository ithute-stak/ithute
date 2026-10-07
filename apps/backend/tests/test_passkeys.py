import json

import pytest

from app.services import passkeys


class _Pipeline:
    def __init__(self, store):
        self.store = store
        self.key = None

    def get(self, key):
        self.key = key
        return self

    def delete(self, key):
        self.delete_key = key
        return self

    def execute(self):
        value = self.store.get(self.key)
        self.store.pop(self.delete_key, None)
        return [value, 1 if value is not None else 0]


class _Redis:
    def __init__(self):
        self.store = {}

    def setex(self, key, ttl, value):
        assert ttl == passkeys.PASSKEY_FLOW_TTL_SECONDS
        self.store[key] = value

    def pipeline(self):
        return _Pipeline(self.store)


def test_passkey_flow_is_single_use(monkeypatch):
    fake = _Redis()
    monkeypatch.setattr(passkeys, "_redis", lambda: fake)

    flow_id = passkeys._store_flow("authenticate", {"challenge": "abc"})
    assert passkeys._consume_flow("authenticate", flow_id) == {"challenge": "abc"}

    with pytest.raises(passkeys.PasskeyError, match="invalid or expired"):
        passkeys._consume_flow("authenticate", flow_id)


def test_relying_party_uses_origin_only(monkeypatch):
    monkeypatch.setattr(passkeys.settings, "frontend_url", "https://ithute.co.ls/some/path/")
    monkeypatch.setattr(passkeys.settings, "environment", "production")

    rp_id, origin = passkeys.relying_party()

    assert rp_id == "ithute.co.ls"
    assert origin == "https://ithute.co.ls"


def test_production_passkeys_reject_plain_http(monkeypatch):
    monkeypatch.setattr(passkeys.settings, "frontend_url", "http://ithute.co.ls")
    monkeypatch.setattr(passkeys.settings, "environment", "production")

    with pytest.raises(passkeys.PasskeyError, match="HTTPS"):
        passkeys.relying_party()
