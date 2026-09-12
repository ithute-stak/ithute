import re
from email import policy
from email.parser import BytesParser
from typing import Annotated

import bleach
from fastapi import APIRouter, Cookie, HTTPException, Query

from app.api.v1.external_webmail import EXTERNAL_COOKIE
from app.core.config import settings
from app.services.external_webmail import (
    ExternalWebmailError,
    _fetch_raw as external_fetch_raw,
    _imap as external_imap,
    _select as external_select,
    session_config,
)
from app.services.webmail import (
    WebmailError,
    _fetch_raw,
    _imap,
    _select,
    session_credentials,
)

router = APIRouter(tags=["webmail-content"])

ALLOWED_TAGS = [
    "a", "abbr", "b", "blockquote", "br", "caption", "code", "col", "colgroup",
    "dd", "del", "div", "dl", "dt", "em", "h1", "h2", "h3", "h4", "h5", "h6",
    "hr", "i", "li", "ol", "p", "pre", "s", "small", "span", "strong", "sub", "sup",
    "table", "tbody", "td", "tfoot", "th", "thead", "tr", "u", "ul",
]
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title"],
    "td": ["colspan", "rowspan", "align"],
    "th": ["colspan", "rowspan", "align"],
    "table": ["border", "cellpadding", "cellspacing", "width"],
    "col": ["span", "width"],
}
REMOTE_IMAGE_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)


def _part_text(part) -> str:
    try:
        return part.get_content()
    except Exception:
        payload = part.get_payload(decode=True) or b""
        return payload.decode(part.get_content_charset() or "utf-8", errors="replace")


def _html_body(raw: bytes) -> tuple[str, bool, int]:
    parsed = BytesParser(policy=policy.default).parsebytes(raw)
    html_value = ""
    if parsed.is_multipart():
        for part in parsed.walk():
            if (
                part.get_content_type() == "text/html"
                and part.get_content_disposition() != "attachment"
            ):
                html_value = _part_text(part)
                break
    elif parsed.get_content_type() == "text/html":
        html_value = _part_text(parsed)

    if not html_value:
        return "", False, 0

    html_value = SCRIPT_STYLE_RE.sub("", html_value)
    image_count = len(REMOTE_IMAGE_RE.findall(html_value))
    # Remote images are removed server-side by default. This prevents tracking
    # pixels and third-party content from loading just because a message opened.
    html_value = REMOTE_IMAGE_RE.sub("", html_value)
    safe = bleach.clean(
        html_value,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=["http", "https", "mailto"],
        strip=True,
    )
    return safe[:2_000_000], True, image_count


def _uid(value: str) -> str:
    if not value.isdigit():
        raise HTTPException(status_code=422, detail="Invalid IMAP UID")
    return value


@router.get("/webmail/messages/{uid}/content")
def internal_content(
    uid: str,
    folder: str = Query(default="INBOX", min_length=1, max_length=255),
    token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None,
):
    try:
        address, password = session_credentials(token or "")
        client = _imap(address, password)
        try:
            _select(client, folder, readonly=True)
            raw, _ = _fetch_raw(client, _uid(uid), mark_seen=False)
        finally:
            try:
                client.logout()
            except Exception:
                pass
        html_value, has_html, blocked = _html_body(raw)
        return {
            "body_html": html_value,
            "has_html": has_html,
            "remote_images_blocked": blocked,
        }
    except WebmailError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/webmail/external/messages/{uid}/content")
def external_content(
    uid: str,
    folder: str = Query(default="INBOX", min_length=1, max_length=255),
    token: Annotated[str | None, Cookie(alias=EXTERNAL_COOKIE)] = None,
):
    try:
        config = session_config(token or "")
        client = external_imap(config)
        try:
            external_select(client, folder, readonly=True)
            raw, _ = external_fetch_raw(client, _uid(uid), mark_seen=False)
        finally:
            try:
                client.logout()
            except Exception:
                pass
        html_value, has_html, blocked = _html_body(raw)
        return {
            "body_html": html_value,
            "has_html": has_html,
            "remote_images_blocked": blocked,
        }
    except ExternalWebmailError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
