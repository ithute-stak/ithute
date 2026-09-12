import base64
import hashlib
import imaplib
import json
import secrets
import smtplib
import ssl
from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import format_datetime, formataddr, make_msgid
from html import unescape
from re import sub

import redis

from app.core.config import settings
from app.core.security import decrypt_secret, encrypt_secret, hash_token


class WebmailError(RuntimeError):
    pass


def _redis():
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def _session_key(token: str) -> str:
    return f"webmail:session:{hash_token(token)}"


def _tls_context() -> ssl.SSLContext:
    # Mail services are reached over the private Docker network. Public clients
    # still receive the production ACME/external certificate on SMTP/IMAP.
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def _imap(address: str, password: str) -> imaplib.IMAP4:
    try:
        client = imaplib.IMAP4(
            settings.webmail_imap_host,
            settings.webmail_imap_port,
            timeout=settings.webmail_transport_timeout_seconds,
        )
        client.starttls(ssl_context=_tls_context())
        client.login(address, password)
        return client
    except (imaplib.IMAP4.error, OSError, ssl.SSLError) as exc:
        raise WebmailError("Mailbox authentication or IMAP connection failed") from exc


def authenticate(address: str, password: str) -> None:
    client = _imap(address, password)
    try:
        client.noop()
    finally:
        try:
            client.logout()
        except Exception:
            pass


