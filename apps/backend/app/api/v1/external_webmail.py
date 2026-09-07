import re
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services.external_webmail import (
    ExternalWebmailError,
    attachment,
    delete_message,
    delete_session,
    folder_counts,
    folders,
    messages,
    move_message,
    save_draft,
    send_message,
    session_config,
    set_flags,
)
from app.services.external_webmail_read import message as read_message
from app.services.external_webmail_setup import ExternalSetupError, connect_external_account
from app.services.security_audit import record_webmail_security_event
from app.services.security_controls import (
    SecurityControlUnavailable,
    clear_webmail_login_failures,
    record_webmail_login_failure,
    webmail_login_allowed,
)

router = APIRouter(prefix="/webmail/external", tags=["external-webmail"])
UID_RE = re.compile(r"^[0-9]+$")
CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]+")
EXTERNAL_COOKIE = f"{settings.webmail_session_cookie_name}_external"


class ExternalLogin(BaseModel):
    address: EmailStr
    password: str = Field(min_length=1, max_length=512)
    username: str = Field(default="", max_length=320)
    display_name: str = Field(default="", max_length=255)
    imap_host: str = Field(default="", max_length=253)
    imap_port: int = Field(default=993, ge=1, le=65535)
    imap_security: str = Field(default="ssl", max_length=20)
    smtp_host: str = Field(default="", max_length=253)
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_security: str = Field(default="starttls", max_length=20)


class ExternalFlags(BaseModel):
    seen: bool | None = None
    flagged: bool | None = None
    answered: bool | None = None


class ExternalMove(BaseModel):
    destination: str = Field(min_length=1, max_length=255)


