import hashlib
import imaplib
import os
import re
import time
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


def _folder_name(raw: bytes | str) -> str:
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    match = re.search(r' (?:"([^"]+)"|([^\s]+))$', text)
    folder = (match.group(1) or match.group(2)) if match else "INBOX"
    if folder.upper() == "INBOX":
        return ""
    safe = folder.replace("/", ".").replace("\\", ".")
    safe = re.sub(r"[^A-Za-z0-9_. -]+", "_", safe).strip(". ")
    return safe[:180]


def _maildir_for(address: str, folder: str) -> Path:
    local, domain = address.lower().split("@", 1)
    base = Path(settings.mail_data_path) / domain / local / "Maildir"
    return base if not folder else base / f".{folder}"


def _write_maildir_message(target: Path, raw_message: bytes) -> bool:
    for sub in ("tmp", "new", "cur"):
        path = target / sub
        path.mkdir(parents=True, exist_ok=True)
        os.chown(target, 5000, 5000)
        os.chown(path, 5000, 5000)
    digest = hashlib.sha256(raw_message).hexdigest()
    filename = f"{int(time.time())}.{digest[:24]}.migration"
    path = target / "new" / filename
    if path.exists():
        return False
    path.write_bytes(raw_message)
    os.chown(path, 5000, 5000)
    return True


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
        folders = [_folder_name(row) for row in (rows or [])]
        if "" not in folders:
            folders.insert(0, "")
        copied = 0
        copied_bytes = 0
        folder_count = 0
        for folder in folders:
            source_name = "INBOX" if folder == "" else folder.replace(".", "/")
            status, _ = client.select(f'"{source_name}"', readonly=True)
            if status != "OK":
                continue
            folder_count += 1
            status, ids = client.uid("search", None, "ALL")
            if status != "OK" or not ids:
                continue
            uid_list = ids[0].split()
            target = _maildir_for(destination_address, folder)
            for uid in uid_list:
                status, fetched = client.uid("fetch", uid, "(RFC822)")
                if status != "OK" or not fetched:
                    continue
                raw = next((part[1] for part in fetched if isinstance(part, tuple) and isinstance(part[1], bytes)), None)
                if raw is None:
                    continue
                if _write_maildir_message(target, raw):
                    copied += 1
                    copied_bytes += len(raw)
        return {"folders_total": len(folders), "folders_done": folder_count, "messages_copied": copied, "bytes_copied": copied_bytes}
    finally:
        try:
            client.logout()
        except Exception:
            pass
