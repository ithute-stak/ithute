import base64
import ipaddress
import imaplib
import json
import re
import secrets
import smtplib
import socket
import ssl
from dataclasses import asdict, dataclass
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


class ExternalWebmailError(RuntimeError):
    pass


ALLOWED_IMAP_PORTS = {143, 993}
ALLOWED_SMTP_PORTS = {25, 465, 587, 2525}
ALLOWED_SECURITY = {"ssl", "starttls"}
MAX_ATTACHMENT_BYTES = 15 * 1024 * 1024
HOST_RE = re.compile(r"^[A-Za-z0-9.-]{1,253}$")


@dataclass(frozen=True)
class ExternalMailboxConfig:
    address: str
    username: str
    password: str
    display_name: str
    imap_host: str
    imap_port: int
    imap_security: str
    smtp_host: str
    smtp_port: int
    smtp_security: str

    def public_dict(self) -> dict:
        return {
            "address": self.address,
            "username": self.username,
            "display_name": self.display_name,
            "imap_host": self.imap_host,
            "imap_port": self.imap_port,
            "imap_security": self.imap_security,
            "smtp_host": self.smtp_host,
            "smtp_port": self.smtp_port,
            "smtp_security": self.smtp_security,
        }


def _redis():
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def _session_key(token: str) -> str:
    return f"webmail:external-session:{hash_token(token)}"


def _clean_host(value: str) -> str:
    host = (value or "").strip().rstrip(".").lower()
    if not host or "://" in host or "/" in host or "@" in host or not HOST_RE.fullmatch(host):
        raise ExternalWebmailError("Enter a valid mail server hostname")
    return host


def _assert_public_host(host: str, port: int) -> None:
    host = _clean_host(host)
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ExternalWebmailError(f"Mail server {host} could not be resolved") from exc
    if not infos:
        raise ExternalWebmailError(f"Mail server {host} could not be resolved")
    addresses = {row[4][0].split("%", 1)[0] for row in infos if row and row[4]}
    if not addresses:
        raise ExternalWebmailError(f"Mail server {host} could not be resolved")
    for raw in addresses:
        try:
            address = ipaddress.ip_address(raw)
        except ValueError as exc:
            raise ExternalWebmailError("Mail server resolved to an invalid address") from exc
        if not address.is_global:
            raise ExternalWebmailError("Private, loopback and reserved mail server addresses are not allowed")


def normalized_config(
    *,
    address: str,
    username: str,
    password: str,
    display_name: str,
    imap_host: str,
    imap_port: int,
    imap_security: str,
    smtp_host: str,
    smtp_port: int,
    smtp_security: str,
) -> ExternalMailboxConfig:
    mailbox = (address or "").strip().lower()
    login = (username or mailbox).strip()
    if "@" not in mailbox or mailbox.startswith("@") or mailbox.endswith("@"):
        raise ExternalWebmailError("Enter a valid external mailbox address")
    if not login:
        raise ExternalWebmailError("Mailbox username is required")
    if not password:
        raise ExternalWebmailError("Mailbox password is required")
    if imap_port not in ALLOWED_IMAP_PORTS:
        raise ExternalWebmailError("IMAP port must be 143 or 993")
    if smtp_port not in ALLOWED_SMTP_PORTS:
        raise ExternalWebmailError("SMTP port must be 25, 465, 587 or 2525")
    imap_mode = (imap_security or "").strip().lower()
    smtp_mode = (smtp_security or "").strip().lower()
    if imap_mode not in ALLOWED_SECURITY or smtp_mode not in ALLOWED_SECURITY:
        raise ExternalWebmailError("Only SSL/TLS or STARTTLS mail connections are allowed")
    incoming_host = _clean_host(imap_host)
    outgoing_host = _clean_host(smtp_host)
    _assert_public_host(incoming_host, imap_port)
    _assert_public_host(outgoing_host, smtp_port)
    return ExternalMailboxConfig(
        address=mailbox,
        username=login,
        password=password,
        display_name=" ".join((display_name or "").replace("\r", " ").replace("\n", " ").split())[:255],
        imap_host=incoming_host,
        imap_port=imap_port,
        imap_security=imap_mode,
        smtp_host=outgoing_host,
        smtp_port=smtp_port,
        smtp_security=smtp_mode,
    )


