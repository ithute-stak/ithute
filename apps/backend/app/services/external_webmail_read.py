import imaplib

from app.services.external_webmail import (
    ExternalMailboxConfig,
    ExternalWebmailError,
    _fetch_raw,
    _imap,
    _message_json,
    _select,
)


def _logout(client) -> None:
    if client is None:
        return
    try:
        client.logout()
    except Exception:
        pass


def message(config: ExternalMailboxConfig, uid: str, folder: str = "INBOX") -> dict:
    """Read a message independently from the best-effort Seen flag update.

    Some external providers allow read-only fetches but reject or behave
    differently for writable SELECT/RFC822 fetches. A failure to update
    ``\\Seen`` must never prevent the user from reading a message.
    """
    reader = _imap(config)
    try:
        _select(reader, folder, readonly=True)
        raw, meta = _fetch_raw(reader, uid, mark_seen=False)
        row = _message_json(uid, raw, meta, include_body=True)
    finally:
        _logout(reader)

    if row.get("seen"):
        return row

    writer = None
    try:
        writer = _imap(config)
        _select(writer, folder, readonly=False)
        status, _ = writer.uid("store", uid, "+FLAGS.SILENT", "(\\Seen)")
        if status == "OK":
            row["seen"] = True
    except (ExternalWebmailError, imaplib.IMAP4.error, OSError):
        # The content has already been fetched successfully. Provider-specific
        # write restrictions or transient Seen-flag failures must not turn a
        # successful read into an "Unable to open message" error.
        pass
    finally:
        _logout(writer)

    return row