class ExternalAttachment(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(default="application/octet-stream", min_length=1, max_length=255)
    content_b64: str = Field(min_length=1, max_length=25_000_000)


class ExternalSend(BaseModel):
    to: list[EmailStr] = Field(min_length=1, max_length=100)
    cc: list[EmailStr] = Field(default_factory=list, max_length=100)
    bcc: list[EmailStr] = Field(default_factory=list, max_length=100)
    subject: str = Field(default="", max_length=998)
    body_text: str = Field(default="", max_length=2_000_000)
    attachments: list[ExternalAttachment] = Field(default_factory=list, max_length=20)
    in_reply_to: str = Field(default="", max_length=998)
    references: str = Field(default="", max_length=4000)


class ExternalDraft(BaseModel):
    to: list[EmailStr] = Field(default_factory=list, max_length=100)
    cc: list[EmailStr] = Field(default_factory=list, max_length=100)
    subject: str = Field(default="", max_length=998)
    body_text: str = Field(default="", max_length=2_000_000)


def _failure(exc: ExternalWebmailError, status: int = 503) -> HTTPException:
    text = str(exc)
    lower = text.lower()
    if isinstance(exc, ExternalSetupError):
        status = 401 if exc.authentication_failed else 422
    elif "session" in lower or "authentication" in lower:
        status = 401
    elif "not found" in lower:
        status = 404
    elif "not allowed" in lower or "valid" in lower or "must be" in lower:
        status = 422
    return HTTPException(status_code=status, detail=text)


def _config(token: str | None):
    try:
        return session_config(token or "")
    except ExternalWebmailError as exc:
        raise _failure(exc, 401) from exc


def _uid(value: str) -> str:
    if not UID_RE.fullmatch(value):
        raise HTTPException(status_code=422, detail="Invalid IMAP UID")
    return value


def _client_ip(request: Request) -> str:
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
    return (value or "attachment.bin")[:180]


def _record_auth_failure(db: Session, request: Request, address: str, client_ip: str, exc: Exception) -> None:
    try:
        _, locked = record_webmail_login_failure(address, client_ip)
    except SecurityControlUnavailable as control_exc:
        raise HTTPException(status_code=503, detail=str(control_exc)) from control_exc
    if locked:
        _security_event(
            db,
            request,
            address,
            "security.webmail.external.login.locked",
            "failed",
            settings.webmail_login_lock_seconds,
        )
        raise HTTPException(
            status_code=429,
            detail="Too many external mailbox sign-in failures. Try again later.",
            headers={"Retry-After": str(settings.webmail_login_lock_seconds)},
        ) from exc


@router.post("/session")
def login(payload: ExternalLogin, request: Request, response: Response, db: Session = Depends(get_db)):
    address = str(payload.address).strip().lower()
    client_ip = _client_ip(request)
    try:
        allowed, retry_after = webmail_login_allowed(address, client_ip)
    except SecurityControlUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not allowed:
        _security_event(db, request, address, "security.webmail.external.login.blocked", "rate_limited", retry_after)
        raise HTTPException(
            status_code=429,
            detail="Too many external mailbox connection attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    try:
        result = connect_external_account(
            address=address,
            username=payload.username,
            password=payload.password,
            display_name=payload.display_name,
            imap_host=payload.imap_host,
            imap_port=payload.imap_port,
            imap_security=payload.imap_security,
            smtp_host=payload.smtp_host,
            smtp_port=payload.smtp_port,
            smtp_security=payload.smtp_security,
        )
        token = result.token
        config = result.config
    except ExternalSetupError as exc:
        if exc.authentication_failed:
            _record_auth_failure(db, request, address, client_ip, exc)
            _security_event(db, request, address, "security.webmail.external.login.failed", "failed")
        else:
            # Host/port/TLS discovery errors are setup failures, not password
            # failures. Do not poison the mailbox login lockout counter.
            _security_event(db, request, address, "security.webmail.external.setup.failed", "failed")
        raise _failure(exc, 422) from exc
    except ExternalWebmailError as exc:
        _security_event(db, request, address, "security.webmail.external.setup.failed", "failed")
        raise _failure(exc, 422) from exc

    try:
        clear_webmail_login_failures(address, client_ip)
    except SecurityControlUnavailable as exc:
        delete_session(token)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    _security_event(db, request, address, "security.webmail.external.login.succeeded", "succeeded")
    response.set_cookie(
        EXTERNAL_COOKIE,
        token,
        max_age=settings.webmail_session_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/api/v1/webmail/external",
    )
    return {
        "authenticated": True,
        "auto_configured": result.auto_configured,
        **config.public_dict(),
    }


@router.get("/session")
def session(token: Annotated[str | None, Cookie(alias=EXTERNAL_COOKIE)] = None):
    config = _config(token)
    return {"authenticated": True, **config.public_dict()}


@router.delete("/session", status_code=204)
def logout(
    response: Response,
    token: Annotated[str | None, Cookie(alias=EXTERNAL_COOKIE)] = None,
):
    if token:
        try:
            delete_session(token)
        except ExternalWebmailError as exc:
            raise _failure(exc) from exc
    response.delete_cookie(EXTERNAL_COOKIE, path="/api/v1/webmail/external")


@router.get("/folders")
def list_folders(token: Annotated[str | None, Cookie(alias=EXTERNAL_COOKIE)] = None):
    try:
        return {"items": folders(_config(token))}
    except ExternalWebmailError as exc:
        raise _failure(exc) from exc


@router.get("/folder-counts")
def counts(token: Annotated[str | None, Cookie(alias=EXTERNAL_COOKIE)] = None):
    try:
        return {"items": folder_counts(_config(token))}
    except ExternalWebmailError as exc:
        raise _failure(exc) from exc


@router.get("/messages")
def list_messages(
    folder: str = Query(default="INBOX", min_length=1, max_length=255),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100000),
    q: str = Query(default="", max_length=255),
    token: Annotated[str | None, Cookie(alias=EXTERNAL_COOKIE)] = None,
):
    try:
        return messages(_config(token), folder=folder, limit=limit, offset=offset, query=q)
    except ExternalWebmailError as exc:
        raise _failure(exc) from exc


@router.get("/messages/{uid}")
def get_message(
    uid: str,
    folder: str = Query(default="INBOX", min_length=1, max_length=255),
    token: Annotated[str | None, Cookie(alias=EXTERNAL_COOKIE)] = None,
):
    try:
        return read_message(_config(token), _uid(uid), folder=folder)
    except ExternalWebmailError as exc:
        raise _failure(exc) from exc


@router.patch("/messages/{uid}/flags")
def update_flags(
    uid: str,
    payload: ExternalFlags,
    folder: str = Query(default="INBOX", min_length=1, max_length=255),
    token: Annotated[str | None, Cookie(alias=EXTERNAL_COOKIE)] = None,
):
    try:
        return set_flags(_config(token), _uid(uid), folder, payload.seen, payload.flagged, payload.answered)
    except ExternalWebmailError as exc:
        raise _failure(exc) from exc


@router.post("/messages/{uid}/move")
def move(
    uid: str,
    payload: ExternalMove,
    folder: str = Query(default="INBOX", min_length=1, max_length=255),
    token: Annotated[str | None, Cookie(alias=EXTERNAL_COOKIE)] = None,
):
    try:
        return move_message(_config(token), _uid(uid), folder, payload.destination)
    except ExternalWebmailError as exc:
        raise _failure(exc, 409) from exc


@router.delete("/messages/{uid}")
def remove(
    uid: str,
    folder: str = Query(default="INBOX", min_length=1, max_length=255),
    token: Annotated[str | None, Cookie(alias=EXTERNAL_COOKIE)] = None,
):
    try:
        return delete_message(_config(token), _uid(uid), folder)
    except ExternalWebmailError as exc:
        raise _failure(exc) from exc


@router.get("/messages/{uid}/attachments/{index}")
def download_attachment(
    uid: str,
    index: int,
    folder: str = Query(default="INBOX", min_length=1, max_length=255),
    token: Annotated[str | None, Cookie(alias=EXTERNAL_COOKIE)] = None,
):
    try:
        filename, _content_type, payload = attachment(_config(token), _uid(uid), folder, index)
    except ExternalWebmailError as exc:
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
def draft(
    payload: ExternalDraft,
    token: Annotated[str | None, Cookie(alias=EXTERNAL_COOKIE)] = None,
):
    try:
        return save_draft(
            _config(token),
            [str(value).lower() for value in payload.to],
            [str(value).lower() for value in payload.cc],
            payload.subject,
            payload.body_text,
        )
    except ExternalWebmailError as exc:
        raise _failure(exc) from exc


@router.get("/identity")
def identity(token: Annotated[str | None, Cookie(alias=EXTERNAL_COOKIE)] = None):
    config = _config(token)
    return {
        "address": config.address,
        "display_name": config.display_name,
        "provider": "external",
        "imap_host": config.imap_host,
        "smtp_host": config.smtp_host,
    }


@router.post("/send", status_code=202)
def compose(
    payload: ExternalSend,
    token: Annotated[str | None, Cookie(alias=EXTERNAL_COOKIE)] = None,
):
    try:
        return send_message(
            _config(token),
            [str(value).lower() for value in payload.to],
            [str(value).lower() for value in payload.cc],
            [str(value).lower() for value in payload.bcc],
            payload.subject,
            payload.body_text,
            [item.model_dump() for item in payload.attachments],
            payload.in_reply_to,
            payload.references,
        )
    except ExternalWebmailError as exc:
        raise _failure(exc) from exc