def _tls_context() -> ssl.SSLContext:
    # External providers are public services: never disable hostname or
    # certificate verification here.
    return ssl.create_default_context()


def _imap(config: ExternalMailboxConfig) -> imaplib.IMAP4:
    _assert_public_host(config.imap_host, config.imap_port)
    try:
        if config.imap_security == "ssl":
            client = imaplib.IMAP4_SSL(
                config.imap_host,
                config.imap_port,
                ssl_context=_tls_context(),
                timeout=settings.webmail_transport_timeout_seconds,
            )
        else:
            client = imaplib.IMAP4(
                config.imap_host,
                config.imap_port,
                timeout=settings.webmail_transport_timeout_seconds,
            )
            client.starttls(ssl_context=_tls_context())
        client.login(config.username, config.password)
        return client
    except (imaplib.IMAP4.error, OSError, ssl.SSLError) as exc:
        raise ExternalWebmailError("External mailbox authentication or IMAP connection failed") from exc


def _smtp(config: ExternalMailboxConfig):
    _assert_public_host(config.smtp_host, config.smtp_port)
    try:
        if config.smtp_security == "ssl":
            client = smtplib.SMTP_SSL(
                config.smtp_host,
                config.smtp_port,
                timeout=settings.webmail_transport_timeout_seconds,
                context=_tls_context(),
            )
            client.ehlo()
        else:
            client = smtplib.SMTP(
                config.smtp_host,
                config.smtp_port,
                timeout=settings.webmail_transport_timeout_seconds,
            )
            client.ehlo()
            client.starttls(context=_tls_context())
            client.ehlo()
        client.login(config.username, config.password)
        return client
    except (smtplib.SMTPException, OSError, ssl.SSLError) as exc:
        raise ExternalWebmailError("External mailbox authentication or SMTP connection failed") from exc


def test_account(config: ExternalMailboxConfig) -> None:
    imap = _imap(config)
    try:
        imap.noop()
    finally:
        try:
            imap.logout()
        except Exception:
            pass
    smtp = _smtp(config)
    try:
        smtp.noop()
    finally:
        try:
            smtp.quit()
        except Exception:
            try:
                smtp.close()
            except Exception:
                pass


def create_session(config: ExternalMailboxConfig) -> str:
    test_account(config)
    token = secrets.token_urlsafe(48)
    payload = asdict(config)
    payload["password"] = encrypt_secret(config.password)
    payload["created_at"] = datetime.now(timezone.utc).isoformat()
    try:
        _redis().setex(
            _session_key(token),
            settings.webmail_session_ttl_seconds,
            json.dumps(payload, separators=(",", ":")),
        )
    except redis.RedisError as exc:
        raise ExternalWebmailError("External webmail session store is unavailable") from exc
    return token


def session_config(token: str) -> ExternalMailboxConfig:
    if not token:
        raise ExternalWebmailError("External webmail session is missing")
    try:
        raw = _redis().get(_session_key(token))
    except redis.RedisError as exc:
        raise ExternalWebmailError("External webmail session store is unavailable") from exc
    if not raw:
        raise ExternalWebmailError("External webmail session expired")
    try:
        payload = json.loads(raw)
        return ExternalMailboxConfig(
            address=str(payload["address"]),
            username=str(payload["username"]),
            password=decrypt_secret(str(payload["password"])),
            display_name=str(payload.get("display_name") or ""),
            imap_host=str(payload["imap_host"]),
            imap_port=int(payload["imap_port"]),
            imap_security=str(payload["imap_security"]),
            smtp_host=str(payload["smtp_host"]),
            smtp_port=int(payload["smtp_port"]),
            smtp_security=str(payload["smtp_security"]),
        )
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ExternalWebmailError("External webmail session is invalid") from exc


def delete_session(token: str) -> None:
    if not token:
        return
    try:
        _redis().delete(_session_key(token))
    except redis.RedisError as exc:
        raise ExternalWebmailError("External webmail session store is unavailable") from exc


def _folder_name(item: bytes | str) -> str:
    text = item.decode(errors="replace") if isinstance(item, bytes) else str(item)
    match = re.search(r'\)\s+(?:"[^"]*"|NIL)\s+(?:"((?:[^"\\]|\\.)*)"|(.*))$', text)
    if match:
        value = (match.group(1) or match.group(2) or "").strip()
        return value.replace('\\"', '"')
    return text.rsplit(" ", 1)[-1].strip('"')


