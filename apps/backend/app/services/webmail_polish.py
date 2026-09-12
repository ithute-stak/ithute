import base64
import html
import imaplib
import json
import re
import smtplib
import ssl
from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import format_datetime, getaddresses, make_msgid

import bleach
import redis

from app.core.config import settings
from app.services.webmail import WebmailError, _ensure_folder, _imap, _tls_context, sender_header

ALLOWED_TAGS = ["p", "br", "strong", "b", "em", "i", "u", "ul", "ol", "li", "blockquote", "a", "code", "pre"]
ALLOWED_ATTRS = {"a": ["href", "title"]}
SIGNATURE_ALLOWED_TAGS = [*ALLOWED_TAGS, "img"]
IMAGE_DATA_RE = re.compile(r"^data:image/(png|jpeg|gif|webp);base64,([A-Za-z0-9+/=\r\n]+)$", re.IGNORECASE)
IMAGE_SRC_RE = re.compile(r'src="(data:image/(png|jpeg|gif|webp);base64,[A-Za-z0-9+/=]+)"', re.IGNORECASE)
CONTACT_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CONTACT_SCAN_LIMIT = 100
MAX_ATTACHMENT_BYTES = 15 * 1024 * 1024


def _redis():
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def sanitize_html(value: str) -> str:
    return bleach.clean(value or "", tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, protocols=["http", "https", "mailto"], strip=True)


def _valid_image_data_url(value: str) -> bool:
    match = IMAGE_DATA_RE.fullmatch((value or "").strip())
    if not match:
        return False
    try:
        payload = base64.b64decode(re.sub(r"\s+", "", match.group(2)), validate=True)
    except (ValueError, TypeError):
        return False
    return 0 < len(payload) <= 2 * 1024 * 1024


def _signature_attr_filter(tag: str, name: str, value: str) -> bool:
    if tag == "a":
        return name in {"href", "title"}
    if tag == "img":
        if name == "src":
            return _valid_image_data_url(value)
        return name in {"alt", "width", "height"}
    return False


def sanitize_signature_html(value: str) -> str:
    return bleach.clean(
        value or "",
        tags=SIGNATURE_ALLOWED_TAGS,
        attributes=_signature_attr_filter,
        protocols=["http", "https", "mailto", "data"],
        strip=True,
    )


def signature(address: str) -> str:
    try:
        return _redis().get(f"webmail:signature:{address.lower()}") or ""
    except redis.RedisError as exc:
        raise WebmailError("Webmail preferences store is unavailable") from exc


def save_signature(address: str, value: str) -> dict:
    safe = sanitize_signature_html(value)[:20000]
    try:
        _redis().set(f"webmail:signature:{address.lower()}", safe)
    except redis.RedisError as exc:
        raise WebmailError("Webmail preferences store is unavailable") from exc
    return {"saved": True, "html": safe}


def _contact_meta_key(address: str) -> str:
    return f"webmail:contacts-meta:{address.lower()}"


def _normal_contact(value: str) -> str:
    return (value or "").strip().lower()


def _clean_name(value: str) -> str:
    return " ".join((value or "").replace("\r", " ").replace("\n", " ").split())[:255]