def create_session(address: str, password: str) -> str:
    authenticate(address, password)
    token = secrets.token_urlsafe(48)
    payload = json.dumps(
        {
            "address": address.strip().lower(),
            "password": encrypt_secret(password),
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        separators=(",", ":"),
    )
    try:
        _redis().setex(_session_key(token), settings.webmail_session_ttl_seconds, payload)
    except redis.RedisError as exc:
        raise WebmailError("Webmail session store is unavailable") from exc
    return token


def session_credentials(token: str) -> tuple[str, str]:
    if not token:
        raise WebmailError("Webmail session is missing")
    try:
        raw = _redis().get(_session_key(token))
    except redis.RedisError as exc:
        raise WebmailError("Webmail session store is unavailable") from exc
    if not raw:
        raise WebmailError("Webmail session expired")
    try:
        payload = json.loads(raw)
        address = str(payload["address"])
        password = decrypt_secret(str(payload["password"]))
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise WebmailError("Webmail session is invalid") from exc
    return address, password


def delete_session(token: str) -> None:
    if not token:
        return
    try:
        _redis().delete(_session_key(token))
    except redis.RedisError as exc:
        raise WebmailError("Webmail session store is unavailable") from exc


def display_name(address: str) -> str:
    try:
        return (_redis().get(f"webmail:display-name:{address.lower()}") or "").strip()
    except redis.RedisError as exc:
        raise WebmailError("Webmail preferences store is unavailable") from exc


def save_display_name(address: str, value: str) -> dict:
    clean = " ".join((value or "").replace("\r", " ").replace("\n", " ").split())[:255]
    key = f"webmail:display-name:{address.lower()}"
    try:
        if clean:
            _redis().set(key, clean)
        else:
            _redis().delete(key)
    except redis.RedisError as exc:
        raise WebmailError("Webmail preferences store is unavailable") from exc
    return {"saved": True, "display_name": clean}


def sender_header(address: str) -> str:
    name = display_name(address)
    return formataddr((name, address)) if name else address


def _decode(value) -> str:
    if value is None:
        return ""
    return str(value)


def _plain_body(message) -> str:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain" and part.get_content_disposition() != "attachment":
                try:
                    return part.get_content()
                except Exception:
                    payload = part.get_payload(decode=True) or b""
                    return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        for part in message.walk():
            if part.get_content_type() == "text/html" and part.get_content_disposition() != "attachment":
                try:
                    html = part.get_content()
                except Exception:
                    html = (part.get_payload(decode=True) or b"").decode(part.get_content_charset() or "utf-8", errors="replace")
                return unescape(sub(r"<[^>]+>", " ", html))
        return ""
    try:
        value = message.get_content()
    except Exception:
        value = (message.get_payload(decode=True) or b"").decode(message.get_content_charset() or "utf-8", errors="replace")
    if message.get_content_type() == "text/html":
        value = unescape(sub(r"<[^>]+>", " ", value))
    return value


def _attachments(message) -> list[dict]:
    rows = []
    attachment_index = 0
    for part in message.walk():
        filename = part.get_filename()
        disposition = part.get_content_disposition()
        if filename or disposition == "attachment":
            payload = part.get_payload(decode=True) or b""
            rows.append(
                {
                    "index": attachment_index,
                    "filename": filename or f"attachment-{attachment_index + 1}",
                    "content_type": part.get_content_type(),
                    "size": len(payload),
                }
            )
            attachment_index += 1
    return rows


def _message_json(uid: str, raw: bytes, meta: bytes | str = b"", include_body: bool = False) -> dict:
    parsed = BytesParser(policy=policy.default).parsebytes(raw)
    meta_text = meta.decode(errors="replace") if isinstance(meta, bytes) else str(meta)
    body = _plain_body(parsed)
    normalized = " ".join(body.split())
    row = {
        "uid": uid,
        "message_id": _decode(parsed.get("Message-ID")),
        "in_reply_to": _decode(parsed.get("In-Reply-To")),
        "references": _decode(parsed.get("References")),
        "from": _decode(parsed.get("From")),
        "to": _decode(parsed.get("To")),
        "cc": _decode(parsed.get("Cc")),
        "reply_to": _decode(parsed.get("Reply-To")),
        "subject": _decode(parsed.get("Subject")) or "(no subject)",
        "date": _decode(parsed.get("Date")),
        "seen": "\\Seen" in meta_text,
        "flagged": "\\Flagged" in meta_text,
        "answered": "\\Answered" in meta_text,
        "draft": "\\Draft" in meta_text,
        "snippet": normalized[:240],
        "attachments": _attachments(parsed),
    }
    if include_body:
        row["body_text"] = body
    return row


def _select(client: imaplib.IMAP4, folder: str, readonly: bool = False) -> None:
    status, _ = client.select(folder, readonly=readonly)
    if status != "OK":
        raise WebmailError("Unable to open mailbox folder")


def _fetch_raw(client: imaplib.IMAP4, uid: str, mark_seen: bool = False) -> tuple[bytes, bytes | str]:
    query = "(RFC822 FLAGS)" if mark_seen else "(BODY.PEEK[] FLAGS)"
    status, fetched = client.uid("fetch", uid, query)
    if status != "OK" or not fetched:
        raise WebmailError("Message was not found")
    pair = next((part for part in fetched if isinstance(part, tuple) and len(part) == 2), None)
    if not pair:
        raise WebmailError("Message was not found")
    return pair[1], pair[0]


def _ensure_folder(client: imaplib.IMAP4, folder: str) -> None:
    status, _ = client.status(folder, "(MESSAGES)")
    if status == "OK":
        return
    status, _ = client.create(folder)
    if status != "OK":
        raise WebmailError(f"Unable to create mailbox folder {folder}")


def folders(address: str, password: str) -> list[dict]:
    client = _imap(address, password)
    try:
        status, data = client.list()
        if status != "OK":
            raise WebmailError("Unable to list mailbox folders")
        rows = []
        for item in data or []:
            text = item.decode(errors="replace") if isinstance(item, bytes) else str(item)
            name = text.rsplit(" ", 1)[-1].strip('"')
            rows.append({"name": name, "raw": text})
        preferred = {"INBOX": 0, "Drafts": 1, "Sent": 2, "Junk": 3, "Spam": 3, "Trash": 4, "Archive": 5}
        rows.sort(key=lambda x: (preferred.get(x["name"], 10), x["name"].lower()))
        return rows
    finally:
        try:
            client.logout()
        except Exception:
            pass


def messages(address: str, password: str, folder: str = "INBOX", limit: int = 50, offset: int = 0, query: str = "") -> dict:
    client = _imap(address, password)
    try:
        _select(client, folder, readonly=True)
        if query.strip():
            safe = query.strip().replace("\\", "\\\\").replace('"', '\\"')[:255]
            status, data = client.uid("search", None, "TEXT", f'"{safe}"')
        else:
            status, data = client.uid("search", None, "ALL")
        if status != "OK":
            raise WebmailError("Unable to search mailbox")
        uids = data[0].decode().split() if data and data[0] else []
        uids.reverse()
        selected = uids[offset : offset + limit]
        rows = []
        for uid in selected:
            try:
                raw, meta = _fetch_raw(client, uid, mark_seen=False)
            except WebmailError:
                continue
            rows.append(_message_json(uid, raw, meta))
        return {"items": rows, "total": len(uids), "folder": folder, "limit": limit, "offset": offset, "query": query.strip()}
    finally:
        try:
            client.logout()
        except Exception:
            pass


def message(address: str, password: str, uid: str, folder: str = "INBOX") -> dict:
    client = _imap(address, password)
    try:
        _select(client, folder, readonly=False)
        raw, meta = _fetch_raw(client, uid, mark_seen=True)
        return _message_json(uid, raw, meta, include_body=True)
    finally:
        try:
            client.logout()
        except Exception:
            pass


def set_flags(address: str, password: str, uid: str, folder: str, seen: bool | None = None, flagged: bool | None = None, answered: bool | None = None) -> dict:
    client = _imap(address, password)
    try:
        _select(client, folder, readonly=False)
        changes = (("\\Seen", seen), ("\\Flagged", flagged), ("\\Answered", answered))
        for flag, value in changes:
            if value is None:
                continue
            operation = "+FLAGS.SILENT" if value else "-FLAGS.SILENT"
            status, _ = client.uid("store", uid, operation, f"({flag})")
            if status != "OK":
                raise WebmailError("Unable to update message flags")
        raw, meta = _fetch_raw(client, uid, mark_seen=False)
        return _message_json(uid, raw, meta)
    finally:
        try:
            client.logout()
        except Exception:
            pass


def move_message(address: str, password: str, uid: str, folder: str, destination: str) -> dict:
    if folder == destination:
        raise WebmailError("Source and destination folders are the same")
    client = _imap(address, password)
    try:
        _select(client, folder, readonly=False)
        _ensure_folder(client, destination)
        status, _ = client.uid("copy", uid, destination)
        if status != "OK":
            raise WebmailError("Unable to copy message to destination folder")
        status, _ = client.uid("store", uid, "+FLAGS.SILENT", "(\\Deleted)")
        if status != "OK":
            raise WebmailError("Unable to remove source message")
        client.expunge()
        return {"moved": True, "uid": uid, "from": folder, "to": destination}
    finally:
        try:
            client.logout()
        except Exception:
            pass


def delete_message(address: str, password: str, uid: str, folder: str) -> dict:
    if folder.lower() not in {"trash", "deleted", "deleted items"}:
        return move_message(address, password, uid, folder, "Trash")
    client = _imap(address, password)
    try:
        _select(client, folder, readonly=False)
        status, _ = client.uid("store", uid, "+FLAGS.SILENT", "(\\Deleted)")
        if status != "OK":
            raise WebmailError("Unable to delete message")
        client.expunge()
        return {"deleted": True, "uid": uid, "folder": folder}
    finally:
        try:
            client.logout()
        except Exception:
            pass


def save_draft(address: str, password: str, to: list[str], cc: list[str], subject: str, body_text: str) -> dict:
    msg = EmailMessage()
    msg["From"] = sender_header(address)
    if to:
        msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg["Date"] = format_datetime(datetime.now(timezone.utc))
    msg["Message-ID"] = make_msgid(domain=address.split("@", 1)[-1])
    msg.set_content(body_text)
    client = _imap(address, password)
    try:
        _ensure_folder(client, "Drafts")
        status, _ = client.append("Drafts", "\\Draft", imaplib.Time2Internaldate(datetime.now().timestamp()), msg.as_bytes())
        if status != "OK":
            raise WebmailError("Unable to save draft")
        return {"saved": True, "message_id": msg["Message-ID"], "folder": "Drafts"}
    finally:
        try:
            client.logout()
        except Exception:
            pass


def attachment(address: str, password: str, uid: str, folder: str, index: int) -> tuple[str, str, bytes]:
    client = _imap(address, password)
    try:
        _select(client, folder, readonly=True)
        raw, _ = _fetch_raw(client, uid, mark_seen=False)
        parsed = BytesParser(policy=policy.default).parsebytes(raw)
        candidates = []
        for part in parsed.walk():
            if part.get_filename() or part.get_content_disposition() == "attachment":
                candidates.append(part)
        if index < 0 or index >= len(candidates):
            raise WebmailError("Attachment was not found")
        part = candidates[index]
        filename = part.get_filename() or f"attachment-{index + 1}"
        return filename, part.get_content_type(), part.get_payload(decode=True) or b""
    finally:
        try:
            client.logout()
        except Exception:
            pass


def send_message(
    address: str,
    password: str,
    to: list[str],
    cc: list[str],
    bcc: list[str],
    subject: str,
    body_text: str,
    attachments: list[dict] | None = None,
    in_reply_to: str = "",
    references: str = "",
) -> dict:
    msg = EmailMessage()
    msg["From"] = sender_header(address)
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg["Date"] = format_datetime(datetime.now(timezone.utc))
    msg["Message-ID"] = make_msgid(domain=address.split("@", 1)[-1])
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to[:998]
    if references:
        msg["References"] = references[:4000]
    msg.set_content(body_text)

    total_attachment_bytes = 0
    for item in attachments or []:
        try:
            payload = base64.b64decode(str(item.get("content_b64", "")), validate=True)
        except Exception as exc:
            raise WebmailError("Attachment data is invalid") from exc
        total_attachment_bytes += len(payload)
        if total_attachment_bytes > 15 * 1024 * 1024:
            raise WebmailError("Total attachment size exceeds 15 MB")
        content_type = str(item.get("content_type") or "application/octet-stream")
        maintype, _, subtype = content_type.partition("/")
        if not subtype:
            maintype, subtype = "application", "octet-stream"
        filename = str(item.get("filename") or "attachment")[:255]
        msg.add_attachment(payload, maintype=maintype, subtype=subtype, filename=filename)

    recipients = [*to, *cc, *bcc]
    try:
        with smtplib.SMTP(settings.webmail_smtp_host, settings.webmail_smtp_port, timeout=settings.webmail_transport_timeout_seconds) as smtp:
            smtp.ehlo()
            smtp.starttls(context=_tls_context())
            smtp.ehlo()
            smtp.login(address, password)
            smtp.send_message(msg, from_addr=address, to_addrs=recipients)
    except (smtplib.SMTPException, OSError, ssl.SSLError) as exc:
        raise WebmailError("Unable to send message") from exc

    try:
        client = _imap(address, password)
        try:
            _ensure_folder(client, "Sent")
            client.append("Sent", "\\Seen", imaplib.Time2Internaldate(datetime.now().timestamp()), msg.as_bytes())
        finally:
            client.logout()
    except Exception:
        pass
    return {"sent": True, "message_id": msg["Message-ID"], "recipients": len(recipients), "attachments": len(attachments or [])}
