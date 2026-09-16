from __future__ import annotations

import fcntl
import hashlib
import os
import tempfile
from pathlib import Path

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.models.mail import Mailbox, MailboxStatus


class MailAccountSyncError(RuntimeError):
    """Raised when the live Docker Mailserver account files cannot be synchronized."""


_listener_installed = False
_FORWARDING_MARKER_PREFIX = "# platform-forwarding-revision:"
_FORWARDING_READY_MARKER = ".recipient-bcc-ready"


def _accounts_path() -> Path | None:
    raw = os.getenv("MAIL_ACCOUNTS_FILE", "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        raise MailAccountSyncError("MAIL_ACCOUNTS_FILE must be an absolute path")
    return path


def _forwarding_path() -> Path | None:
    accounts = _accounts_path()
    if accounts is None:
        return None
    raw = os.getenv("MAIL_FORWARDING_FILE", "").strip()
    path = Path(raw) if raw else accounts.parent / "postfix-recipient-bcc.cf"
    if not path.is_absolute():
        raise MailAccountSyncError("MAIL_FORWARDING_FILE must be an absolute path")
    if path.parent != accounts.parent:
        raise MailAccountSyncError("MAIL_FORWARDING_FILE must share the MAIL_ACCOUNTS_FILE directory")
    if path == accounts:
        raise MailAccountSyncError("MAIL_FORWARDING_FILE must not overwrite MAIL_ACCOUNTS_FILE")
    return path


def _atomic_write(path: Path, payload: str, *, prefix: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=prefix, dir=path.parent)
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


def _validate_account(address: str, password_hash: str) -> tuple[str, str]:
    clean_address = address.strip().lower()
    clean_hash = password_hash.strip()
    if not clean_address or "@" not in clean_address or any(char in clean_address for char in "|\r\n"):
        raise MailAccountSyncError("Mailbox address is invalid for Docker Mailserver synchronization")
    if not clean_hash.startswith("{SHA512-CRYPT}$6$") or any(char in clean_hash for char in "|\r\n"):
        raise MailAccountSyncError("Mailbox password hash is not a supported Docker Mailserver SHA512-CRYPT value")
    return clean_address, clean_hash


def _validate_forwarding_destination(address: str, destination: str) -> tuple[str, str]:
    clean_address = address.strip().lower()
    clean_destination = destination.strip().lower()
    for value in (clean_address, clean_destination):
        if not value or "@" not in value or any(char.isspace() for char in value) or any(char in value for char in "\r\n"):
            raise MailAccountSyncError("Mailbox forwarding address is invalid")
    if clean_address == clean_destination:
        raise MailAccountSyncError("Mailbox cannot forward to itself")
    return clean_address, clean_destination


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
            _atomic_write(path, payload, prefix=".postfix-accounts.")
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


def sync_mailbox_forwarding(mailbox: Mailbox, destination: str | None) -> bool:
    """Keep the mailbox local and add/remove one Postfix recipient BCC copy.

    Docker Mailserver v15.1 monitors ``postfix-accounts.cf`` and reloads Postfix
    when that file changes. The forwarding map itself lives beside the isolated
    account file, so the application never needs access to the wider DMS config
    directory. A deterministic revision comment in the account file is updated
    whenever the map changes, causing DMS to reload Postfix and reopen the
    ``texthash`` recipient BCC map without restarting the mail container.

    The runtime installer creates ``.recipient-bcc-ready`` only after Postfix
    reports the exact expected ``recipient_bcc_maps`` setting. Until that proof
    exists this method returns ``False`` and production API calls fail closed.
    """

    accounts_path = _accounts_path()
    forwarding_path = _forwarding_path()
    if accounts_path is None or forwarding_path is None:
        return False
    if not (accounts_path.parent / _FORWARDING_READY_MARKER).is_file():
        return False

    clean_address = mailbox.address.strip().lower()
    clean_destination: str | None = None
    if destination and mailbox.status == MailboxStatus.active:
        clean_address, clean_destination = _validate_forwarding_destination(mailbox.address, destination)
    elif not clean_address or "@" not in clean_address or any(char.isspace() for char in clean_address):
        raise MailAccountSyncError("Mailbox forwarding address is invalid")

    try:
        accounts_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = accounts_path.parent / ".postfix-accounts.lock"
        with lock_path.open("a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)

            existing = forwarding_path.read_text(encoding="utf-8").splitlines() if forwarding_path.exists() else []
            kept: list[str] = []
            for line in existing:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    kept.append(line)
                    continue
                candidate = stripped.split(None, 1)[0].lower()
                if candidate == clean_address:
                    continue
                kept.append(line)
            if clean_destination:
                kept.append(f"{clean_address} {clean_destination}")

            forwarding_payload = "\n".join(kept)
            if forwarding_payload:
                forwarding_payload += "\n"
            _atomic_write(forwarding_path, forwarding_payload, prefix=".postfix-recipient-bcc.")

            revision = hashlib.sha256(forwarding_payload.encode("utf-8")).hexdigest()
            account_lines = accounts_path.read_text(encoding="utf-8").splitlines() if accounts_path.exists() else []
            account_lines = [line for line in account_lines if not line.startswith(_FORWARDING_MARKER_PREFIX)]
            account_lines.append(f"{_FORWARDING_MARKER_PREFIX}{revision}")
            account_payload = "\n".join(account_lines)
            if account_payload:
                account_payload += "\n"
            _atomic_write(accounts_path, account_payload, prefix=".postfix-accounts.")

            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        return True
    except OSError as exc:
        raise MailAccountSyncError(f"Unable to synchronize forwarding for {clean_address}") from exc


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
