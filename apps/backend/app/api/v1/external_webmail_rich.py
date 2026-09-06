from __future__ import annotations

import imaplib
import re
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from html import escape
from html.parser import HTMLParser
from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel, EmailStr, Field

from app.api.v1.external_webmail import EXTERNAL_COOKIE
from app.services.external_webmail import (
    ExternalWebmailError,
    _attachment_rows,
    _ensure_folder,
    _folder_for,
    _imap,
    _list_folder_names,
    _sender_header,
    _smtp,
    session_config,
)

router = APIRouter(prefix="/webmail/external", tags=["external-webmail-rich"])

_ALLOWED_TAGS = {
    "p", "div", "br", "strong", "b", "em", "i", "u", "ul", "ol", "li",
    "blockquote", "a", "span", "font", "pre", "code",
}
_ALLOWED_STYLE_PROPERTIES = {
    "text-align", "font-family", "font-size", "color", "background-color",
    "font-weight", "font-style", "text-decoration", "margin", "margin-left",
    "padding-left", "border-left", "line-height",
}
_STYLE_VALUE_RE = re.compile(r"^[#(),.%\-\sA-Za-z0-9]+$")


class RichAttachment(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(default="application/octet-stream", min_length=1, max_length=255)
    content_b64: str = Field(min_length=1, max_length=25_000_000)


class RichSend(BaseModel):
    to: list[EmailStr] = Field(min_length=1, max_length=100)
    cc: list[EmailStr] = Field(default_factory=list, max_length=100)
    bcc: list[EmailStr] = Field(default_factory=list, max_length=100)
    subject: str = Field(default="", max_length=998)
    body_text: str = Field(default="", max_length=2_000_000)
    body_html: str = Field(default="", max_length=2_000_000)
    attachments: list[RichAttachment] = Field(default_factory=list, max_length=20)
    in_reply_to: str = Field(default="", max_length=998)
    references: str = Field(default="", max_length=4000)


class RichDraft(BaseModel):
    to: list[EmailStr] = Field(default_factory=list, max_length=100)
    cc: list[EmailStr] = Field(default_factory=list, max_length=100)
    bcc: list[EmailStr] = Field(default_factory=list, max_length=100)
    subject: str = Field(default="", max_length=998)
    body_text: str = Field(default="", max_length=2_000_000)
    body_html: str = Field(default="", max_length=2_000_000)


class _MailHtmlSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.output: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag not in _ALLOWED_TAGS:
            return
        safe_attrs: list[str] = []
        for raw_name, raw_value in attrs:
            name = raw_name.lower()
            value = str(raw_value or "").strip()
            if tag == "a" and name == "href":
                parsed = urlparse(value)
                if parsed.scheme.lower() not in {"http", "https", "mailto"}:
                    continue
                safe_attrs.append(f'href="{escape(value, quote=True)}"')
                safe_attrs.append('rel="noopener noreferrer"')
            elif tag == "a" and name == "title":
                safe_attrs.append(f'title="{escape(value, quote=True)}"')
            elif tag == "font" and name in {"color", "face", "size"}:
                safe_attrs.append(f'{name}="{escape(value[:100], quote=True)}"')
            elif name == "style":
                declarations: list[str] = []
                for declaration in value.split(";"):
                    key, sep, style_value = declaration.partition(":")
                    key = key.strip().lower()
                    style_value = style_value.strip()
                    if not sep or key not in _ALLOWED_STYLE_PROPERTIES or not _STYLE_VALUE_RE.fullmatch(style_value[:200]):
                        continue
                    declarations.append(f"{key}:{style_value[:200]}")
                if declarations:
                    safe_attrs.append(f'style="{escape(";".join(declarations), quote=True)}"')
        suffix = f" {' '.join(safe_attrs)}" if safe_attrs else ""
        self.output.append(f"<{tag}{suffix}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "br":
            self.output.append("<br>")
        else:
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _ALLOWED_TAGS and tag != "br":
            self.output.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        self.output.append(escape(data))


def _sanitize_html(value: str) -> str:
    if not value.strip():
        return ""
    parser = _MailHtmlSanitizer()
    parser.feed(value)
    parser.close()
    return "".join(parser.output).strip()


def _config(token: str | None):
    try:
        return session_config(token or "")
    except ExternalWebmailError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def _message(
    config,
    *,
    to: list[str],
    cc: list[str],
    bcc: list[str],
    subject: str,
    body_text: str,
    body_html: str,
    attachments: list[dict] | None = None,
    in_reply_to: str = "",
    references: str = "",
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = _sender_header(config)
    if to:
        msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    if bcc:
        # Bcc is deliberately not added as a message header.
        pass
    msg["Subject"] = subject
    msg["Date"] = format_datetime(datetime.now(timezone.utc))
    msg["Message-ID"] = make_msgid(domain=config.address.split("@", 1)[-1])
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to[:998]
    if references:
        msg["References"] = references[:4000]
    msg.set_content(body_text or "")
    safe_html = _sanitize_html(body_html)
    if safe_html:
        msg.add_alternative(safe_html, subtype="html")
    for payload, maintype, subtype, filename in _attachment_rows(attachments):
        msg.add_attachment(payload, maintype=maintype, subtype=subtype, filename=filename)
    return msg


def _append(config, folder_role: str, fallback: str, msg: EmailMessage, flags: str) -> str:
    client = _imap(config)
    try:
        names = _list_folder_names(client)
        target = _folder_for(names, folder_role) or fallback
        _ensure_folder(client, target)
        status, _ = client.append(target, flags, imaplib.Time2Internaldate(datetime.now().timestamp()), msg.as_bytes())
        if status != "OK":
            raise ExternalWebmailError(f"Unable to save message in {target}")
        return target
    finally:
        try:
            client.logout()
        except Exception:
            pass


@router.post("/send-rich", status_code=202)
def send_rich(
    payload: RichSend,
    token: Annotated[str | None, Cookie(alias=EXTERNAL_COOKIE)] = None,
):
    config = _config(token)
    to = [str(value).lower() for value in payload.to]
    cc = [str(value).lower() for value in payload.cc]
    bcc = [str(value).lower() for value in payload.bcc]
    msg = _message(
        config,
        to=to,
        cc=cc,
        bcc=bcc,
        subject=payload.subject,
        body_text=payload.body_text,
        body_html=payload.body_html,
        attachments=[item.model_dump() for item in payload.attachments],
        in_reply_to=payload.in_reply_to,
        references=payload.references,
    )
    smtp = _smtp(config)
    try:
        smtp.send_message(msg, from_addr=config.address, to_addrs=[*to, *cc, *bcc])
    except (smtplib.SMTPException, OSError, ssl.SSLError) as exc:
        raise HTTPException(status_code=503, detail="Unable to send external message") from exc
    finally:
        try:
            smtp.quit()
        except Exception:
            try:
                smtp.close()
            except Exception:
                pass
    try:
        _append(config, "sent", "Sent", msg, "\\Seen")
    except ExternalWebmailError:
        # Delivery already succeeded. A provider-specific Sent-folder problem
        # must not turn a successfully sent message into an apparent failure.
        pass
    return {"sent": True, "message_id": str(msg["Message-ID"]), "rich_html": bool(_sanitize_html(payload.body_html))}


@router.post("/drafts-rich", status_code=201)
def save_rich_draft(
    payload: RichDraft,
    token: Annotated[str | None, Cookie(alias=EXTERNAL_COOKIE)] = None,
):
    config = _config(token)
    msg = _message(
        config,
        to=[str(value).lower() for value in payload.to],
        cc=[str(value).lower() for value in payload.cc],
        bcc=[str(value).lower() for value in payload.bcc],
        subject=payload.subject,
        body_text=payload.body_text,
        body_html=payload.body_html,
    )
    try:
        folder = _append(config, "drafts", "Drafts", msg, "\\Draft")
    except ExternalWebmailError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"saved": True, "message_id": str(msg["Message-ID"]), "folder": folder}