def _list_folder_names(client: imaplib.IMAP4) -> list[str]:
    status, data = client.list()
    if status != "OK":
        raise ExternalWebmailError("Unable to list external mailbox folders")
    names = [_folder_name(item) for item in data or []]
    names = [name for name in names if name]
    preferred = {"inbox": 0, "drafts": 1, "sent": 2, "sent items": 2, "spam": 3, "junk": 3, "trash": 4, "deleted items": 4, "archive": 5, "all mail": 5}
    return sorted(dict.fromkeys(names), key=lambda name: (preferred.get(name.lower(), 10), name.lower()))


def _folder_for(names: list[str], role: str) -> str | None:
    candidates = {
        "sent": ["sent", "sent items", "sent messages", "inbox.sent"],
        "drafts": ["drafts", "draft", "inbox.drafts"],
        "trash": ["trash", "deleted items", "deleted messages", "bin", "inbox.trash"],
        "archive": ["archive", "archives", "all mail", "inbox.archive"],
    }[role]
    lowered = {name.lower(): name for name in names}
    for candidate in candidates:
        if candidate in lowered:
            return lowered[candidate]
    for name in names:
        lower = name.lower()
        if any(candidate in lower for candidate in candidates):
            return name
    return None


def _select(client: imaplib.IMAP4, folder: str, readonly: bool = False) -> None:
    status, _ = client.select(folder, readonly=readonly)
    if status != "OK":
        raise ExternalWebmailError("Unable to open external mailbox folder")


def _fetch_raw(client: imaplib.IMAP4, uid: str, mark_seen: bool = False) -> tuple[bytes, bytes | str]:
    query = "(RFC822 FLAGS)" if mark_seen else "(BODY.PEEK[] FLAGS)"
    status, fetched = client.uid("fetch", uid, query)
    if status != "OK" or not fetched:
        raise ExternalWebmailError("Message was not found")
    pair = next((part for part in fetched if isinstance(part, tuple) and len(part) == 2), None)
    if not pair:
        raise ExternalWebmailError("Message was not found")
    return pair[1], pair[0]


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
    index = 0
    for part in message.walk():
        filename = part.get_filename()
        if filename or part.get_content_disposition() == "attachment":
            payload = part.get_payload(decode=True) or b""
            rows.append({
                "index": index,
                "filename": filename or f"attachment-{index + 1}",
                "content_type": part.get_content_type(),
                "size": len(payload),
            })
            index += 1
    return rows


def _message_json(uid: str, raw: bytes, meta: bytes | str = b"", include_body: bool = False) -> dict:
    parsed = BytesParser(policy=policy.default).parsebytes(raw)
    meta_text = meta.decode(errors="replace") if isinstance(meta, bytes) else str(meta)
    body = _plain_body(parsed)
    row = {
        "uid": uid,
        "message_id": str(parsed.get("Message-ID") or ""),
        "in_reply_to": str(parsed.get("In-Reply-To") or ""),
        "references": str(parsed.get("References") or ""),
        "from": str(parsed.get("From") or ""),
        "to": str(parsed.get("To") or ""),
        "cc": str(parsed.get("Cc") or ""),
        "reply_to": str(parsed.get("Reply-To") or ""),
        "subject": str(parsed.get("Subject") or "(no subject)"),
        "date": str(parsed.get("Date") or ""),
        "seen": "\\Seen" in meta_text,
        "flagged": "\\Flagged" in meta_text,
        "answered": "\\Answered" in meta_text,
        "draft": "\\Draft" in meta_text,
        "snippet": " ".join(body.split())[:240],
        "attachments": _attachments(parsed),
    }
    if include_body:
        row["body_text"] = body
    return row


def folders(config: ExternalMailboxConfig) -> list[dict]:
    client = _imap(config)
    try:
        return [{"name": name, "raw": name} for name in _list_folder_names(client)]
    finally:
        try:
            client.logout()
        except Exception:
            pass


def folder_counts(config: ExternalMailboxConfig) -> list[dict]:
    client = _imap(config)
    try:
        rows = []
        for name in _list_folder_names(client):
            status, result = client.status(name, "(MESSAGES UNSEEN)")
            raw = result[0].decode(errors="replace") if status == "OK" and result and result[0] else ""
            messages_match = re.search(r"MESSAGES\s+(\d+)", raw, re.IGNORECASE)
            unseen_match = re.search(r"UNSEEN\s+(\d+)", raw, re.IGNORECASE)
            rows.append({
                "name": name,
                "messages": int(messages_match.group(1)) if messages_match else 0,
                "unseen": int(unseen_match.group(1)) if unseen_match else 0,
            })
        return rows
    finally:
        try:
            client.logout()
        except Exception:
            pass


