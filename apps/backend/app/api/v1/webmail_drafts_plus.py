import imaplib
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel, EmailStr, Field

from app.api.v1.external_webmail import EXTERNAL_COOKIE
from app.core.config import settings
from app.services.external_webmail import (
    ExternalWebmailError,
    _attachment_rows as external_attachment_rows,
    _ensure_folder as external_ensure_folder,
    _folder_for as external_folder_for,
    _imap as external_imap,
    _list_folder_names as external_folder_names,
    _sender_header as external_sender_header,
    session_config,
)
from app.services.webmail import (
    WebmailError,
    _ensure_folder,
    _imap,
    sender_header,
    session_credentials,
)
from app.services.webmail_polish import _attachment_payloads

router = APIRouter(tags=["webmail-drafts"])


class DraftAttachment(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(default="application/octet-stream", min_length=1, max_length=255)
    content_b64: str = Field(min_length=1, max_length=25_000_000)


class FullDraft(BaseModel):
    to: list[EmailStr] = Field(default_factory=list, max_length=100)
    cc: list[EmailStr] = Field(default_factory=list, max_length=100)
    bcc: list[EmailStr] = Field(default_factory=list, max_length=100)
    subject: str = Field(default="", max_length=998)
    body_text: str = Field(default="", max_length=2_000_000)
    attachments: list[DraftAttachment] = Field(default_factory=list, max_length=20)


def _headers(msg: EmailMessage, to: list[str], cc: list[str], bcc: list[str], subject: str) -> None:
    if to:
        msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    if bcc:
        # Bcc is deliberately present in a saved draft. SMTP send paths remove
        # it from the transmitted message headers while still using recipients.
        msg["Bcc"] = ", ".join(bcc)
    msg["Subject"] = subject
    msg["Date"] = format_datetime(datetime.now(timezone.utc))


def _payload(payload: FullDraft) -> tuple[list[str], list[str], list[str]]:
    return (
        [str(value).lower() for value in payload.to],
        [str(value).lower() for value in payload.cc],
        [str(value).lower() for value in payload.bcc],
    )


@router.post("/webmail/drafts-rich", status_code=201)
def save_internal_full_draft(
    payload: FullDraft,
    token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None,
):
    try:
        address, password = session_credentials(token or "")
        to, cc, bcc = _payload(payload)
        msg = EmailMessage()
        msg["From"] = sender_header(address)
        _headers(msg, to, cc, bcc, payload.subject)
        msg["Message-ID"] = make_msgid(domain=address.split("@", 1)[-1])
        msg.set_content(payload.body_text)
        for raw, maintype, subtype, filename in _attachment_payloads(
            [item.model_dump() for item in payload.attachments]
        ):
            msg.add_attachment(raw, maintype=maintype, subtype=subtype, filename=filename)

        client = _imap(address, password)
        try:
            _ensure_folder(client, "Drafts")
            status, _ = client.append(
                "Drafts",
                "\\Draft",
                imaplib.Time2Internaldate(datetime.now().timestamp()),
                msg.as_bytes(),
            )
            if status != "OK":
                raise WebmailError("Unable to save draft")
        finally:
            try:
                client.logout()
            except Exception:
                pass
        return {"saved": True, "message_id": msg["Message-ID"], "folder": "Drafts"}
    except WebmailError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/webmail/external/drafts-rich", status_code=201)
def save_external_full_draft(
    payload: FullDraft,
    token: Annotated[str | None, Cookie(alias=EXTERNAL_COOKIE)] = None,
):
    try:
        config = session_config(token or "")
        to, cc, bcc = _payload(payload)
        msg = EmailMessage()
        msg["From"] = external_sender_header(config)
        _headers(msg, to, cc, bcc, payload.subject)
        msg["Message-ID"] = make_msgid(domain=config.address.split("@", 1)[-1])
        msg.set_content(payload.body_text)
        for raw, maintype, subtype, filename in external_attachment_rows(
            [item.model_dump() for item in payload.attachments]
        ):
            msg.add_attachment(raw, maintype=maintype, subtype=subtype, filename=filename)

        client = external_imap(config)
        try:
            names = external_folder_names(client)
            drafts = external_folder_for(names, "drafts") or "Drafts"
            external_ensure_folder(client, drafts)
            status, _ = client.append(
                drafts,
                "\\Draft",
                imaplib.Time2Internaldate(datetime.now().timestamp()),
                msg.as_bytes(),
            )
            if status != "OK":
                raise ExternalWebmailError("Unable to save external draft")
        finally:
            try:
                client.logout()
            except Exception:
                pass
        return {"saved": True, "message_id": msg["Message-ID"], "folder": drafts}
    except ExternalWebmailError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