def _contact_metadata(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _learn_contact(address: str, email_address: str, display_name: str = "", source: str = "automatic") -> dict | None:
    owner = _normal_contact(address)
    email_address = _normal_contact(email_address)
    if not CONTACT_RE.fullmatch(email_address) or email_address == owner:
        return None

    source = source if source in {"incoming", "outgoing", "manual"} else "automatic"
    now = datetime.now(timezone.utc).isoformat()
    name = _clean_name(display_name)
    try:
        store = _redis()
        contacts_key = f"webmail:contacts:{owner}"
        meta_key = _contact_meta_key(owner)
        existing_name = store.hget(contacts_key, email_address) or ""
        meta = _contact_metadata(store.hget(meta_key, email_address))
        sources = {str(item) for item in meta.get("sources", []) if item}
        if not sources and existing_name:
            sources.add("manual")
        sources.add(source)
        if existing_name and "manual" in sources:
            name = existing_name
        elif not name:
            name = existing_name
        store.hset(contacts_key, email_address, name)
        store.hset(
            meta_key,
            email_address,
            json.dumps(
                {
                    "sources": sorted(sources),
                    "last_seen": now,
                    "interactions": int(meta.get("interactions", 0) or 0) + 1,
                },
                separators=(",", ":"),
            ),
        )
    except redis.RedisError as exc:
        raise WebmailError("Webmail contacts store is unavailable") from exc
    return {"saved": True, "email": email_address, "name": name, "sources": sorted(sources), "last_seen": now}


def learn_contacts_from_headers(address: str, headers: list[str], source: str) -> int:
    learned = 0
    for display_name, email_address in getaddresses([item for item in headers if item]):
        if _learn_contact(address, email_address, display_name, source):
            learned += 1
    return learned


def contacts(address: str, query: str = "") -> list[dict]:
    owner = address.lower()
    try:
        store = _redis()
        raw = store.hgetall(f"webmail:contacts:{owner}")
        meta_raw = store.hgetall(_contact_meta_key(owner))
    except redis.RedisError as exc:
        raise WebmailError("Webmail contacts store is unavailable") from exc
    q = query.strip().lower()
    rows = []
    for email_address, display_name in raw.items():
        if q and q not in email_address.lower() and q not in display_name.lower():
            continue
        meta = _contact_metadata(meta_raw.get(email_address))
        sources = [str(item) for item in meta.get("sources", []) if item]
        if not sources:
            sources = ["manual"]
        rows.append(
            {
                "email": email_address,
                "name": display_name,
                "sources": sources,
                "last_seen": str(meta.get("last_seen") or ""),
                "interactions": int(meta.get("interactions", 0) or 0),
            }
        )
    return sorted(rows, key=lambda row: (row["last_seen"], row["name"].lower(), row["email"].lower()), reverse=True)[:100]


def save_contact(address: str, email_address: str, display_name: str = "") -> dict:
    result = _learn_contact(address, email_address, display_name, "manual")
    if not result:
        raise WebmailError("Invalid contact email address")
    return result


def _scan_contact_folder(client: imaplib.IMAP4, address: str, folder: str, source: str) -> None:
    status, _ = client.select(folder, readonly=True)
    if status != "OK":
        return
    status, data = client.uid("search", None, "ALL")
    if status != "OK" or not data or not data[0]:
        return
    uids = data[0].decode(errors="replace").split()[-CONTACT_SCAN_LIMIT:]
    if not uids:
        return
    status, fetched = client.uid("fetch", ",".join(uids), "(BODY.PEEK[HEADER.FIELDS (FROM REPLY-TO TO CC)])")
    if status != "OK" or not fetched:
        return
    for part in fetched:
        if not isinstance(part, tuple) or len(part) != 2 or not part[1]:
            continue
        try:
            parsed = BytesParser(policy=policy.default).parsebytes(part[1])
        except Exception:
            continue
        if source == "outgoing":
            headers = [str(parsed.get("To") or ""), str(parsed.get("Cc") or "")]
        else:
            headers = [str(parsed.get("From") or ""), str(parsed.get("Reply-To") or "")]
        try:
            learn_contacts_from_headers(address, headers, source)
        except WebmailError:
            return


def folder_counts(address: str, password: str) -> list[dict]:
    client = _imap(address, password)
    try:
        status, data = client.list()
        if status != "OK":
            raise WebmailError("Unable to list mailbox folders")
        rows = []
        for item in data or []:
            text = item.decode(errors="replace") if isinstance(item, bytes) else str(item)
            name = text.rsplit(" ", 1)[-1].strip('"')
            s, result = client.status(name, "(MESSAGES UNSEEN)")
            values = (result[0].decode(errors="replace") if s == "OK" and result and result[0] else "")
            m = re.search(r"MESSAGES\s+(\d+).*UNSEEN\s+(\d+)", values)
            rows.append({"name": name, "messages": int(m.group(1)) if m else 0, "unseen": int(m.group(2)) if m else 0})

        # Contact discovery is intentionally best-effort. It scans recent Inbox
        # and Sent headers using the already-authenticated IMAP session, so
        # normal mailbox refreshes continuously grow compose autocomplete.
        try:
            inbox_name = next((row["name"] for row in rows if row["name"].lower() == "inbox"), "INBOX")
            sent_name = next((row["name"] for row in rows if "sent" in row["name"].lower()), "")
            _scan_contact_folder(client, address, inbox_name, "incoming")
            if sent_name:
                _scan_contact_folder(client, address, sent_name, "outgoing")
        except Exception:
            pass
        return rows
    finally:
        try:
            client.logout()
        except Exception:
            pass


def _embedded_signature_images(value: str) -> tuple[str, list[tuple[bytes, str, str]]]:
    embedded: list[tuple[bytes, str, str]] = []

    def replace(match: re.Match[str]) -> str:
        data_url = match.group(1)
        if not _valid_image_data_url(data_url):
            return match.group(0)
        subtype = match.group(2).lower()
        encoded = data_url.split(",", 1)[1]
        try:
            payload = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError):
            return match.group(0)
        cid = make_msgid(domain="ithute-mail.local")
        embedded.append((payload, subtype, cid))
        return f'src="cid:{cid[1:-1]}"'

    return IMAGE_SRC_RE.sub(replace, value or ""), embedded


