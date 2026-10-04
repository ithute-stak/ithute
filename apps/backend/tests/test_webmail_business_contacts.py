from pathlib import Path

from app.services import webmail_polish


class _FakeRedis:
    def __init__(self):
        self.values: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.lists: dict[str, list[str]] = {}

    def setex(self, key: str, ttl: int, value: str):
        assert ttl == webmail_polish.PRESENCE_TTL_SECONDS
        self.values[key] = value

    def mget(self, keys: list[str]):
        return [self.values.get(key) for key in keys]

    def hget(self, key: str, field: str):
        return self.hashes.get(key, {}).get(field)

    def hset(self, key: str, field: str, value: str):
        self.hashes.setdefault(key, {})[field] = value

    def hgetall(self, key: str):
        return dict(self.hashes.get(key, {}))

    def lpush(self, key: str, value: str):
        self.lists.setdefault(key, []).insert(0, value)

    def rpush(self, key: str, value: str):
        self.lists.setdefault(key, []).append(value)

    def ltrim(self, key: str, start: int, end: int):
        rows = self.lists.setdefault(key, [])
        if start < 0:
            start = max(0, len(rows) + start)
        if end < 0:
            end = len(rows) + end
        self.lists[key] = rows[start : end + 1]

    def lrange(self, key: str, start: int, end: int):
        rows = self.lists.get(key, [])
        if start < 0:
            start = max(0, len(rows) + start)
        if end < 0:
            end = len(rows) + end
        return rows[start : end + 1]


def test_presence_only_marks_active_imail_sessions(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(webmail_polish, "_redis", lambda: fake)

    webmail_polish.touch_presence("Person@Example.com")
    presence = webmail_polish.contact_presence(["person@example.com", "external@example.net"])

    assert presence["person@example.com"] is True
    assert presence["external@example.net"] is False


def test_relationship_metadata_notes_tasks_pin_and_internal_chat(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(webmail_polish, "_redis", lambda: fake)

    webmail_polish.save_contact("owner@ithute.co.ls", "client@example.com", "Client")
    pinned = webmail_polish.set_contact_pinned("owner@ithute.co.ls", "client@example.com", True)
    note = webmail_polish.add_relationship_note("owner@ithute.co.ls", "client@example.com", "Quotation sent")
    task = webmail_polish.add_relationship_task("owner@ithute.co.ls", "client@example.com", "Follow up", "2026-10-05T09:00")
    chat = webmail_polish.send_internal_chat("owner@ithute.co.ls", "colleague@ithute.co.ls", "Are you online?")

    contact = webmail_polish.contacts("owner@ithute.co.ls")[0]
    assert pinned["pinned"] is True
    assert contact["pinned"] is True
    assert contact["domain"] == "example.com"
    assert note["text"] == "Quotation sent"
    assert webmail_polish.relationship_notes("owner@ithute.co.ls", "client@example.com")[0]["text"] == "Quotation sent"
    assert task["text"] == "Follow up"
    assert webmail_polish.relationship_tasks("owner@ithute.co.ls", "client@example.com")[0]["due_at"] == "2026-10-05T09:00"
    assert chat["to"] == "colleague@ithute.co.ls"
    assert webmail_polish.internal_chat_messages("owner@ithute.co.ls", "colleague@ithute.co.ls")[0]["text"] == "Are you online?"


def test_internal_chat_rejects_external_domains(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(webmail_polish, "_redis", lambda: fake)

    try:
        webmail_polish.send_internal_chat("owner@ithute.co.ls", "external@example.com", "hello")
    except webmail_polish.WebmailError as exc:
        assert "same company domain" in str(exc)
    else:
        raise AssertionError("external-domain chat should be rejected")


def test_business_contact_routes_and_workspace_contract_exist():
    root = Path(__file__).parents[2]
    api_source = (root / "app" / "api" / "v1" / "webmail.py").read_text(encoding="utf-8")
    ui_source = (root.parent / "frontend" / "app" / "webmail" / "hosted-workspace.tsx").read_text(encoding="utf-8")
    workspace_source = (root.parent / "frontend" / "app" / "webmail" / "business-contact-workspace.tsx").read_text(encoding="utf-8")

    assert '@router.get("/business-contacts")' in api_source
    assert '@router.get("/business-conversation")' in api_source
    assert '@router.get("/business-workspace")' in api_source
    assert '@router.put("/business-contacts/pin")' in api_source
    assert '@router.post("/business-notes"' in api_source
    assert '@router.post("/business-tasks"' in api_source
    assert '@router.post("/business-chat"' in api_source
    assert "Business contacts" in ui_source
    assert "contactGroups" in ui_source
    assert "BusinessContactWorkspace" in ui_source
    assert '"documents"' in workspace_source
    assert '"people"' in workspace_source
    assert '"notes"' in workspace_source
    assert '"activity"' in workspace_source
    assert '"chat"' in workspace_source
