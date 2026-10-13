import pytest
from app.services.mail_transfer_lifecycle import (
    TransferPrincipal, TransferRecord, TransferState, TransferAccessDenied,
    InvalidTransferTransition, authorize_owner, transition, approve_scan,
)

OWNER = TransferPrincipal("tenant", "mailbox")


def test_owner_isolation():
    record = TransferRecord("tenant", "mailbox", TransferState.CREATED)
    with pytest.raises(TransferAccessDenied):
        authorize_owner(record, TransferPrincipal("other", "mailbox"))
    with pytest.raises(TransferAccessDenied):
        transition(record, TransferPrincipal("tenant", "other"), TransferState.UPLOADING)


def test_quarantine_required_before_send():
    record = TransferRecord("tenant", "mailbox", TransferState.CREATED)
    with pytest.raises(InvalidTransferTransition):
        transition(record, OWNER, TransferState.SENT)
    record = transition(record, OWNER, TransferState.UPLOADING)
    record = transition(record, OWNER, TransferState.QUARANTINED)
    with pytest.raises(InvalidTransferTransition):
        transition(record, OWNER, TransferState.READY)
    record = approve_scan(record, OWNER)
    record = transition(record, OWNER, TransferState.READY)
    assert transition(record, OWNER, TransferState.SENT).state == TransferState.SENT


def test_revocation_is_terminal():
    record = TransferRecord("tenant", "mailbox", TransferState.CREATED)
    record = transition(record, OWNER, TransferState.REVOKED)
    with pytest.raises(InvalidTransferTransition):
        transition(record, OWNER, TransferState.UPLOADING)
