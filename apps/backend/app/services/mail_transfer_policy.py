"""Decision policy for iMail attachments and secure large-file transfers.

This policy never authorizes delivery on its own. Secure-link delivery
requires a separately implemented, authenticated, scanned storage workflow.
"""
from dataclasses import dataclass
from enum import Enum

MIB = 1024 * 1024
MAX_INLINE_FILE_BYTES = 10 * MIB
MAX_INLINE_TOTAL_BYTES = 15 * MIB
MAX_INLINE_FILE_COUNT = 20
MAX_SECURE_TRANSFER_FILE_BYTES = 2 * 1024 * MIB
MAX_SECURE_TRANSFER_TOTAL_BYTES = 5 * 1024 * MIB


class TransferMode(str, Enum):
    INLINE = "inline"
    SECURE_LINK = "secure_link"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class FileDescriptor:
    name: str
    size: int


@dataclass(frozen=True)
class TransferDecision:
    mode: TransferMode
    reason: str
    total_bytes: int


def choose_transfer_mode(files: list[FileDescriptor]) -> TransferDecision:
    """Choose a delivery *plan*, not permission to upload or send."""
    if any(not item.name or item.size < 0 for item in files):
        return TransferDecision(TransferMode.UNSUPPORTED, "invalid_file", 0)
    total = sum(item.size for item in files)
    if not files:
        return TransferDecision(TransferMode.INLINE, "no_files", 0)
    if any(item.size > MAX_SECURE_TRANSFER_FILE_BYTES for item in files):
        return TransferDecision(TransferMode.UNSUPPORTED, "per_file_hard_limit", total)
    if total > MAX_SECURE_TRANSFER_TOTAL_BYTES:
        return TransferDecision(TransferMode.UNSUPPORTED, "aggregate_hard_limit", total)
    if len(files) <= MAX_INLINE_FILE_COUNT and total <= MAX_INLINE_TOTAL_BYTES and all(
        item.size <= MAX_INLINE_FILE_BYTES for item in files
    ):
        return TransferDecision(TransferMode.INLINE, "smtp_compatible", total)
    return TransferDecision(TransferMode.SECURE_LINK, "secure_transfer_required", total)
