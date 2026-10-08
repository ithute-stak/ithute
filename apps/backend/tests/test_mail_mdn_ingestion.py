from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.services.mail_mdn_ingestion import ingest_unverified_mdn


def test_ingestion_does_not_persist_unowned_receipt():
    db = MagicMock()
    with patch("app.services.mail_mdn_ingestion.attribute_receipt", return_value=None), patch(
        "app.services.mail_mdn_ingestion.record_unverified_receipt"
    ) as save:
        result = ingest_unverified_mdn(
            db, mailbox_id=uuid4(), raw=b"not an MDN",
            sent_message_id="<sent@example.com>", sent_message_owned=False,
            expected_recipient="r@example.com", reported_recipient="r@example.com",
        )
    assert result is None
    save.assert_not_called()


def test_ingestion_does_not_promote_external_claim_to_confirmed():
    db = MagicMock()
    attribution = MagicMock(original_message_id="<sent@example.com>", recipient="r@example.com")
    with patch("app.services.mail_mdn_ingestion.attribute_receipt", return_value=attribution), patch(
        "app.services.mail_mdn.parse_mdn", return_value={"disposition": "displayed"}
    ), patch("app.services.mail_mdn_ingestion.record_unverified_receipt") as save:
        ingest_unverified_mdn(
            db, mailbox_id=uuid4(), raw=b"receipt",
            sent_message_id="<sent@example.com>", sent_message_owned=True,
            expected_recipient="r@example.com", reported_recipient="r@example.com",
        )
    assert save.call_count == 1
    assert save.call_args.kwargs["disposition"] == "displayed"


def test_missing_authenticated_mailbox_never_persists_receipt():
    db = MagicMock()
    with patch("app.services.mail_mdn_ingestion.record_unverified_receipt") as save:
        result = ingest_unverified_mdn(
            db, mailbox_id=None, raw=b"anything",
            sent_message_id="<sent@example.com>", sent_message_owned=True,
            expected_recipient="r@example.com", reported_recipient="r@example.com",
        )
    assert result is None
    save.assert_not_called()
