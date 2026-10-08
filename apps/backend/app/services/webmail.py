import base64
import imaplib
import json
import logging
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

import bleach
import redis

from app.core.config import settings
from app.core.security import decrypt_secret, encrypt_secret, hash_token
from app.services.engine_router import execute_binary, execute_mail_render_plan, execute_mail_structured_profile
from app.services.engine_runtime import MimeScan
from app.services.metrics import MAIL_MIME_SCAN_BYTES, MAIL_MIME_SCAN_TOTAL
from app.services.mailbox_events import publish_mailbox_change


logger = logging.getLogger(__name__)


class WebmailError(RuntimeError):
    pass


def _redis():
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def _session_key(token: str) -> str:
    return f"webmail:session:{hash_token(token)}"


def _transport_key(address: str) -> str:
    return f"webmail:transport:{address.strip().lower()}"


def _mail_transport(address: str) -> dict:
    defaults = {
        "imap_host": settings.webmail_imap_host,
        "imap_port": settings.webmail_imap_port,
        "smtp_host": settings.webmail_smtp_host,
        "smtp_port": settings.webmail_smtp_port,
    }
    try:
        raw = _redis().get(_transport_key(address))
    except redis.RedisError:
        return defaults
    if not raw:
        return defaults
    try:
        payload = json.loads(raw)
        imap_port = int(payload.get("imap_port") or defaults["imap_port"])
        smtp_port = int(payload.get("smtp_port") or defaults["smtp_port"])
        return {
            "imap_host": str(payload.get("imap_host") or defaults["imap_host"]),
            "imap_port": imap_port if 1 <= imap_port <= 65535 else defaults["imap_port"],
            "smtp_host": str(payload.get("smtp_host") or defaults["smtp_host"]),
            "smtp_port": smtp_port if 1 <= smtp_port <= 65535 else defaults["smtp_port"],
        }
    except (TypeError, ValueError, json.JSONDecodeError):
        return defaults


def _tls_context() -> ssl.SSLContext:
    """Build the TLS policy used by hosted webmail transports.

    Production connects to the public mail hostname and must verify its
    certificate. Development keeps the historical relaxed mode so local
    self-signed mail containers remain usable.
    """
    context = ssl.create_default_context()
    if settings.environment.lower() != "production":
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


def _close_imap(client: imaplib.IMAP4) -> None:
    try:
        client.logout()
    except Exception:
        pass


def _connect_imap(host: str | None = None, port: int | None = None) -> imaplib.IMAP4:
    """Open IMAP with the transport expected by the configured port.

    Port 993 is implicit TLS (IMAPS). Other configured IMAP ports use
    STARTTLS, including the standard submission-style port 143 setup used by
    local development. Treat handshake/greeting failures as transport errors,
    not bad passwords.
    """
    try:
        resolved_host = host or settings.webmail_imap_host
        resolved_port = port or settings.webmail_imap_port
        if resolved_port == 993:
            return imaplib.IMAP4_SSL(
                resolved_host,
                resolved_port,
                ssl_context=_tls_context(),
                timeout=settings.webmail_transport_timeout_seconds,
            )

        client = imaplib.IMAP4(
            resolved_host,
            resolved_port,
            timeout=settings.webmail_transport_timeout_seconds,
        )
        client.starttls(ssl_context=_tls_context())
        return client
    except (imaplib.IMAP4.error, OSError, ssl.SSLError) as exc:
        raise WebmailError("Mail server connection failed") from exc


def _imap(address: str, password: str, host: str | None = None, port: int | None = None) -> imaplib.IMAP4:
    transport = _mail_transport(address)
    client = _connect_imap(host or transport["imap_host"], port or transport["imap_port"])
    try:
        client.login(address, password)
        return client
    except imaplib.IMAP4.error as exc:
        _close_imap(client)
        raise WebmailError("Mailbox address or password was not accepted") from exc
    except (OSError, ssl.SSLError) as exc:
        _close_imap(client)
        raise WebmailError("Mail server connection failed") from exc


def authenticate(address: str, password: str, *, imap_host: str | None = None, imap_port: int | None = None) -> None:
    client = _imap(address, password, imap_host, imap_port)
    try:
        client.noop()
    finally:
        _close_imap(client)


