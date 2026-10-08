"""Contract tests for the production live-mail event transport."""
from unittest.mock import MagicMock, patch

from app.api.v1.webmail_events import _event_cursor, _sse
from app.services.mail_events import publish_mail_event, stream_key


def test_streams_are_account_scoped_and_address_is_not_exposed():
    alice = stream_key("Alice@Example.com")
    assert alice == stream_key(" alice@example.com ")
    assert alice != stream_key("bob@example.com")
    assert "alice" not in alice


def test_resume_cursor_rejects_malformed_input():
    assert _event_cursor("123-0") == "123-0"
    assert _event_cursor("$") == "$"
    assert _event_cursor("123-0\\nmalicious") == "$"
    assert _event_cursor("bad") == "$"


def test_sse_encodes_one_event_with_replay_id():
    result = _sse({"id": "123-0", "type": "mailbox.changed", "data": {"source": "test"}})
    assert result.startswith("id: 123-0\\nevent: mailbox.changed\\ndata: ")
    assert result.endswith("\\n\\n")
    assert '"source":"test"' in result


@patch("app.services.mail_events.redis.Redis.from_url")
def test_authoritative_publish_uses_scoped_stream(mock_from_url):
    client = MagicMock()
    client.xadd.return_value = "123-1"
    mock_from_url.return_value = client
    assert publish_mail_event("alice@example.com", "mailbox.changed", {"source": "test"}) == "123-1"
    args, kwargs = client.xadd.call_args
    assert args[0] == stream_key("alice@example.com")
    assert kwargs["maxlen"] >= 100
    client.close.assert_called_once()
