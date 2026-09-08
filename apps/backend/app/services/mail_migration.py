import hashlib
import imaplib
import os
import re
import shutil
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Mailbox

_PROVIDER_DEFAULTS = {
    "google": ("imap.gmail.com", 993),
    "microsoft365": ("outlook.office365.com", 993),
    "office365": ("outlook.office365.com", 993),
}


def provider_endpoint(provider: str, host: str | None, port: int | None) -> tuple[str, int]:
    key = provider.strip().lower()
    if key in _PROVIDER_DEFAULTS:
        return _PROVIDER_DEFAULTS[key]
    if not host:
        raise ValueError("source_host is required for generic IMAP/cPanel migrations")
    return host.strip(), int(port or 993)


def _xoauth2(username: str, token: str) -> bytes:
    return f"user={username}\x01auth=Bearer {token}\x01\x01".encode("utf-8")


def _folder_pair(raw: bytes | str) -> tuple[str, str]:
    """Return the original IMAP folder name plus a safe Maildir folder name.

    Keeping the original source name is important for Gmail special folders such
    as ``[Gmail]/All Mail``; the previous migration code sanitized the name and
    then attempted to SELECT the sanitized value on Gmail.
    """
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
    match = re.search(r' (?:"((?:[^"\\]|\\.)*)"|([^\s]+))$', text)
    source = (match.group(1) or match.group(2)) if match else "INBOX"
    source = source.replace('\\"', '"').replace("\\\\", "\\")
    if source.upper() == "INBOX":
        return "INBOX", ""
    safe = source.replace("/", ".").replace("\\", ".")
    safe = re.sub(r"[^A-Za-z0-9_. -]+", "_", safe).strip(". ")
    return source, safe[:180] or "Imported"


def _maildir_for(address: str, folder: str) -> Path:
    local, domain = address.lower().split("@", 1)
    base = Path(settings.mail_data_path) / domain / local / "Maildir"
    return base if not folder else base / f".{folder}"


def _maildir_root(address: str) -> Path:
    return _maildir_for(address, "")


def _maildir_size(root: Path) -> int:
    if not root.exists():
        return 0
    total = 0
    for path in root.rglob("*"):
        try:
            if path.is_file():
                total += path.stat().st_size
        except (FileNotFoundError, PermissionError, OSError):
            continue
    return total


def _configured_quota(address: str) -> int | None:
    """Read the authoritative hosted-mailbox quota when the destination is local."""
    with SessionLocal() as db:
        value = db.scalar(select(Mailbox.quota_bytes).where(Mailbox.address == address.strip().lower()))
    return int(value) if value is not None and int(value) > 0 else None


def _maildir_flags(meta: bytes | str) -> str:
    text = meta.decode("utf-8", "replace") if isinstance(meta, bytes) else str(meta)
    mapping = (
        ("\\Draft", "D"),
        ("\\Flagged", "F"),
        ("\\Answered", "R"),
        ("\\Seen", "S"),
        ("\\Deleted", "T"),
    )
    return "".join(letter for flag, letter in mapping if flag in text)


