"""Verify receipt history stays scoped to the authenticated mailbox."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.api.v1.webmail_productivity import read_receipt_evidence


def test_history_queries_only_authenticated_mailbox_and_requested_message():
    mailbox = SimpleNamespace(id=uuid4())
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    with patch("app.api.v1.webmail_productivity._owner", return_value=(mailbox, "secret")):
        result = read_receipt_evidence("<message@example.com>", token="session", db=db)

    statement = db.scalars.call_args.args[0]
    parameters = list(statement.compile().params.values())
    assert mailbox.id in parameters
    assert "<message@example.com>" in parameters
    assert result["read_confirmed"] is False
    assert result["items"] == []
