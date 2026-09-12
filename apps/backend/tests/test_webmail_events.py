from app.api.v1.webmail_events import _event_cursor, _sse
from app.services.mail_events import probe_lock_key, stream_key


def test_mailbox_stream_key_is_stable_and_does_not_expose_address() -> None:
    first = stream_key("User@Example.com")
    second = stream_key("user@example.com")
    assert first == second
    assert "user@example.com" not in first
    assert first.startswith("webmail:events:")
    assert probe_lock_key("User@Example.com") == probe_lock_key("user@example.com")


def test_replay_cursor_rejects_malformed_values() -> None:
    assert _event_cursor(None) == "$"
    assert _event_cursor("123-0") == "123-0"
    assert _event_cursor(" 123-4 ") == "123-4"
    assert _event_cursor("0-0; DROP TABLE events") == "$"


def test_sse_frame_contains_replay_id_type_and_payload() -> None:
    frame = _sse(
        {
            "id": "123-0",
            "type": "mailbox.changed",
            "at": "2026-09-04T00:00:00+00:00",
            "data": {"folder": "INBOX"},
        }
    )
    assert "id: 123-0" in frame
    assert "event: mailbox.changed" in frame
    assert '"folder":"INBOX"' in frame
    assert frame.endswith("\n\n")