def _ensure_maildir(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    try:
        os.chown(target, 5000, 5000)
    except FileNotFoundError:
        pass
    for sub in ("tmp", "new", "cur"):
        path = target / sub
        path.mkdir(parents=True, exist_ok=True)
        os.chown(path, 5000, 5000)


def _already_imported(target: Path, marker: str) -> bool:
    for sub in ("new", "cur"):
        path = target / sub
        if path.exists() and any(path.glob(f"migrated.{marker}.migration*")):
            return True
    return False


def _write_maildir_message(target: Path, raw_message: bytes, meta: bytes | str = b"") -> bool:
    """Write one raw message using a deterministic migration marker.

    Deterministic filenames make migrations safe to resume or repeat: the same
    source message in the same destination folder is skipped rather than copied
    again. Standard IMAP flags are carried into the Maildir ``:2,`` suffix.
    """
    _ensure_maildir(target)
    digest = hashlib.sha256(raw_message).hexdigest()
    marker = digest[:32]
    if _already_imported(target, marker):
        return False

    flags = _maildir_flags(meta)
    filename = f"migrated.{marker}.migration"
    sub = "cur" if flags else "new"
    if flags:
        filename += f":2,{flags}"
    path = target / sub / filename
    path.write_bytes(raw_message)
    os.chown(path, 5000, 5000)
    return True


def _quote_folder(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _ensure_capacity(
    *,
    root: Path,
    current_bytes: int,
    incoming_bytes: int,
    destination_quota_bytes: int | None,
) -> None:
    if destination_quota_bytes is not None and destination_quota_bytes > 0:
        if current_bytes + incoming_bytes > destination_quota_bytes:
            remaining = max(0, destination_quota_bytes - current_bytes)
            raise RuntimeError(
                f"Destination mailbox quota would be exceeded. "
                f"Remaining quota is {remaining} bytes; increase the mailbox quota or free space, then resume the migration."
            )

    # Keep a small operational reserve so a migration cannot consume the last
    # bytes needed by Dovecot, indexes, logs and normal mail delivery.
    probe = root if root.exists() else root.parent
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    try:
        free = shutil.disk_usage(probe).free
    except OSError:
        return
    reserve = max(256 * 1024 * 1024, incoming_bytes * 2)
    if free < incoming_bytes + reserve:
        raise RuntimeError(
            "The mail server does not have enough safe free disk space to continue this migration. "
            "Free storage and resume the migration; source messages have not been deleted."
        )


def migrate_imap_mailbox(
    *,
    destination_address: str,
    source_provider: str,
    source_username: str,
    source_password: str | None = None,
    oauth2_token: str | None = None,
    source_host: str | None = None,
    source_port: int | None = None,
    destination_quota_bytes: int | None = None,
) -> dict:
    host, port = provider_endpoint(source_provider, source_host, source_port)
    client = imaplib.IMAP4_SSL(host, port)
    root = _maildir_root(destination_address)
    destination_bytes = _maildir_size(root)
    if destination_quota_bytes is None:
        destination_quota_bytes = _configured_quota(destination_address)
    try:
        if oauth2_token:
            client.authenticate("XOAUTH2", lambda _challenge: _xoauth2(source_username, oauth2_token))
        elif source_password:
            client.login(source_username, source_password)
        else:
            raise ValueError("source_password or oauth2_token is required")

        status, rows = client.list()
        if status != "OK":
            raise RuntimeError("Unable to list source IMAP folders")

        folder_pairs: list[tuple[str, str]] = []
        seen_pairs: set[tuple[str, str]] = set()
        for row in rows or []:
            pair = _folder_pair(row)
            if pair not in seen_pairs:
                folder_pairs.append(pair)
                seen_pairs.add(pair)
        if not any(target == "" for _, target in folder_pairs):
            folder_pairs.insert(0, ("INBOX", ""))

        copied = 0
        skipped = 0
        copied_bytes = 0
        folder_count = 0
        for source_name, folder in folder_pairs:
            status, _ = client.select(_quote_folder(source_name), readonly=True)
            if status != "OK":
                continue
            folder_count += 1
            status, ids = client.uid("search", None, "ALL")
            if status != "OK" or not ids:
                continue
            uid_list = ids[0].split()
            target = _maildir_for(destination_address, folder)
            for uid in uid_list:
                status, fetched = client.uid("fetch", uid, "(BODY.PEEK[] FLAGS)")
                if status != "OK" or not fetched:
                    continue
                pair = next(
                    (
                        part
                        for part in fetched
                        if isinstance(part, tuple)
                        and len(part) >= 2
                        and isinstance(part[1], bytes)
                    ),
                    None,
                )
                if pair is None:
                    continue
                raw = pair[1]
                meta = pair[0]

                # Detect duplicates before capacity checks so a harmless resume
                # does not fail merely because the destination is now near quota.
                digest = hashlib.sha256(raw).hexdigest()[:32]
                if _already_imported(target, digest):
                    skipped += 1
                    continue

                _ensure_capacity(
                    root=root,
                    current_bytes=destination_bytes + copied_bytes,
                    incoming_bytes=len(raw),
                    destination_quota_bytes=destination_quota_bytes,
                )
                if _write_maildir_message(target, raw, meta):
                    copied += 1
                    copied_bytes += len(raw)
                else:
                    skipped += 1
        return {
            "folders_total": len(folder_pairs),
            "folders_done": folder_count,
            "messages_copied": copied,
            "messages_skipped": skipped,
            "bytes_copied": copied_bytes,
        }
    finally:
        try:
            client.logout()
        except Exception:
            pass