def create_session(
    address: str,
    password: str,
    *,
    imap_host: str | None = None,
    imap_port: int | None = None,
    smtp_host: str | None = None,
    smtp_port: int | None = None,
) -> str:
    authenticate(address, password, imap_host=imap_host, imap_port=imap_port)
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
        store = _redis()
        store.setex(_session_key(token), settings.webmail_session_ttl_seconds, payload)
        if imap_host or smtp_host:
            transport = {
                "imap_host": imap_host or settings.webmail_imap_host,
                "imap_port": imap_port or settings.webmail_imap_port,
                "smtp_host": smtp_host or settings.webmail_smtp_host,
                "smtp_port": smtp_port or settings.webmail_smtp_port,
            }
            store.setex(
                _transport_key(address),
                settings.webmail_session_ttl_seconds,
                json.dumps(transport, separators=(",", ":")),
            )
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


def _decode_payload(value, charset: str | None = None) -> str:
    """Return MIME content as text even when the email package returns bytes.

    Non-text root parts such as application/octet-stream legitimately return
    bytes from EmailMessage.get_content(). A mailbox list must still be able to
    produce a safe snippet instead of raising TypeError while joining bytes.
    """
    if value is None:
        return ""
    if not isinstance(value, bytes):
        return str(value)

    encoding = charset or "utf-8"
    try:
        return value.decode(encoding, errors="replace")
    except (LookupError, UnicodeError):
        return value.decode("utf-8", errors="replace")


def _part_text(part) -> str:
    try:
        value = part.get_content()
    except Exception:
        value = part.get_payload(decode=True) or b""
    return _decode_payload(value, part.get_content_charset())


INCOMING_HTML_TAGS = [
    "p", "br", "div", "span", "strong", "b", "em", "i", "u", "s",
    "ul", "ol", "li", "blockquote", "a", "code", "pre", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td",
]
INCOMING_HTML_ATTRS = {
    "a": ["href", "title"],
    "table": ["role"],
    "th": ["colspan", "rowspan", "scope"],
    "td": ["colspan", "rowspan"],
}


def _html_body(message) -> str:
    parts = message.walk() if message.is_multipart() else [message]
    for part in parts:
        if part.get_content_type() != "text/html" or part.get_content_disposition() == "attachment":
            continue
        raw_html = _part_text(part)
        if not raw_html:
            continue
        # Incoming HTML is never trusted as a web page. Strip scripts, style,
        # forms, remote media and layout-control attributes. The frontend owns
        # typography, width and spacing so wildly different newsletters,
        # receipts and security messages render consistently.
        return bleach.clean(
            raw_html,
            tags=INCOMING_HTML_TAGS,
            attributes=INCOMING_HTML_ATTRS,
            protocols=["http", "https", "mailto"],
            strip=True,
            strip_comments=True,
        )[:1_000_000]
    return ""


def _conversation_segments(body_text: str, body_html: str) -> dict:
    text = body_text.replace("\r\n", "\n").replace("\r", "\n")
    main_text = text
    quoted_text = ""
    signature_text = ""
    footer_text = ""

    quote_markers = (
        "\n-----Original Message-----",
        "\n---------- Forwarded message ----------",
        "\nOn ",
    )
    quote_positions = [pos for marker in quote_markers if (pos := text.find(marker)) >= 0]
    gt_lines = [idx for idx, line in enumerate(text.split("\n")) if line.lstrip().startswith(">")]
    if gt_lines:
        lines = text.split("\n")
        char_pos = sum(len(line) + 1 for line in lines[:gt_lines[0]])
        quote_positions.append(char_pos)
    if quote_positions:
        split_at = min(quote_positions)
        main_text = text[:split_at].rstrip()
        quoted_text = text[split_at:].strip()

    signature_markers = ("\n-- \n", "\nSent from my iPhone", "\nSent from my Android", "\nGet Outlook for ")
    sig_positions = [pos for marker in signature_markers if (pos := main_text.find(marker)) >= 0]
    if sig_positions:
        split_at = min(sig_positions)
        signature_text = main_text[split_at:].strip()
        main_text = main_text[:split_at].rstrip()

    lower_main = main_text.lower()
    footer_markers = ("unsubscribe", "privacy policy", "manage preferences", "confidentiality notice")
    footer_candidates = [lower_main.rfind(marker) for marker in footer_markers if lower_main.rfind(marker) >= max(0, len(lower_main) - 1800)]
    if footer_candidates:
        split_at = min(footer_candidates)
        line_start = main_text.rfind("\n", 0, split_at)
        if line_start >= 0 and len(main_text) - line_start <= 2200:
            footer_text = main_text[line_start:].strip()
            main_text = main_text[:line_start].rstrip()

    main_html = body_html
    quoted_html = ""
    if body_html:
        lower_html = body_html.lower()
        blockquote_at = lower_html.find("<blockquote")
        if blockquote_at >= 0:
            main_html = body_html[:blockquote_at].rstrip()
            quoted_html = body_html[blockquote_at:].strip()

    return {
        "main_text": main_text,
        "quoted_text": quoted_text,
        "signature_text": signature_text,
        "footer_text": footer_text,
        "main_html": main_html,
        "quoted_html": quoted_html,
        "has_quoted_history": bool(quoted_text or quoted_html),
        "has_signature": bool(signature_text),
        "has_footer": bool(footer_text),
    }


