import re
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, BeforeValidator, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import MailNode
from app.models.mail import Mailbox, MailboxStatus, MailboxStorageType
from app.services.mailboxes import normalize_destination
from app.services.security_audit import record_webmail_security_event
from app.services.security_controls import SecurityControlUnavailable, clear_webmail_login_failures, record_webmail_login_failure, webmail_login_allowed
from app.services.webmail import (
    WebmailError,
    attachment,
    create_session,
    delete_message,
    delete_session,
    display_name,
    folders,
    message,
    messages,
    move_message,
    save_display_name,
    save_draft,
    send_message,
    session_credentials,
    set_flags,
)
from app.services.webmail_polish import contact_presence, contacts, folder_counts, save_contact, save_signature, send_rich_message, signature

router = APIRouter(prefix="/webmail", tags=["webmail"])
UID_RE = re.compile(r"^[0-9]+$")
CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]+")


def _normalize_webmail_address(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("destination must be an email address")
    try:
        return normalize_destination(value)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc


WebmailAddress = Annotated[str, BeforeValidator(_normalize_webmail_address)]


class WebmailLogin(BaseModel):
    address: WebmailAddress = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=512)


class WebmailAttachment(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(default="application/octet-stream", min_length=1, max_length=255)
    content_b64: str = Field(min_length=1, max_length=25_000_000)


class WebmailSend(BaseModel):
    to: list[WebmailAddress] = Field(min_length=1, max_length=100)
    cc: list[WebmailAddress] = Field(default_factory=list, max_length=100)
    bcc: list[WebmailAddress] = Field(default_factory=list, max_length=100)
    subject: str = Field(default="", max_length=998)
    body_text: str = Field(default="", max_length=2_000_000)
    attachments: list[WebmailAttachment] = Field(default_factory=list, max_length=20)
    in_reply_to: str = Field(default="", max_length=998)
    references: str = Field(default="", max_length=4000)


class WebmailRichSend(BaseModel):
    to: list[WebmailAddress] = Field(min_length=1, max_length=100)
    cc: list[WebmailAddress] = Field(default_factory=list, max_length=100)
    bcc: list[WebmailAddress] = Field(default_factory=list, max_length=100)
    subject: str = Field(default="", max_length=998)
    body_text: str = Field(default="", max_length=2_000_000)
    body_html: str = Field(default="", max_length=2_000_000)
    signature_html: str = Field(default="", max_length=20000)
    attachments: list[WebmailAttachment] = Field(default_factory=list, max_length=20)
    in_reply_to: str = Field(default="", max_length=998)
    references: str = Field(default="", max_length=4000)


class WebmailDraft(BaseModel):
    to: list[WebmailAddress] = Field(default_factory=list, max_length=100)
    cc: list[WebmailAddress] = Field(default_factory=list, max_length=100)
    subject: str = Field(default="", max_length=998)
    body_text: str = Field(default="", max_length=2_000_000)


class WebmailFlags(BaseModel):
    seen: bool | None = None
    flagged: bool | None = None
    answered: bool | None = None


class WebmailMove(BaseModel):
    destination: str = Field(min_length=1, max_length=255)


class WebmailSignature(BaseModel):
    html: str = Field(default="", max_length=20000)


class WebmailIdentity(BaseModel):
    display_name: str = Field(default="", max_length=255)


class WebmailContact(BaseModel):
    email: EmailStr
    name: str = Field(default="", max_length=255)


def _failure(exc: WebmailError, status: int = 503) -> HTTPException:
    text = str(exc)
    if "session" in text.lower() or "authentication" in text.lower():
        status = 401
    elif "not found" in text.lower():
        status = 404
    return HTTPException(status_code=status, detail=text)


def _credentials(token: str | None) -> tuple[str, str]:
    try:
        return session_credentials(token or "")
    except WebmailError as exc:
        raise _failure(exc, 401) from exc


def _uid(value: str) -> str:
    if not UID_RE.fullmatch(value):
        raise HTTPException(status_code=422, detail="Invalid IMAP UID")
    return value


def _client_ip(request: Request) -> str:
    # Only trust the direct peer. Trusted proxy forwarding is configured at the
    # edge rather than accepting spoofable X-Forwarded-For values here.
    return request.client.host if request.client else "unknown"


def _security_event(db: Session, request: Request, address: str, action: str, outcome: str, retry_after: int | None = None) -> None:
    try:
        record_webmail_security_event(
            db,
            action=action,
            address=address,
            client_ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            request_id=getattr(request.state, "request_id", None),
            outcome=outcome,
            retry_after=retry_after,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Security audit service is unavailable") from exc


def _safe_attachment_name(filename: str) -> str:
    value = CONTROL_CHARS_RE.sub(" ", filename or "").replace("/", "_").replace("\\", "_").strip(" .")
    if not value or value in {".", ".."}:
        return "attachment.bin"
    return value[:180]


def _mailbox_transport(db: Session, address: str) -> dict:
    mailbox = db.scalar(
        select(Mailbox).where(
            Mailbox.address == address.lower(),
            Mailbox.status == MailboxStatus.active,
        )
    )
    if mailbox is None or mailbox.storage_type != MailboxStorageType.external:
        return {
            "imap_host": settings.webmail_imap_host,
            "imap_port": settings.webmail_imap_port,
            "smtp_host": settings.webmail_smtp_host,
            "smtp_port": settings.webmail_smtp_port,
        }
    if mailbox.mail_node_id is None:
        raise HTTPException(status_code=503, detail="Mailbox storage node is not assigned")
    node = db.scalar(
        select(MailNode).where(
            MailNode.id == mailbox.mail_node_id,
            MailNode.status == "active",
            (MailNode.tenant_id.is_(None)) | (MailNode.tenant_id == mailbox.tenant_id),
        )
    )
    if node is None:
        raise HTTPException(status_code=503, detail="Mailbox storage node is unavailable")
    return {
        "imap_host": node.hostname,
        "imap_port": 993,
        "smtp_host": node.hostname,
        "smtp_port": 587,
    }


@router.post("/session")
def login(payload: WebmailLogin, request: Request, response: Response, db: Session = Depends(get_db)):
    address = payload.address
    client_ip = _client_ip(request)
    try:
        allowed, retry_after = webmail_login_allowed(address, client_ip)
    except SecurityControlUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not allowed:
        _security_event(db, request, address, "security.webmail.login.blocked", "rate_limited", retry_after)
        raise HTTPException(status_code=429, detail="Too many mailbox login attempts. Try again later.", headers={"Retry-After": str(retry_after)})
    transport = _mailbox_transport(db, address)
    try:
        token = create_session(address, payload.password, **transport)
    except WebmailError as exc:
        try:
            _, locked = record_webmail_login_failure(address, client_ip)
        except SecurityControlUnavailable as control_exc:
            raise HTTPException(status_code=503, detail=str(control_exc)) from control_exc
        if locked:
            _security_event(db, request, address, "security.webmail.login.locked", "failed", settings.webmail_login_lock_seconds)
            raise HTTPException(status_code=429, detail="Too many mailbox login attempts. Try again later.", headers={"Retry-After": str(settings.webmail_login_lock_seconds)}) from exc
        _security_event(db, request, address, "security.webmail.login.failed", "failed")
        raise _failure(exc, 401) from exc
    try:
        clear_webmail_login_failures(address, client_ip)
    except SecurityControlUnavailable as exc:
        delete_session(token)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    _security_event(db, request, address, "security.webmail.login.succeeded", "succeeded")
    response.set_cookie(settings.webmail_session_cookie_name, token, max_age=settings.webmail_session_ttl_seconds, httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite, path="/api/v1/webmail")
    return {"authenticated": True, "address": address}


@router.get("/session")
def session(token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, _ = _credentials(token)
    return {"authenticated": True, "address": address}


@router.delete("/session", status_code=204)
def logout(request: Request, response: Response, token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None, db: Session = Depends(get_db)):
    address = None
    if token:
        try:
            address, _ = session_credentials(token)
        except WebmailError:
            address = None
        try:
            delete_session(token)
        except WebmailError as exc:
            raise _failure(exc) from exc
    if address:
        _security_event(db, request, address, "security.webmail.logout", "succeeded")
    response.delete_cookie(settings.webmail_session_cookie_name, path="/api/v1/webmail")


@router.get("/folders")
def list_folders(token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, password = _credentials(token)
    try:
        return {"items": folders(address, password)}
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.get("/folder-counts")
def counts(token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, password = _credentials(token)
    try:
        return {"items": folder_counts(address, password)}
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.get("/messages")
def list_messages(folder: str = Query(default="INBOX", min_length=1, max_length=255), limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0, le=100000), q: str = Query(default="", max_length=255), token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, password = _credentials(token)
    try:
        return messages(address, password, folder=folder, limit=limit, offset=offset, query=q)
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.get("/messages/{uid}")
def get_message(uid: str, folder: str = Query(default="INBOX", min_length=1, max_length=255), token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, password = _credentials(token)
    try:
        return message(address, password, uid=_uid(uid), folder=folder)
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.patch("/messages/{uid}/flags")
def update_flags(uid: str, payload: WebmailFlags, folder: str = Query(default="INBOX", min_length=1, max_length=255), token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, password = _credentials(token)
    try:
        return set_flags(address, password, _uid(uid), folder, payload.seen, payload.flagged, payload.answered)
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.post("/messages/{uid}/move")
def move(uid: str, payload: WebmailMove, folder: str = Query(default="INBOX", min_length=1, max_length=255), token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, password = _credentials(token)
    try:
        return move_message(address, password, _uid(uid), folder, payload.destination)
    except WebmailError as exc:
        raise _failure(exc, 409) from exc


@router.delete("/messages/{uid}")
def remove(uid: str, folder: str = Query(default="INBOX", min_length=1, max_length=255), token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, password = _credentials(token)
    try:
        return delete_message(address, password, _uid(uid), folder)
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.get("/messages/{uid}/attachments/{index}")
def download_attachment(uid: str, index: int, folder: str = Query(default="INBOX", min_length=1, max_length=255), token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, password = _credentials(token)
    try:
        filename, _content_type, payload = attachment(address, password, _uid(uid), folder, index)
    except WebmailError as exc:
        raise _failure(exc) from exc
    safe_name = _safe_attachment_name(filename)
    return Response(
        content=payload,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(safe_name)}",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'",
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/drafts", status_code=201)
def draft(payload: WebmailDraft, token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, password = _credentials(token)
    try:
        return save_draft(address, password, [str(value).lower() for value in payload.to], [str(value).lower() for value in payload.cc], payload.subject, payload.body_text)
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.get("/identity")
def get_identity(token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, _ = _credentials(token)
    try:
        return {"address": address, "display_name": display_name(address)}
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.put("/identity")
def put_identity(payload: WebmailIdentity, token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, _ = _credentials(token)
    try:
        result = save_display_name(address, payload.display_name)
        return {"address": address, **result}
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.get("/signature")
def get_signature(token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, _ = _credentials(token)
    try:
        return {"html": signature(address)}
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.put("/signature")
def put_signature(payload: WebmailSignature, token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, _ = _credentials(token)
    try:
        return save_signature(address, payload.html)
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.get("/contacts")
def get_contacts(q: str = Query(default="", max_length=255), token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, _ = _credentials(token)
    try:
        return {"items": contacts(address, q)}
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.get("/business-contacts")
def get_business_contacts(
    limit: int = Query(default=12, ge=1, le=50),
    token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None,
):
    address, _ = _credentials(token)
    try:
        rows = contacts(address)
        presence = contact_presence([str(row.get("email") or "") for row in rows])
        enriched = []
        for row in rows:
            email_address = str(row.get("email") or "").lower()
            interactions = int(row.get("interactions") or 0)
            last_seen = str(row.get("last_seen") or "")
            source_set = {str(item) for item in row.get("sources", [])}
            enriched.append({
                **row,
                "online": bool(presence.get(email_address, False)),
                "business": bool("incoming" in source_set or "outgoing" in source_set),
                "score": interactions * 10 + (100000 if presence.get(email_address, False) else 0),
                "last_seen": last_seen,
            })
        enriched.sort(
            key=lambda row: (
                bool(row["online"]),
                int(row["score"]),
                str(row["last_seen"]),
                str(row.get("name") or "").lower(),
                str(row.get("email") or "").lower(),
            ),
            reverse=True,
        )
        return {"items": enriched[:limit]}
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.get("/business-conversation")
def get_business_conversation(
    email: WebmailAddress,
    limit: int = Query(default=25, ge=1, le=50),
    token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None,
):
    address, password = _credentials(token)
    try:
        inbox = messages(address, password, folder="INBOX", limit=limit, offset=0, query=email)
        sent = messages(address, password, folder="Sent", limit=limit, offset=0, query=email)
        rows = [
            *[{**row, "folder": "INBOX"} for row in inbox.get("items", [])],
            *[{**row, "folder": "Sent"} for row in sent.get("items", [])],
        ]
        rows.sort(key=lambda row: str(row.get("date") or ""), reverse=True)
        return {"items": rows[:limit], "email": email}
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.post("/contacts", status_code=201)
def put_contact(payload: WebmailContact, token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, _ = _credentials(token)
    try:
        return save_contact(address, str(payload.email), payload.name)
    except WebmailError as exc:
        raise _failure(exc, 422) from exc


@router.post("/send", status_code=202)
def compose(payload: WebmailSend, token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, password = _credentials(token)
    recipients = [str(value).lower() for value in payload.to]
    cc = [str(value).lower() for value in payload.cc]
    bcc = [str(value).lower() for value in payload.bcc]
    try:
        return send_message(address, password, recipients, cc, bcc, payload.subject, payload.body_text, [item.model_dump() for item in payload.attachments], payload.in_reply_to, payload.references)
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.post("/send-rich", status_code=202)
def compose_rich(payload: WebmailRichSend, token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, password = _credentials(token)
    try:
        return send_rich_message(
            address,
            password,
            [str(v).lower() for v in payload.to],
            [str(v).lower() for v in payload.cc],
            [str(v).lower() for v in payload.bcc],
            payload.subject,
            payload.body_text,
            payload.body_html,
            payload.signature_html,
            [item.model_dump() for item in payload.attachments],
            payload.in_reply_to,
            payload.references,
        )
    except WebmailError as exc:
        raise _failure(exc) from exc
