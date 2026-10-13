"""Server-side state rules for resumable, quarantined iMail file transfers.

Pure transition contract. No public upload/download API is exposed by this module.
"""
from dataclasses import dataclass
from enum import Enum


class TransferState(str, Enum):
    CREATED = "created"
    UPLOADING = "uploading"
    QUARANTINED = "quarantined"
    READY = "ready"
    SENT = "sent"
    EXPIRED = "expired"
    REVOKED = "revoked"
    FAILED = "failed"


_ALLOWED = {
    TransferState.CREATED: frozenset({TransferState.UPLOADING, TransferState.REVOKED, TransferState.EXPIRED, TransferState.FAILED}),
    TransferState.UPLOADING: frozenset({TransferState.QUARANTINED, TransferState.REVOKED, TransferState.EXPIRED, TransferState.FAILED}),
    TransferState.QUARANTINED: frozenset({TransferState.READY, TransferState.REVOKED, TransferState.EXPIRED, TransferState.FAILED}),
    TransferState.READY: frozenset({TransferState.SENT, TransferState.REVOKED, TransferState.EXPIRED, TransferState.FAILED}),
    TransferState.SENT: frozenset({TransferState.REVOKED, TransferState.EXPIRED}),
    TransferState.REVOKED: frozenset(),
    TransferState.EXPIRED: frozenset(),
    TransferState.FAILED: frozenset(),
}


@dataclass(frozen=True)
class TransferPrincipal:
    tenant_id: str
    mailbox_id: str


@dataclass(frozen=True)
class TransferRecord:
    tenant_id: str
    mailbox_id: str
    state: TransferState
    scan_clean: bool = False


class TransferAccessDenied(PermissionError):
    pass


class InvalidTransferTransition(ValueError):
    pass


def authorize_owner(transfer: TransferRecord, principal: TransferPrincipal) -> None:
    if not (principal.tenant_id and principal.mailbox_id):
        raise TransferAccessDenied("Transfer owner is not authenticated")
    if transfer.tenant_id != principal.tenant_id or transfer.mailbox_id != principal.mailbox_id:
        raise TransferAccessDenied("Transfer is not owned by this mailbox")


def transition(
    transfer: TransferRecord, principal: TransferPrincipal, target: TransferState
) -> TransferRecord:
    authorize_owner(transfer, principal)
    if target == transfer.state:
        return transfer
    if target not in _ALLOWED[transfer.state]:
        raise InvalidTransferTransition("Invalid transfer state transition")
    if target in {TransferState.READY, TransferState.SENT} and not transfer.scan_clean:
        raise InvalidTransferTransition("File scan approval is required")
    return TransferRecord(
        tenant_id=transfer.tenant_id,
        mailbox_id=transfer.mailbox_id,
        state=target,
        scan_clean=transfer.scan_clean,
    )


def approve_scan(transfer: TransferRecord, principal: TransferPrincipal) -> TransferRecord:
    """Only an internal, trusted scanner should call this; never expose as an API."""
    authorize_owner(transfer, principal)
    if transfer.state != TransferState.QUARANTINED:
        raise InvalidTransferTransition("Scan approval requires quarantine")
    return TransferRecord(transfer.tenant_id, transfer.mailbox_id, transfer.state, True)