def _render_contract(body_text: str, body_html: str, attachments: list[dict], scan: MimeScan, scan_engine: str, raw: bytes) -> dict:
    normalized_text = body_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized_text.split("\n") if normalized_text else []
    longest_line = max((len(line) for line in lines), default=0)
    html_lower = body_html.lower()
    link_count = html_lower.count("<a ") + normalized_text.lower().count("http://") + normalized_text.lower().count("https://")
    table_count = html_lower.count("<table")
    heading_count = sum(html_lower.count(f"<h{level}") for level in range(1, 7))
    quote_count = html_lower.count("<blockquote") + sum(1 for line in lines if line.lstrip().startswith(">"))
    segments = _conversation_segments(body_text, body_html)
    cpp_profile = execute_binary("native.blob_profile", normalized_text.encode("utf-8", errors="replace"))
    metrics = {
        "has_html": bool(body_html),
        "characters": len(normalized_text),
        "lines": len(lines),
        "longest_line": longest_line,
        "table_count": table_count,
        "heading_count": heading_count,
        "quote_count": quote_count,
        "link_count": link_count,
        "attachment_count": len(attachments),
    }
    go_plan = execute_mail_render_plan(metrics)
    java_profile = execute_mail_structured_profile(metrics)
    if body_html:
        kind = "structured_html"
    elif longest_line > 220 or (lines and len(lines) <= 3 and len(normalized_text) > 800):
        kind = "longform_plain"
    else:
        kind = "plain"
    if table_count:
        kind = "transactional_table"
    layout = str(go_plan.value.get("layout") or "")
    if layout == "transactional":
        kind = "transactional_table"
    elif layout == "longform_plain":
        kind = "longform_plain"
    density = str(go_plan.value.get("density") or ("compact" if len(normalized_text) < 800 else "comfortable" if len(normalized_text) < 6000 else "long"))
    return {
        "version": 1,
        "kind": kind,
        "density": density,
        "has_html": bool(body_html),
        "has_plain": bool(body_text.strip()),
        "character_count": len(normalized_text),
        "line_count": len(lines),
        "longest_line": longest_line,
        "table_count": table_count,
        "heading_count": heading_count,
        "quote_count": quote_count,
        "link_count": link_count,
        "attachment_count": len(attachments),
        "engines": {
            "mime_structure": scan_engine,
            "text_shape": cpp_profile.engine,
            "layout_plan": go_plan.engine,
            "structured_profile": java_profile.engine,
            "orchestrator": "python",
        },
        "safe_html_policy": "semantic-tags-no-style-no-script-no-form-no-remote-media",
        "conversation": {
            "has_quoted_history": segments["has_quoted_history"],
            "has_signature": segments["has_signature"],
            "has_footer": segments["has_footer"],
            "collapse_quoted_history": bool(java_profile.value.get("collapse_quoted_history")) or segments["has_quoted_history"],
            "main_text": segments["main_text"],
            "quoted_text": segments["quoted_text"],
            "signature_text": segments["signature_text"],
            "footer_text": segments["footer_text"],
            "main_html": segments["main_html"],
            "quoted_html": segments["quoted_html"],
        },
        "layout_plan": go_plan.value,
        "structured_profile": java_profile.value,
    }


def _plain_body(message) -> str:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain" and part.get_content_disposition() != "attachment":
                return _part_text(part)
        for part in message.walk():
            if part.get_content_type() == "text/html" and part.get_content_disposition() != "attachment":
                html = _part_text(part)
                return unescape(sub(r"<[^>]+>", " ", html))
        return ""

    value = _part_text(message)
    if message.get_content_type() == "text/html":
        value = unescape(sub(r"<[^>]+>", " ", value))
    return value


