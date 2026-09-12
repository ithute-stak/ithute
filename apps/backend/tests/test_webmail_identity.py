from app.main import app
from app.services import webmail


class FakeRedis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value
        return True

    def delete(self, key):
        self.values.pop(key, None)
        return 1


def test_display_name_round_trip_and_sender_header(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(webmail, "_redis", lambda: fake)

    result = webmail.save_display_name("info@example.com", "  Example   Company  ")

    assert result == {"saved": True, "display_name": "Example Company"}
    assert webmail.display_name("info@example.com") == "Example Company"
    assert webmail.sender_header("info@example.com") == "Example Company <info@example.com>"


def test_display_name_removes_header_newlines(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(webmail, "_redis", lambda: fake)

    webmail.save_display_name("info@example.com", "Example\r\nCompany")

    assert webmail.sender_header("info@example.com") == "Example Company <info@example.com>"


def test_identity_routes_are_exposed():
    paths = set(app.openapi().get("paths", {}))
    assert "/api/v1/webmail/identity" in paths