def messages(config: ExternalMailboxConfig, folder: str = "INBOX", limit: int = 50, offset: int = 0, query: str = "") -> dict:
    client = _imap(config)
    try:
        _select(client, folder, readonly=True)
        if query.strip():
            safe = query.strip().replace("\\", "\\\\").replace('"', '\\"')[:255]
            status, data = client.uid("search", None, "TEXT", f'"{safe}"')
        else:
            status, data = client.uid("search", None, "ALL")
        if status != "OK":
            raise ExternalWebmailError("Unable to search external mailbox")
        uids = data[0].decode(errors="replace").split() if data and data[0] else []
        uids.reverse()
        selected = uids[offset : offset + limit]
        rows = []
        for uid in selected:
            try:
                raw, meta = _fetch_raw(client, uid, mark_seen=False)
                rows.append(_message_json(uid, raw, meta))
            except ExternalWebmailError:
                continue
        return {"items": rows, "total": len(uids), "folder": folder, "limit": limit, "offset": offset, "query": query.strip()}
    finally:
        try:
            client.logout()
        except Exception:
            pass


def message(config: ExternalMailboxConfig, uid: str, folder: str = "INBOX") -> dict:
    client = _imap(config)
    try:
        _select(client, folder, readonly=False)
        raw, meta = _fetch_raw(client, uid, mark_seen=True)
        return _message_json(uid, raw, meta, include_body=True)
    finally:
        try:
            client.logout()
        except Exception:
            pass


def set_flags(config: ExternalMailboxConfig, uid: str, folder: str, seen: bool | None = None, flagged: bool | None = None, answered: bool | None = None) -> dict:
    client = _imap(config)
    try:
        _select(client, folder, readonly=False)
        for flag, value in (("\\Seen", seen), ("\\Flagged", flagged), ("\\Answered", answered)):
            if value is None:
                continue
            operation = "+FLAGS.SILENT" if value else "-FLAGS.SILENT"
            status, _ = client.uid("store", uid, operation, f"({flag})")
            if status != "OK":
                raise ExternalWebmailError("Unable to update message flags")
        raw, meta = _fetch_raw(client, uid, mark_seen=False)
        return _message_json(uid, raw, meta)
    finally:
        try:
            client.logout()
        except Exception:
            pass


def _ensure_folder(client: imaplib.IMAP4, folder: str) -> None:
    status, _ = client.status(folder, "(MESSAGES)")
    if status == "OK":
        return
    status, _ = client.create(folder)
    if status != "OK":
        raise ExternalWebmailError(f"Unable to create mailbox folder {folder}")


def move_message(config: ExternalMailboxConfig, uid: str, folder: str, destination: str) -> dict:
    if folder.lower() == destination.lower():
        raise ExternalWebmailError("Source and destination folders are the same")
    client = _imap(config)
    try:
        _select(client, folder, readonly=False)
        _ensure_folder(client, destination)
        status, _ = client.uid("copy", uid, destination)
        if status != "OK":
            raise ExternalWebmailError("Unable to copy message")
        status, _ = client.uid("store", uid, "+FLAGS.SILENT", "(\\Deleted)")
        if status != "OK":
            raise ExternalWebmailError("Unable to remove source message")
        client.expunge()
        return {"moved": True, "uid": uid, "from": folder, "to": destination}
    finally:
        try:
            client.logout()
        except Exception:
            pass


def delete_message(config: ExternalMailboxConfig, uid: str, folder: str) -> dict:
    client = _imap(config)
    try:
        names = _list_folder_names(client)
        trash = _folder_for(names, "trash") or "Trash"
    finally:
        try:
            client.logout()
        except Exception:
            pass
    if folder.lower() != trash.lower():
        return move_message(config, uid, folder, trash)
    client = _imap(config)
    try:
        _select(client, folder, readonly=False)
        status, _ = client.uid("store", uid, "+FLAGS.SILENT", "(\\Deleted)")
        if status != "OK":
            raise ExternalWebmailError("Unable to delete message")
        client.expunge()
        return {"deleted": True, "uid": uid, "folder": folder}
    finally:
        try:
            client.logout()
        except Exception:
            pass