def _attachments(message, scan: MimeScan | None = None) -> list[dict]:
    # The Rust/Python pre-scan is deliberately conservative. A zero signal
    # means there is no filename/name/Content-Disposition marker anywhere in
    # the raw RFC822 bytes, so the authoritative Python MIME tree cannot expose
    # an attachment through the fields this function uses.
    if scan is not None and scan.attachment_signals == 0:
        return []

    rows = []
    attachment_index = 0
    for part in message.walk():
        filename = part.get_filename()
        disposition = part.get_content_disposition()
        if filename or disposition == "attachment":
            payload = part.get_payload(decode=True) or b""
            digest = execute_binary("mail.sha256", payload)
            profile = execute_binary("native.blob_profile", payload)
            rows.append(
                {
                    "index": attachment_index,
                    "filename": filename or f"attachment-{attachment_index + 1}",
                    "content_type": part.get_content_type(),
                    "size": len(payload),
                    "sha256": digest.value,
                    "fingerprint": str(profile.value.fnv1a64),
                    "nul_bytes": profile.value.nul_bytes,
                    "control_bytes": profile.value.control_bytes,
                    "high_bytes": profile.value.high_bytes,
                    "profile_engine": profile.engine,
                }
            )
            attachment_index += 1
    return rows


def _normalized_thread_subject(value: str) -> str:
    text = " ".join(str(value or "").split()).strip().lower()
    previous = None
    while text and text != previous:
        previous = text
        text = sub(r"^(?:(?:re|fw|fwd)\s*:\s*)+", "", text, flags=0).strip()
        text = sub(r"^\[(?:external|ext|spam|bulk)\]\s*", "", text, flags=0).strip()
    return text[:255]


def _message_id_tokens(value: str) -> list[str]:
    raw = str(value or "")
    tokens = []
    for match in __import__("re").findall(r"<[^>]{1,500}>", raw):
        normalized = match.strip().lower()
        if normalized not in tokens:
            tokens.append(normalized)
    return tokens[:100]


def _thread_metadata(parsed) -> dict:
    message_id = _decode(parsed.get("Message-ID"))
    in_reply_to = _decode(parsed.get("In-Reply-To"))
    references = _decode(parsed.get("References"))
    subject = _decode(parsed.get("Subject")) or "(no subject)"
    return {
        "message_id_tokens": _message_id_tokens(message_id),
        "in_reply_to_tokens": _message_id_tokens(in_reply_to),
        "reference_tokens": _message_id_tokens(references),
        "subject_key": _normalized_thread_subject(subject),
    }


def _message_json(uid: str, raw: bytes, meta: bytes | str = b"", include_body: bool = False) -> dict:
    scan_execution = execute_binary("mail.mime_scan", raw)
    scan = scan_execution.value
    scan_engine = scan_execution.engine
    parsed = BytesParser(policy=policy.default).parsebytes(raw)
    meta_text = meta.decode(errors="replace") if isinstance(meta, bytes) else str(meta)
    body = _plain_body(parsed)
    normalized = " ".join(body.split())
    attachment_walk = "skipped" if scan.attachment_signals == 0 else "walked"
    MAIL_MIME_SCAN_TOTAL.labels(scan_engine, attachment_walk).inc()
    MAIL_MIME_SCAN_BYTES.labels(scan_engine).observe(scan.bytes)
    if scan.nul_bytes:
        logger.debug(
            "Webmail MIME pre-scan detected NUL bytes uid=%s engine=%s count=%s",
            uid,
            scan_engine,
            scan.nul_bytes,
        )
    attachments = _attachments(parsed, scan)
    safe_html = _html_body(parsed) if include_body else ""
    thread = _thread_metadata(parsed)
    row = {
        "uid": uid,
        "message_id": _decode(parsed.get("Message-ID")),
        "thread": thread,
        "in_reply_to": _decode(parsed.get("In-Reply-To")),
        "references": _decode(parsed.get("References")),
        "from": _decode(parsed.get("From")),
        "to": _decode(parsed.get("To")),
        "cc": _decode(parsed.get("Cc")),
        "reply_to": _decode(parsed.get("Reply-To")),
        "return_path": _decode(parsed.get("Return-Path")),
        "authentication_results": _decode(parsed.get("Authentication-Results")),
        "received_spf": _decode(parsed.get("Received-SPF")),
        "dkim_signature_present": bool(parsed.get("DKIM-Signature")),
        "subject": _decode(parsed.get("Subject")) or "(no subject)",
        "date": _decode(parsed.get("Date")),
        "seen": "\\Seen" in meta_text,
        "flagged": "\\Flagged" in meta_text,
        "answered": "\\Answered" in meta_text,
        "draft": "\\Draft" in meta_text,
        "snippet": normalized[:240],
        "attachments": attachments,
    }
    if include_body:
        row["body_text"] = body
        row["body_html"] = safe_html
        row["render_contract"] = _render_contract(body, safe_html, attachments, scan, scan_engine, raw)
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
        _close_imap(client)


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
        uids = data[0].decode(errors="replace").split() if data and data[0] else []
        uids.reverse()
        selected = uids[offset : offset + limit]
        rows = []
        skipped = 0
        for uid in selected:
            try:
                raw, meta = _fetch_raw(client, uid, mark_seen=False)
                rows.append(_message_json(uid, raw, meta))
            except Exception as exc:
                skipped += 1
                logger.warning("Skipping unreadable webmail message folder=%s uid=%s: %s", folder, uid, exc)
        return {
            "items": rows,
            "total": len(uids),
            "folder": folder,
            "limit": limit,
            "offset": offset,
            "query": query.strip(),
            "skipped": skipped,
        }
    finally:
        _close_imap(client)



