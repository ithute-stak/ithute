from unittest.mock import MagicMock, patch

import pytest

from app.services.mailbox_events import _key, publish_mailbox_change, read_mailbox_changes


def test_mailbox_key_is_normalized_and_private():
    assert _key(" Alice@Example.com ") == _key("alice@example.com")
    assert "alice@example.com" not in _key("alice@example.com")
    assert _key("alice@example.com") != _key("bob@example.com")


def test_rejects_invalid_event_inputs():
    with pytest.raises(ValueError):
        _key("")
    with pytest.raises(ValueError):
        publish_mailbox_change("alice@example.com", "arbitrary")
    with pytest.raises(ValueError):
        read_mailbox_changes("alice@example.com", since="bad cursor")


@patch("app.services.mailbox_events.redis.Redis.from_url")
def test_publishes_to_scoped_stream(mock_from_url):
    client = MagicMock()
    client.xadd.return_value = "123-0"
    mock_from_url.return_value = client
    assert publish_mailbox_change("ALICE@example.com", "flags_changed") == "123-0"
    args, kwargs = client.xadd.call_args
    assert args[0] == _key("alice@example.com")
    assert args[1] == {"kind": "flags_changed"}
    assert kwargs["maxlen"] == 1000


@patch("app.services.mailbox_events.redis.Redis.from_url")
def test_reads_limited_replay(mock_from_url):
    client = MagicMock()
    client.xrange.return_value = [("124-0", {"kind": "changed"})]
    mock_from_url.return_value = client
    assert read_mailbox_changes("alice@example.com", "123-0", 500) == [{"id": "124-0", "kind": "changed"}]
    assert client.xrange.call_args.kwargs == {"min": "(123-0", "max": "+", "count": 200}
