import html
import re
from email import policy
from email.parser import BytesParser
from typing import Annotated

import bleach
from bleach.css_sanitizer import CSSSanitizer
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
    "a", "abbr", "b", "blockquote", "br", "caption", "center", "code", "col", "colgroup",
    "dd", "del", "div", "dl", "dt", "em", "font", "h1", "h2", "h3", "h4", "h5", "h6",
    "hr", "i", "img", "li", "ol", "p", "pre", "s", "small", "span", "strong", "sub", "sup",
    "table", "tbody", "td", "tfoot", "th", "thead", "tr", "u", "ul",
]
ALLOWED_ATTRIBUTES = {
    "*": ["style", "align", "dir"],
    "a": ["href", "title", "target"],
    "img": ["src", "alt", "title", "width", "height"],
    "td": ["colspan", "rowspan", "align", "valign", "width", "height"],
    "th": ["colspan", "rowspan", "align", "valign", "width", "height"],
    "table": ["border", "cellpadding", "cellspacing", "width", "height", "align"],
    "col": ["span", "width"],
    "font": ["color", "face", "size"],
}
CSS_SANITIZER = CSSSanitizer(
    allowed_css_properties=[
        "background-color", "border", "border-bottom", "border-color", "border-left",
        "border-radius", "border-right", "border-style", "border-top", "border-width",
        "color", "display", "font-family", "font-size", "font-style", "font-weight",
        "height", "letter-spacing", "line-height", "margin", "margin-bottom", "margin-left",
        "margin-right", "margin-top", "max-width", "min-width", "padding", "padding-bottom",
        "padding-left", "padding-right", "padding-top", "text-align", "text-decoration",
        "text-transform", "vertical-align", "white-space", "width", "word-break",
    ],
)
REMOTE_IMAGE_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
IMG_ALT_RE = re.compile(r"""\balt\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.IGNORECASE)
EMPTY_SAFE_LINK_RE = re.compile(
    r'(<a\b[^>]*\bhref=["\'](?:https?://|mailto:)[^"\']+["\'][^>]*>)\s*(</a\s*>)',
    re.IGNORECASE,
)
SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)


def _part_text(part) -> str:
    try:
        return part.get_content()
    except Exception:
        payload = part.get_payload(decode=True) or b""
        return payload.decode(part.get_content_charset() or "utf-8", errors="replace")


def _html_body(raw: bytes, *, show_images: bool = False) -> tuple[str, bool, int, int]:
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
        return "", False, 0, 0

    html_value = SCRIPT_STYLE_RE.sub("", html_value)
    image_count = len(REMOTE_IMAGE_RE.findall(html_value))
    # Remote images stay blocked by default. If the user explicitly chooses to
    # show them, the sanitizer may retain only http/https image sources. Otherwise
    # preserve the human-readable alt text so image-backed action buttons remain usable.
    def _blocked_image_label(match: re.Match[str]) -> str:
        alt = IMG_ALT_RE.search(match.group(0))
        if alt is None:
            return ""
        value = next((part for part in alt.groups() if part is not None), "")
        return html.escape(value.strip())

    if not show_images:
        html_value = REMOTE_IMAGE_RE.sub(_blocked_image_label, html_value)

    safe = bleach.clean(
        html_value,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=["http", "https", "mailto"],
        css_sanitizer=CSS_SANITIZER,
        strip=True,
    )
    # A legitimate action anchor can still be empty when the sender used a
    # decorative/background-only button. Keep the safe URL clickable with a
    # neutral label instead of silently hiding the action from the user.
    safe = EMPTY_SAFE_LINK_RE.sub(r"\1Open secure link\2", safe)
    blocked = 0 if show_images else image_count
    return safe[:2_000_000], True, blocked, image_count


def _uid(value: str) -> str:
    if not value.isdigit():
        raise HTTPException(status_code=422, detail="Invalid IMAP UID")
    return value


@router.get("/webmail/messages/{uid}/content")
def internal_content(
    uid: str,
    folder: str = Query(default="INBOX", min_length=1, max_length=255),
    show_images: bool = Query(default=False),
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
        html_value, has_html, blocked, total_images = _html_body(raw, show_images=show_images)
        return {
            "body_html": html_value,
            "has_html": has_html,
            "remote_images_blocked": blocked,
            "remote_images_total": total_images,
            "remote_images_shown": bool(show_images and total_images),
        }
    except WebmailError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/webmail/external/messages/{uid}/content")
def external_content(
    uid: str,
    folder: str = Query(default="INBOX", min_length=1, max_length=255),
    show_images: bool = Query(default=False),
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
        html_value, has_html, blocked, total_images = _html_body(raw, show_images=show_images)
        return {
            "body_html": html_value,
            "has_html": has_html,
            "remote_images_blocked": blocked,
            "remote_images_total": total_images,
            "remote_images_shown": bool(show_images and total_images),
        }
    except ExternalWebmailError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
