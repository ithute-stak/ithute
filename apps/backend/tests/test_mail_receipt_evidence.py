from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.services.mail_receipt_evidence import record_unverified_receipt


def test_receipt_persistence_is_unverified_and_scoped():
    db = MagicMock()
    db.scalar.return_value = None
    mailbox_id = uuid4()
    row = record_unverified_receipt(
        db, mailbox_id=mailbox_id, original_message_id="<id@example.com>",
        recipient="Recipient@example.com", disposition="displayed",
        raw_evidence=b"untrusted external mdn",
    )
    assert row.mailbox_id == mailbox_id
    assert row.evidence_status == "unverified_read_claim"
    assert row.recipient == "recipient@example.com"
    db.add.assert_called_once_with(row)
    db.flush.assert_called_once()


def test_duplicate_evidence_is_not_inserted_again():
    db = MagicMock()
    previous = object()
    db.scalar.return_value = previous
    result = record_unverified_receipt(
        db, mailbox_id=uuid4(), original_message_id="<id@example.com>",
        recipient="recipient@example.com", disposition="displayed",
        raw_evidence=b"same receipt",
    )
    assert result is previous
    db.add.assert_not_called()


@pytest.mark.parametrize("disposition", ["invalid", "", "READ"])
def test_invalid_disposition_is_rejected(disposition):
    with pytest.raises(ValueError):
        record_unverified_receipt(
            MagicMock(), mailbox_id=uuid4(), original_message_id="<id@example.com>",
            recipient="recipient@example.com", disposition=disposition,
            raw_evidence=b"receipt",
        )
