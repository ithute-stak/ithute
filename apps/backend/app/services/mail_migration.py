import hashlib
import imaplib
import os
import re
from pathlib import Path

from app.core.config import settings

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


def migrate_imap_mailbox(
    *,
    destination_address: str,
    source_provider: str,
    source_username: str,
    source_password: str | None = None,
    oauth2_token: str | None = None,
    source_host: str | None = None,
    source_port: int | None = None,
) -> dict:
    host, port = provider_endpoint(source_provider, source_host, source_port)
    client = imaplib.IMAP4_SSL(host, port)
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
