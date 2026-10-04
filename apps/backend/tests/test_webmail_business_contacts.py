from pathlib import Path

from app.services import webmail_polish


class _FakeRedis:
    def __init__(self):
        self.values: dict[str, str] = {}

    def setex(self, key: str, ttl: int, value: str):
        assert ttl == webmail_polish.PRESENCE_TTL_SECONDS
        self.values[key] = value

    def mget(self, keys: list[str]):
        return [self.values.get(key) for key in keys]


def test_presence_only_marks_active_imail_sessions(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(webmail_polish, "_redis", lambda: fake)

    webmail_polish.touch_presence("Person@Example.com")
    presence = webmail_polish.contact_presence(["person@example.com", "external@example.net"])

    assert presence["person@example.com"] is True
    assert presence["external@example.net"] is False


def test_business_contact_routes_and_sidebar_contract_exist():
    root = Path(__file__).parents[2]
    api_source = (root / "app" / "api" / "v1" / "webmail.py").read_text(encoding="utf-8")
    ui_source = (root.parent / "frontend" / "app" / "webmail" / "hosted-workspace.tsx").read_text(encoding="utf-8")

    assert '@router.get("/business-contacts")' in api_source
    assert '@router.get("/business-conversation")' in api_source
    assert "Business contacts" in ui_source
    assert "Online now" in ui_source
    assert "business-conversation" in ui_source