def attachment(config: ExternalMailboxConfig, uid: str, folder: str, index: int) -> tuple[str, str, bytes]:
    client = _imap(config)
    try:
        _select(client, folder, readonly=True)
        raw, _ = _fetch_raw(client, uid, mark_seen=False)
        parsed = BytesParser(policy=policy.default).parsebytes(raw)
        candidates = [part for part in parsed.walk() if part.get_filename() or part.get_content_disposition() == "attachment"]
        if index < 0 or index >= len(candidates):
            raise ExternalWebmailError("Attachment was not found")
        part = candidates[index]
        return (
            part.get_filename() or f"attachment-{index + 1}",
            part.get_content_type(),
            part.get_payload(decode=True) or b"",
        )
    finally:
        try:
            client.logout()
        except Exception:
            pass


def _sender_header(config: ExternalMailboxConfig) -> str:
    return formataddr((config.display_name, config.address)) if config.display_name else config.address


def _attachment_rows(attachments: list[dict] | None) -> list[tuple[bytes, str, str, str]]:
    rows = []
    total = 0
    for item in attachments or []:
        try:
            payload = base64.b64decode(str(item.get("content_b64") or ""), validate=True)
        except Exception as exc:
            raise ExternalWebmailError("Attachment data is invalid") from exc
        total += len(payload)
        if total > MAX_ATTACHMENT_BYTES:
            raise ExternalWebmailError("Total attachment size exceeds 15 MB")
        content_type = str(item.get("content_type") or "application/octet-stream").split(";", 1)[0]
        maintype, sep, subtype = content_type.partition("/")
        if not sep:
            maintype, subtype = "application", "octet-stream"
        filename = str(item.get("filename") or "attachment").replace("/", "_").replace("\\", "_")[:255]
        rows.append((payload, maintype, subtype, filename or "attachment"))
    return rows


def send_message(
    config: ExternalMailboxConfig,
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
    msg["From"] = _sender_header(config)
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg["Date"] = format_datetime(datetime.now(timezone.utc))
    msg["Message-ID"] = make_msgid(domain=config.address.split("@", 1)[-1])
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to[:998]
    if references:
        msg["References"] = references[:4000]
    msg.set_content(body_text)
    for payload, maintype, subtype, filename in _attachment_rows(attachments):
        msg.add_attachment(payload, maintype=maintype, subtype=subtype, filename=filename)

    smtp = _smtp(config)
    try:
        smtp.send_message(msg, from_addr=config.address, to_addrs=[*to, *cc, *bcc])
    except (smtplib.SMTPException, OSError, ssl.SSLError) as exc:
        raise ExternalWebmailError("Unable to send external message") from exc
    finally:
        try:
            smtp.quit()
        except Exception:
            try:
                smtp.close()
            except Exception:
                pass

    try:
        client = _imap(config)
        try:
            names = _list_folder_names(client)
            sent = _folder_for(names, "sent") or "Sent"
            _ensure_folder(client, sent)
            client.append(sent, "\\Seen", imaplib.Time2Internaldate(datetime.now().timestamp()), msg.as_bytes())
        finally:
            client.logout()
    except Exception:
        pass
    return {"sent": True, "message_id": msg["Message-ID"]}


def save_draft(config: ExternalMailboxConfig, to: list[str], cc: list[str], subject: str, body_text: str) -> dict:
    msg = EmailMessage()
    msg["From"] = _sender_header(config)
    if to:
        msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg["Date"] = format_datetime(datetime.now(timezone.utc))
    msg["Message-ID"] = make_msgid(domain=config.address.split("@", 1)[-1])
    msg.set_content(body_text)
    client = _imap(config)
    try:
        names = _list_folder_names(client)
        drafts = _folder_for(names, "drafts") or "Drafts"
        _ensure_folder(client, drafts)
        status, _ = client.append(drafts, "\\Draft", imaplib.Time2Internaldate(datetime.now().timestamp()), msg.as_bytes())
        if status != "OK":
            raise ExternalWebmailError("Unable to save external draft")
        return {"saved": True, "message_id": msg["Message-ID"], "folder": drafts}
    finally:
        try:
            client.logout()
        except Exception:
            pass
