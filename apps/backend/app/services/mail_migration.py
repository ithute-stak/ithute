import hashlib
import imaplib
import os
import re
import shutil
import ssl
from email.utils import parsedate_to_datetime
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Mailbox
from app.services.external_webmail import _assert_public_host, _tls_context

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
    """Return the original IMAP folder name plus a safe Maildir folder name."""
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


def _internaldate_timestamp(meta: bytes | str) -> float | None:
    """Extract the source IMAP INTERNALDATE so migrated mail keeps its arrival date."""
    text = meta.decode("utf-8", "replace") if isinstance(meta, bytes) else str(meta)
    match = re.search(r'INTERNALDATE\s+"([^"]+)"', text, re.IGNORECASE)
    if not match:
        return None
    try:
        return parsedate_to_datetime(match.group(1)).timestamp()
    except (TypeError, ValueError, OverflowError):
        return None


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


def _write_maildir_message(
    target: Path,
    raw_message: bytes,
    meta: bytes | str = b"",
    internal_timestamp: float | None = None,
) -> bool:
    """Write one raw message with deterministic dedupe and preserved source metadata."""
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
    if internal_timestamp is not None:
        try:
            os.utime(path, (internal_timestamp, internal_timestamp))
        except (OSError, OverflowError):
            pass
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


def _open_source_client(host: str, port: int, security: str) -> imaplib.IMAP4:
    """Open only a TLS-protected, public-internet IMAP source to prevent SSRF."""
    _assert_public_host(host, port)
    mode = (security or "ssl").strip().lower()
    timeout = settings.webmail_transport_timeout_seconds
    if mode == "ssl":
        return imaplib.IMAP4_SSL(host, port, ssl_context=_tls_context(), timeout=timeout)
    if mode in {"starttls", "tls"}:
        client = imaplib.IMAP4(host, port, timeout=timeout)
        try:
            client.starttls(ssl_context=_tls_context())
            return client
        except Exception:
            try:
                client.logout()
            except Exception:
                pass
            raise
    raise ValueError("Source IMAP security must be ssl or starttls")


def migrate_imap_mailbox(
    *,
    destination_address: str,
    source_provider: str,
    source_username: str,
    source_password: str | None = None,
    oauth2_token: str | None = None,
    source_host: str | None = None,
    source_port: int | None = None,
    source_security: str = "ssl",
    destination_quota_bytes: int | None = None,
) -> dict:
    """Copy a source mailbox without deleting source mail.

    The operation is deliberately repeatable. A first run copies historical mail;
    later delta/final runs re-scan the source but deterministic per-folder hashes
    skip messages already present at Ithute, so mail arriving during MX cutover is
    copied without creating duplicates.
    """
    host, port = provider_endpoint(source_provider, source_host, source_port)
    client = None
    root = _maildir_root(destination_address)
    destination_bytes = _maildir_size(root)
    if destination_quota_bytes is None:
        destination_quota_bytes = _configured_quota(destination_address)

    copied = 0
    skipped = 0
    failed = 0
    seen = 0
    copied_bytes = 0
    folder_count = 0
    failure_details: list[str] = []

    def record_failure(message: str) -> None:
        nonlocal failed
        failed += 1
        if len(failure_details) < 50:
            failure_details.append(message[:500])

    try:
        try:
            client = _open_source_client(host, port, source_security)
            if oauth2_token:
                client.authenticate("XOAUTH2", lambda _challenge: _xoauth2(source_username, oauth2_token))
            elif source_password:
                client.login(source_username, source_password)
            else:
                raise ValueError("source_password or oauth2_token is required")
        except (imaplib.IMAP4.error, OSError, ssl.SSLError) as exc:
            raise RuntimeError("Unable to securely connect or authenticate to the source IMAP mailbox") from exc

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

        for source_name, folder in folder_pairs:
            status, _ = client.select(_quote_folder(source_name), readonly=True)
            if status != "OK":
                record_failure(f"Folder could not be selected: {source_name}")
                continue
            folder_count += 1
            status, ids = client.uid("search", None, "ALL")
            if status != "OK" or not ids:
                if status != "OK":
                    record_failure(f"Folder could not be searched: {source_name}")
                continue
            uid_list = ids[0].split()
            target = _maildir_for(destination_address, folder)
            for uid in uid_list:
                seen += 1
                status, fetched = client.uid("fetch", uid, "(BODY.PEEK[] FLAGS INTERNALDATE)")
                if status != "OK" or not fetched:
                    record_failure(f"Message fetch failed in {source_name} for UID {uid.decode(errors='replace')}")
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
                    record_failure(f"Message payload missing in {source_name} for UID {uid.decode(errors='replace')}")
                    continue
                raw = pair[1]
                meta = pair[0]

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
                if _write_maildir_message(target, raw, meta, _internaldate_timestamp(meta)):
                    copied += 1
                    copied_bytes += len(raw)
                else:
                    skipped += 1

        return {
            "folders_total": len(folder_pairs),
            "folders_done": folder_count,
            "messages_seen": seen,
            "messages_copied": copied,
            "messages_skipped": skipped,
            "messages_failed": failed,
            "bytes_copied": copied_bytes,
            "failure_details": failure_details,
            "clean": failed == 0 and folder_count == len(folder_pairs),
        }
    finally:
        if client is not None:
            try:
                client.logout()
            except Exception:
                pass