def _attachment_payloads(attachments: list[dict] | None) -> list[tuple[bytes, str, str, str]]:
    rows: list[tuple[bytes, str, str, str]] = []
    total_bytes = 0
    for item in attachments or []:
        try:
            payload = base64.b64decode(str(item.get("content_b64", "")), validate=True)
        except Exception as exc:
            raise WebmailError("Attachment data is invalid") from exc
        total_bytes += len(payload)
        if total_bytes > MAX_ATTACHMENT_BYTES:
            raise WebmailError("Total attachment size exceeds 15 MB")
        content_type = str(item.get("content_type") or "application/octet-stream").split(";", 1)[0].strip().lower()
        maintype, separator, subtype = content_type.partition("/")
        if not separator or not maintype or not subtype:
            maintype, subtype = "application", "octet-stream"
        filename = str(item.get("filename") or "attachment").replace("/", "_").replace("\\", "_").strip()[:255] or "attachment"
        rows.append((payload, maintype, subtype, filename))
    return rows


def _plain_signature(value: str) -> str:
    if not value:
        return ""
    without_images = re.sub(r"<img\b[^>]*>", "", value, flags=re.IGNORECASE)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", without_images)).split())


def send_rich_message(
    address: str,
    password: str,
    to: list[str],
    cc: list[str],
    bcc: list[str],
    subject: str,
    body_text: str,
    body_html: str,
    signature_html: str = "",
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

    safe_html = sanitize_html(body_html)
    safe_signature = sanitize_signature_html(signature_html or signature(address))
    plain_body = body_text or re.sub(r"<[^>]+>", " ", body_html or "")
    plain_sig = _plain_signature(safe_signature)
    plain = html.unescape(plain_body)
    if plain_sig:
        plain = f"{plain.rstrip()}\n\n{plain_sig}" if plain.strip() else plain_sig
    msg.set_content(plain)

    signature_with_cid, embedded_images = _embedded_signature_images(safe_signature)
    if safe_html or safe_signature:
        html_value = (safe_html or f"<p>{html.escape(body_text)}</p>") + signature_with_cid
        msg.add_alternative(html_value, subtype="html")
        html_part = msg.get_payload()[-1]
        for payload, subtype, cid in embedded_images:
            html_part.add_related(payload, maintype="image", subtype=subtype, cid=cid, disposition="inline")

    attachment_rows = _attachment_payloads(attachments)
    for payload, maintype, subtype, filename in attachment_rows:
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
        raise WebmailError("Unable to send rich message") from exc

    try:
        client = _imap(address, password)
        try:
            _ensure_folder(client, "Sent")
            client.append("Sent", "\\Seen", imaplib.Time2Internaldate(datetime.now().timestamp()), msg.as_bytes())
        finally:
            client.logout()
    except Exception:
        pass

    # Learn successful outgoing recipients immediately. A Redis preference-store
    # outage must never make a message that was already sent look unsuccessful.
    try:
        learn_contacts_from_headers(address, [*to, *cc, *bcc], "outgoing")
    except WebmailError:
        pass

    return {
        "sent": True,
        "message_id": msg["Message-ID"],
        "recipients": len(recipients),
        "attachments": len(attachment_rows),
        "html": bool(safe_html or safe_signature),
        "signature_images": len(embedded_images),
    }
