from __future__ import annotations

import fcntl
import os
import tempfile
from pathlib import Path

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.mail import Mailbox, MailboxStatus


class MailAccountSyncError(RuntimeError):
    """Raised when the live Docker Mailserver account file cannot be synchronized."""


_listener_installed = False


def _accounts_path() -> Path | None:
    raw = settings.mail_accounts_file
    if not raw:
        return None
    return Path(raw)


def _validate_account(address: str, password_hash: str) -> tuple[str, str]:
    clean_address = address.strip().lower()
    clean_hash = password_hash.strip()
    if not clean_address or "@" not in clean_address or any(char in clean_address for char in "|\r\n"):
        raise MailAccountSyncError("Mailbox address is invalid for Docker Mailserver synchronization")
    if not clean_hash.startswith("{SHA512-CRYPT}$6$") or any(char in clean_hash for char in "|\r\n"):
        raise MailAccountSyncError("Mailbox password hash is not a supported Docker Mailserver SHA512-CRYPT value")
    return clean_address, clean_hash


def _write_account(address: str, password_hash: str, *, active: bool) -> bool:
    path = _accounts_path()
    if path is None:
        return False

    clean_address, clean_hash = _validate_account(address, password_hash)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = path.parent / ".postfix-accounts.lock"
        with lock_path.open("a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
            kept: list[str] = []
            for line in existing:
                candidate = line.split("|", 1)[0].strip().lower() if "|" in line else ""
                if candidate == clean_address:
                    continue
                kept.append(line)
            if active:
                kept.append(f"{clean_address}|{clean_hash}")

            payload = "\n".join(kept)
            if payload:
                payload += "\n"
            fd, temporary = tempfile.mkstemp(prefix=".postfix-accounts.", dir=path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.chmod(temporary, 0o600)
                os.replace(temporary, path)
                directory_fd = os.open(path.parent, os.O_DIRECTORY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        return True
    except OSError as exc:
        raise MailAccountSyncError(f"Unable to synchronize mailbox {clean_address} with the live mail server") from exc


def sync_mailbox(mailbox: Mailbox, *, deleted: bool = False) -> bool:
    return _write_account(
        mailbox.address,
        mailbox.password_hash,
        active=not deleted and mailbox.status == MailboxStatus.active,
    )


def reconcile_mail_accounts(db: Session) -> int:
    """Make application-managed mailbox rows authoritative for their matching DMS accounts.

    Accounts that are owned only by the independent mail stack are preserved because
    synchronization replaces/removes only addresses represented by application rows.
    """

    if _accounts_path() is None:
        return 0
    mailboxes = db.scalars(select(Mailbox).order_by(Mailbox.address)).all()
    for mailbox in mailboxes:
        sync_mailbox(mailbox)
    return len(mailboxes)


def _sync_after_flush(session: Session, _flush_context) -> None:
    if _accounts_path() is None:
        return
    for mailbox in tuple(session.new) + tuple(session.dirty):
        if isinstance(mailbox, Mailbox):
            sync_mailbox(mailbox)
    for mailbox in tuple(session.deleted):
        if isinstance(mailbox, Mailbox):
            sync_mailbox(mailbox, deleted=True)


def install_mailbox_runtime_sync() -> None:
    global _listener_installed
    if _listener_installed:
        return
    event.listen(Session, "after_flush", _sync_after_flush)
    _listener_installed = True