def messages_with_bodies(
    address: str,
    password: str,
    folder: str = "INBOX",
    limit: int = 20,
    offset: int = 0,
    query: str = "",
) -> dict:
    """Fetch a bounded page of full messages over one IMAP session.

    This is intended for intelligence/scanning workloads. It uses BODY.PEEK so
    analysis never marks a message as read merely because a model inspected it.
    """
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

        uids = data[0].decode(errors="replace").split() if data and data[0] else []
        uids.reverse()
        selected = uids[offset : offset + limit]
        rows = []
        skipped = 0
        for uid in selected:
            try:
                raw, meta = _fetch_raw(client, uid, mark_seen=False)
                rows.append(_message_json(uid, raw, meta, include_body=True))
            except Exception as exc:
                skipped += 1
                logger.warning(
                    "Skipping unreadable intelligence message folder=%s uid=%s: %s",
                    folder,
                    uid,
                    exc,
                )
        return {
            "items": rows,
            "total": len(uids),
            "folder": folder,
            "limit": limit,
            "offset": offset,
            "query": query.strip(),
            "skipped": skipped,
        }
    finally:
        _close_imap(client)


def message(address: str, password: str, uid: str, folder: str = "INBOX") -> dict:
    client = _imap(address, password)
    try:
        _select(client, folder, readonly=False)
        raw, meta = _fetch_raw(client, uid, mark_seen=True)
        try:
            return _message_json(uid, raw, meta, include_body=True)
        except Exception as exc:
            logger.warning("Unable to parse webmail message folder=%s uid=%s: %s", folder, uid, exc)
            raise WebmailError("Unable to read message") from exc
    finally:
        _close_imap(client)


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
        publish_mailbox_change(address, "flags_changed")
        try:
            return _message_json(uid, raw, meta)
        except Exception as exc:
            logger.warning("Unable to parse webmail message after flag update folder=%s uid=%s: %s", folder, uid, exc)
            raise WebmailError("Unable to read message") from exc
    finally:
        _close_imap(client)


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
        publish_mailbox_change(address, "message_moved")
        return {"moved": True, "uid": uid, "from": folder, "to": destination}
    finally:
        _close_imap(client)


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
        publish_mailbox_change(address, "message_deleted")
        return {"deleted": True, "uid": uid, "folder": folder}
    finally:
        _close_imap(client)


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
        publish_mailbox_change(address, "changed")
        return {"saved": True, "message_id": msg["Message-ID"], "folder": "Drafts"}
    finally:
        _close_imap(client)


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
        _close_imap(client)


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
    request_read_receipt: bool = False,
) -> dict:
    msg = EmailMessage()
    msg["From"] = sender_header(address)
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg["Date"] = format_datetime(datetime.now(timezone.utc))
    msg["Message-ID"] = make_msgid(domain=address.split("@", 1)[-1])
    if request_read_receipt:
        msg["Disposition-Notification-To"] = address
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
    transport = _mail_transport(address)
    try:
        with smtplib.SMTP(transport["smtp_host"], transport["smtp_port"], timeout=settings.webmail_transport_timeout_seconds) as smtp:
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
            _close_imap(client)
    except Exception:
        pass
    publish_mailbox_change(address, "changed")
    return {"sent": True, "message_id": msg["Message-ID"], "recipients": len(recipients), "attachments": len(attachments or [])}
