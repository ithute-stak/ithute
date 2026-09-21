import pytest

from app.services import webmail


class FakeMailbox:
    def __init__(self):
        self.selected = None
        self.logout_calls = 0

    def select(self, folder, readonly=False):
        self.selected = (folder, readonly)
        return "OK", [b"2"]

    def uid(self, command, *args):
        if command == "search":
            return "OK", [b"1 2"]
        raise AssertionError(f"unexpected IMAP command: {command}")

    def logout(self):
        self.logout_calls += 1
        return "BYE", []


def test_binary_single_part_message_is_rendered_as_text():
    raw = (
        b"From: sender@example.com\r\n"
        b"To: person@example.com\r\n"
        b"Subject: Binary body\r\n"
        b"Content-Type: application/octet-stream\r\n"
        b"\r\n"
        b"\xff\x00binary payload"
    )

    row = webmail._message_json("42", raw, b"42 (FLAGS (\\Seen))", include_body=True)

    assert row["uid"] == "42"
    assert row["subject"] == "Binary body"
    assert isinstance(row["body_text"], str)
    assert "binary payload" in row["body_text"]
    assert "binary payload" in row["snippet"]


def test_messages_skips_one_unreadable_message_without_breaking_inbox(monkeypatch):
    client = FakeMailbox()
    monkeypatch.setattr(webmail, "_imap", lambda *_: client)

    def fake_fetch(_client, uid, mark_seen=False):
        assert mark_seen is False
        return f"Subject: message {uid}\r\n\r\nbody".encode(), b""

    real_message_json = webmail._message_json

    def fake_message_json(uid, raw, meta=b"", include_body=False):
        if uid == "2":
            raise ValueError("malformed MIME")
        return real_message_json(uid, raw, meta, include_body)

    monkeypatch.setattr(webmail, "_fetch_raw", fake_fetch)
    monkeypatch.setattr(webmail, "_message_json", fake_message_json)

    result = webmail.messages("person@example.com", "secret")

    assert result["total"] == 2
    assert result["skipped"] == 1
    assert [item["uid"] for item in result["items"]] == ["1"]
    assert client.logout_calls == 1


def test_message_converts_parser_failure_to_webmail_error(monkeypatch):
    client = FakeMailbox()
    monkeypatch.setattr(webmail, "_imap", lambda *_: client)
    monkeypatch.setattr(webmail, "_fetch_raw", lambda *_args, **_kwargs: (b"broken", b""))
    monkeypatch.setattr(webmail, "_message_json", lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("broken MIME")))

    with pytest.raises(webmail.WebmailError, match="Unable to read message"):
        webmail.message("person@example.com", "secret", "9")

    assert client.logout_calls == 1
