from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.external_webmail import EXTERNAL_COOKIE
from app.core.config import settings
from app.core.security import encrypt_secret
from app.db.session import get_db
from app.models import ConnectedMailAccount, MailSnooze, Mailbox, MailboxStatus
from app.services.connected_mail import (
    ConnectedMailError,
    attachment as connected_attachment,
    config_for_account,
    delete_message as connected_delete,
    folder_counts as connected_counts,
    folders as connected_folders,
    message as connected_message,
    messages as connected_messages,
    move_message as connected_move,
    save_draft as connected_save_draft,
    send_message as connected_send,
    set_flags as connected_set_flags,
    test_account as connected_test,
)
from app.services.external_webmail import ExternalWebmailError, session_config as external_session_config
from app.services.mail_migration import migrate_imap_mailbox
from app.services.mail_oauth import MailOAuthError, begin_oauth, consume_state, exchange_code, provider_capabilities
from app.services.mail_provider_detection import migration_provider_key, provider_detection_payload
from app.services.mail_search import message_timestamp
from app.services.mail_threads import annotate_thread
from app.services.webmail import WebmailError, messages as hosted_messages, session_credentials


router = APIRouter(prefix="/webmail", tags=["webmail-connected-accounts"])
HOSTED_COOKIE = settings.webmail_session_cookie_name


class RememberExternal(BaseModel):
    label: str = Field(default="", max_length=255)
    sync_enabled: bool = True


class AccountUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=255)
    sync_enabled: bool | None = None


class MessageFlags(BaseModel):
    seen: bool | None = None
    flagged: bool | None = None
    answered: bool | None = None


class MessageMove(BaseModel):
    destination: str = Field(min_length=1, max_length=255)


class ConnectedAttachmentIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(default="application/octet-stream", min_length=1, max_length=255)
    content_b64: str = Field(min_length=1, max_length=25_000_000)


class ConnectedSendIn(BaseModel):
    to: list[EmailStr] = Field(min_length=1, max_length=100)
    cc: list[EmailStr] = Field(default_factory=list, max_length=100)
    bcc: list[EmailStr] = Field(default_factory=list, max_length=100)
    subject: str = Field(default="", max_length=998)
    body_text: str = Field(default="", max_length=2_000_000)
    body_html: str = Field(default="", max_length=2_000_000)
    attachments: list[ConnectedAttachmentIn] = Field(default_factory=list, max_length=20)
    in_reply_to: str = Field(default="", max_length=998)
    references: str = Field(default="", max_length=4000)


class ConnectedDraftIn(BaseModel):
    to: list[EmailStr] = Field(default_factory=list, max_length=100)
    cc: list[EmailStr] = Field(default_factory=list, max_length=100)
    subject: str = Field(default="", max_length=998)
    body_text: str = Field(default="", max_length=2_000_000)


class SnoozeIn(BaseModel):
    source_key: str = Field(default="hosted", min_length=1, max_length=80)
    folder: str = Field(default="INBOX", min_length=1, max_length=255)
    message_uid: str = Field(min_length=1, max_length=128)
    message_id: str = Field(default="", max_length=998)
    connected_account_id: UUID | None = None
    wake_at: datetime


def _hosted_identity(token: str | None, db: Session) -> tuple[Mailbox, str]:
    try:
        address, password = session_credentials(token or "")
    except WebmailError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    mailbox = db.scalar(
        select(Mailbox).where(Mailbox.address == address.lower(), Mailbox.status == MailboxStatus.active)
    )
    if mailbox is None:
        raise HTTPException(status_code=401, detail="Sign in to an active Ithute-hosted mailbox")
    return mailbox, password


def _account(db: Session, mailbox: Mailbox, account_id: UUID) -> ConnectedMailAccount:
    item = db.get(ConnectedMailAccount, account_id)
    if item is None or item.mailbox_id != mailbox.id:
        raise HTTPException(status_code=404, detail="Connected account not found")
    return item


def _account_payload(item: ConnectedMailAccount) -> dict:
    return {
        "id": str(item.id),
        "provider": item.provider,
        "address": item.address,
        "display_name": item.display_name,
        "auth_type": item.auth_type,
        "status": item.status,
        "sync_enabled": item.sync_enabled,
        "imap_host": item.imap_host,
        "imap_port": item.imap_port,
        "imap_security": item.imap_security,
        "smtp_host": item.smtp_host,
        "smtp_port": item.smtp_port,
        "smtp_security": item.smtp_security,
        "last_connected_at": item.last_connected_at.isoformat() if item.last_connected_at else None,
        "last_sync_at": item.last_sync_at.isoformat() if item.last_sync_at else None,
        "last_error": item.last_error,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _failure(exc: Exception, default: int = 503) -> HTTPException:
    text = str(exc)
    lower = text.lower()
    if "not found" in lower:
        default = 404
    elif "reauth" in lower or "authorized again" in lower or "authentication" in lower:
        default = 401
    elif "invalid" in lower or "must" in lower:
        default = 422
    return HTTPException(status_code=default, detail=text)


@router.get("/connected-accounts/capabilities")
def connected_capabilities(
    token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None,
    db: Session = Depends(get_db),
):
    mailbox, _ = _hosted_identity(token, db)
    return {
        "hosted_mailbox": mailbox.address,
        "oauth": provider_capabilities(),
        "features": {
            "persistent_accounts": True,
            "unified_inbox": True,
            "conversation_threads": True,
            "advanced_search": True,
            "snooze": True,
            "migration": True,
        },
    }


@router.get("/connected-accounts")
def list_connected_accounts(
    token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None,
    db: Session = Depends(get_db),
):
    mailbox, _ = _hosted_identity(token, db)
    rows = db.scalars(
        select(ConnectedMailAccount)
        .where(ConnectedMailAccount.mailbox_id == mailbox.id)
        .order_by(ConnectedMailAccount.created_at.asc())
    ).all()
    return {
        "hosted": {"address": mailbox.address, "display_name": mailbox.display_name or "", "type": "hosted"},
        "items": [_account_payload(row) for row in rows],
    }


@router.post("/connected-accounts/from-external-session", status_code=201)
def remember_external_session(
    payload: RememberExternal,
    external_token: Annotated[str | None, Cookie(alias=EXTERNAL_COOKIE)] = None,
    hosted_token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None,
    db: Session = Depends(get_db),
):
    mailbox, _ = _hosted_identity(hosted_token, db)
    try:
        config = external_session_config(external_token or "")
    except ExternalWebmailError as exc:
        raise HTTPException(status_code=401, detail="Connect the external mailbox before saving it") from exc

    try:
        detection = provider_detection_payload(config.address)
        provider = str((detection.get("provider") or {}).get("key") or "custom")
    except ValueError:
        provider = migration_provider_key(config.address, config.imap_host)

    existing = db.scalar(
        select(ConnectedMailAccount).where(
            ConnectedMailAccount.mailbox_id == mailbox.id,
            ConnectedMailAccount.address == config.address.lower(),
        )
    )
    now = datetime.now(timezone.utc)
    item = existing or ConnectedMailAccount(
        tenant_id=mailbox.tenant_id,
        mailbox_id=mailbox.id,
        address=config.address.lower(),
        provider=provider,
        imap_host=config.imap_host,
        imap_port=config.imap_port,
        imap_security=config.imap_security,
        smtp_host=config.smtp_host,
        smtp_port=config.smtp_port,
        smtp_security=config.smtp_security,
    )
    item.display_name = payload.label.strip() or config.display_name
    item.auth_type = "app_password" if provider == "google" else "password"
    item.credential_encrypted = encrypt_secret(config.password)
    item.sync_enabled = payload.sync_enabled
    item.status = "active"
    item.last_connected_at = now
    item.last_error = None
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This mailbox is already connected") from exc
    db.refresh(item)
    return _account_payload(item)


@router.patch("/connected-accounts/{account_id}")
def update_connected_account(
    account_id: UUID,
    payload: AccountUpdate,
    token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None,
    db: Session = Depends(get_db),
):
    mailbox, _ = _hosted_identity(token, db)
    item = _account(db, mailbox, account_id)
    if payload.display_name is not None:
        item.display_name = " ".join(payload.display_name.split())[:255]
    if payload.sync_enabled is not None:
        item.sync_enabled = payload.sync_enabled
    db.commit()
    return _account_payload(item)


@router.delete("/connected-accounts/{account_id}", status_code=204)
def remove_connected_account(
    account_id: UUID,
    token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None,
    db: Session = Depends(get_db),
):
    mailbox, _ = _hosted_identity(token, db)
    item = _account(db, mailbox, account_id)
    db.delete(item)
    db.commit()


@router.post("/connected-accounts/{account_id}/verify")
def verify_connected_account(
    account_id: UUID,
    token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None,
    db: Session = Depends(get_db),
):
    mailbox, _ = _hosted_identity(token, db)
    item = _account(db, mailbox, account_id)
    try:
        config = config_for_account(item, db)
        connected_test(config)
        item.status = "active"
        item.last_connected_at = datetime.now(timezone.utc)
        item.last_error = None
        db.commit()
        return {"ok": True, "account": _account_payload(item)}
    except ConnectedMailError as exc:
        item.status = "error" if item.status != "needs_reauth" else item.status
        item.last_error = str(exc)[:2000]
        db.commit()
        raise _failure(exc) from exc


@router.get("/connected-accounts/oauth/{provider}/start")
def start_connected_oauth(
    provider: str,
    return_to: str = Query(default="/webmail/accounts", max_length=500),
    token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None,
    db: Session = Depends(get_db),
):
    mailbox, _ = _hosted_identity(token, db)
    try:
        return begin_oauth(provider, str(mailbox.id), return_to)
    except MailOAuthError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/connected-accounts/oauth/{provider}/callback")
def connected_oauth_callback(
    provider: str,
    request: Request,
    state: str = Query(default=""),
    code: str = Query(default=""),
    error: str = Query(default=""),
    db: Session = Depends(get_db),
):
    try:
        state_payload = consume_state(state)
        if state_payload.get("provider") != provider_config_key(provider):
            raise MailOAuthError("OAuth provider does not match the original request")
        mailbox = db.get(Mailbox, UUID(str(state_payload["mailbox_id"])))
        if mailbox is None or mailbox.status != MailboxStatus.active:
            raise MailOAuthError("The destination Ithute mailbox is no longer active")
        if error:
            raise MailOAuthError("Authorization was cancelled or rejected by the mail provider")
        result = exchange_code(provider, code)
        existing = db.scalar(
            select(ConnectedMailAccount).where(
                ConnectedMailAccount.mailbox_id == mailbox.id,
                ConnectedMailAccount.address == result["address"],
            )
        )
        item = existing or ConnectedMailAccount(
            tenant_id=mailbox.tenant_id,
            mailbox_id=mailbox.id,
            address=result["address"],
            provider=result["provider"],
            imap_host=result["imap_host"],
            imap_port=result["imap_port"],
            imap_security=result["imap_security"],
            smtp_host=result["smtp_host"],
            smtp_port=result["smtp_port"],
            smtp_security=result["smtp_security"],
        )
        item.provider = result["provider"]
        item.display_name = result["display_name"]
        item.auth_type = "oauth"
        item.credential_encrypted = None
        item.oauth_access_token_encrypted = encrypt_secret(result["access_token"])
        if result["refresh_token"]:
            item.oauth_refresh_token_encrypted = encrypt_secret(result["refresh_token"])
        item.oauth_access_token_expires_at = result["expires_at"]
        item.oauth_scopes_json = result["scope"]
        item.imap_host = result["imap_host"]
        item.imap_port = result["imap_port"]
        item.imap_security = result["imap_security"]
        item.smtp_host = result["smtp_host"]
        item.smtp_port = result["smtp_port"]
        item.smtp_security = result["smtp_security"]
        item.status = "active"
        item.sync_enabled = True
        item.last_connected_at = datetime.now(timezone.utc)
        item.last_error = None
        db.add(item)
        db.commit()
        db.refresh(item)
        return_to = str(state_payload.get("return_to") or "/webmail/accounts")
        separator = "&" if "?" in return_to else "?"
        destination = f"{settings.frontend_url.rstrip('/')}{return_to}{separator}connected={quote(item.address)}"
        return RedirectResponse(destination, status_code=303)
    except (MailOAuthError, ValueError) as exc:
        destination = f"{settings.frontend_url.rstrip('/')}/webmail/accounts?oauth_error={quote(str(exc)[:300])}"
        return RedirectResponse(destination, status_code=303)


def provider_config_key(provider: str) -> str:
    key = provider.strip().lower()
    if key in {"google", "gmail", "google-workspace"}:
        return "google"
    if key in {"microsoft", "microsoft365", "office365", "outlook"}:
        return "microsoft"
    return key


@router.get("/connected-accounts/{account_id}/folders")
def account_folders(
    account_id: UUID,
    token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None,
    db: Session = Depends(get_db),
):
    mailbox, _ = _hosted_identity(token, db)
    item = _account(db, mailbox, account_id)
    try:
        return {"items": connected_folders(config_for_account(item, db))}
    except ConnectedMailError as exc:
        raise _failure(exc) from exc


@router.get("/connected-accounts/{account_id}/folder-counts")
def account_folder_counts(
    account_id: UUID,
    token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None,
    db: Session = Depends(get_db),
):
    mailbox, _ = _hosted_identity(token, db)
    item = _account(db, mailbox, account_id)
    try:
        return {"items": connected_counts(config_for_account(item, db))}
    except ConnectedMailError as exc:
        raise _failure(exc) from exc


@router.get("/connected-accounts/{account_id}/messages")
def account_messages(
    account_id: UUID,
    folder: str = Query(default="INBOX", min_length=1, max_length=255),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100000),
    q: str = Query(default="", max_length=1000),
    token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None,
    db: Session = Depends(get_db),
):
    mailbox, _ = _hosted_identity(token, db)
    item = _account(db, mailbox, account_id)
    try:
        result = connected_messages(config_for_account(item, db), folder, limit, offset, q)
        result["items"] = [annotate_thread(row) for row in result["items"]]
        return result
    except ConnectedMailError as exc:
        raise _failure(exc) from exc


@router.get("/connected-accounts/{account_id}/messages/{uid}")
def account_message(
    account_id: UUID,
    uid: str,
    folder: str = Query(default="INBOX", min_length=1, max_length=255),
    token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None,
    db: Session = Depends(get_db),
):
    mailbox, _ = _hosted_identity(token, db)
    item = _account(db, mailbox, account_id)
    try:
        return annotate_thread(connected_message(config_for_account(item, db), uid, folder))
    except ConnectedMailError as exc:
        raise _failure(exc) from exc


@router.patch("/connected-accounts/{account_id}/messages/{uid}/flags")
def account_message_flags(
    account_id: UUID,
    uid: str,
    payload: MessageFlags,
    folder: str = Query(default="INBOX", min_length=1, max_length=255),
    token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None,
    db: Session = Depends(get_db),
):
    mailbox, _ = _hosted_identity(token, db)
    item = _account(db, mailbox, account_id)
    try:
        return connected_set_flags(
            config_for_account(item, db), uid, folder, seen=payload.seen, flagged=payload.flagged, answered=payload.answered
        )
    except ConnectedMailError as exc:
        raise _failure(exc) from exc


@router.post("/connected-accounts/{account_id}/messages/{uid}/move")
def account_message_move(
    account_id: UUID,
    uid: str,
    payload: MessageMove,
    folder: str = Query(default="INBOX", min_length=1, max_length=255),
    token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None,
    db: Session = Depends(get_db),
):
    mailbox, _ = _hosted_identity(token, db)
    item = _account(db, mailbox, account_id)
    try:
        return connected_move(config_for_account(item, db), uid, folder, payload.destination)
    except ConnectedMailError as exc:
        raise _failure(exc) from exc


@router.delete("/connected-accounts/{account_id}/messages/{uid}")
def account_message_delete(
    account_id: UUID,
    uid: str,
    folder: str = Query(default="INBOX", min_length=1, max_length=255),
    token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None,
    db: Session = Depends(get_db),
):
    mailbox, _ = _hosted_identity(token, db)
    item = _account(db, mailbox, account_id)
    try:
        return connected_delete(config_for_account(item, db), uid, folder)
    except ConnectedMailError as exc:
        raise _failure(exc) from exc


@router.get("/connected-accounts/{account_id}/messages/{uid}/attachments/{index}")
def account_attachment(
    account_id: UUID,
    uid: str,
    index: int,
    folder: str = Query(default="INBOX", min_length=1, max_length=255),
    token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None,
    db: Session = Depends(get_db),
):
    from fastapi.responses import Response as BinaryResponse

    mailbox, _ = _hosted_identity(token, db)
    item = _account(db, mailbox, account_id)
    try:
        filename, content_type, data = connected_attachment(config_for_account(item, db), uid, folder, index)
    except ConnectedMailError as exc:
        raise _failure(exc) from exc
    return BinaryResponse(
        content=data,
        media_type=content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename.replace(chr(34), "_")}"'},
    )


@router.post("/connected-accounts/{account_id}/send")
def account_send(
    account_id: UUID,
    payload: ConnectedSendIn,
    token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None,
    db: Session = Depends(get_db),
):
    mailbox, _ = _hosted_identity(token, db)
    item = _account(db, mailbox, account_id)
    try:
        return connected_send(
            config_for_account(item, db),
            to=[str(x) for x in payload.to],
            cc=[str(x) for x in payload.cc],
            bcc=[str(x) for x in payload.bcc],
            subject=payload.subject,
            body_text=payload.body_text,
            body_html=payload.body_html,
            attachments=[row.model_dump() for row in payload.attachments],
            in_reply_to=payload.in_reply_to,
            references=payload.references,
        )
    except ConnectedMailError as exc:
        raise _failure(exc) from exc


@router.post("/connected-accounts/{account_id}/drafts")
def account_draft(
    account_id: UUID,
    payload: ConnectedDraftIn,
    token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None,
    db: Session = Depends(get_db),
):
    mailbox, _ = _hosted_identity(token, db)
    item = _account(db, mailbox, account_id)
    try:
        return connected_save_draft(
            config_for_account(item, db),
            to=[str(x) for x in payload.to],
            cc=[str(x) for x in payload.cc],
            subject=payload.subject,
            body_text=payload.body_text,
        )
    except ConnectedMailError as exc:
        raise _failure(exc) from exc


@router.get("/unified/inbox")
def unified_inbox(
    q: str = Query(default="", max_length=1000),
    limit: int = Query(default=60, ge=1, le=200),
    token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None,
    db: Session = Depends(get_db),
):
    mailbox, password = _hosted_identity(token, db)
    accounts = db.scalars(
        select(ConnectedMailAccount).where(
            ConnectedMailAccount.mailbox_id == mailbox.id,
            ConnectedMailAccount.sync_enabled.is_(True),
            ConnectedMailAccount.status.in_(["active", "error"]),
        )
    ).all()

    items: list[dict] = []
    errors: list[dict] = []
    try:
        hosted = hosted_messages(mailbox.address, password, folder="INBOX", limit=min(limit, 60), offset=0, query=q)
        for row in hosted.get("items", []):
            items.append(
                annotate_thread(
                    {
                        **row,
                        "source_key": "hosted",
                        "source_type": "hosted",
                        "account_id": None,
                        "account_address": mailbox.address,
                        "account_label": mailbox.display_name or mailbox.address,
                        "provider": "ithute",
                        "folder": "INBOX",
                    }
                )
            )
    except WebmailError as exc:
        errors.append({"source_key": "hosted", "address": mailbox.address, "error": str(exc)})

    configs: list[tuple[ConnectedMailAccount, object]] = []
    for account in accounts[:8]:
        try:
            configs.append((account, config_for_account(account, db)))
        except ConnectedMailError as exc:
            errors.append({"source_key": str(account.id), "address": account.address, "error": str(exc)})

    def load_connected(pair):
        account, config = pair
        result = connected_messages(config, "INBOX", min(30, limit), 0, q)
        return account, result

    if configs:
        with ThreadPoolExecutor(max_workers=min(4, len(configs))) as pool:
            future_map = {pool.submit(load_connected, pair): pair[0] for pair in configs}
            for future in as_completed(future_map):
                account = future_map[future]
                try:
                    _, result = future.result()
                    account.last_sync_at = datetime.now(timezone.utc)
                    account.last_error = None
                    for row in result.get("items", []):
                        items.append(
                            annotate_thread(
                                {
                                    **row,
                                    "source_key": str(account.id),
                                    "source_type": "connected",
                                    "account_id": str(account.id),
                                    "account_address": account.address,
                                    "account_label": account.display_name or account.address,
                                    "provider": account.provider,
                                    "folder": "INBOX",
                                }
                            )
                        )
                except Exception as exc:
                    account.last_error = str(exc)[:2000]
                    errors.append({"source_key": str(account.id), "address": account.address, "error": str(exc)})
        db.commit()

    now = datetime.now(timezone.utc)
    snoozed = {
        (row.source_key, row.folder, row.message_uid)
        for row in db.scalars(
            select(MailSnooze).where(MailSnooze.mailbox_id == mailbox.id, MailSnooze.wake_at > now)
        ).all()
    }
    items = [row for row in items if (str(row["source_key"]), str(row.get("folder") or "INBOX"), str(row["uid"])) not in snoozed]
    items.sort(key=lambda row: message_timestamp(str(row.get("date") or "")), reverse=True)
    return {"items": items[:limit], "errors": errors, "query": q, "sources": 1 + len(accounts)}


@router.post("/snoozes", status_code=201)
def snooze_message(
    payload: SnoozeIn,
    token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None,
    db: Session = Depends(get_db),
):
    mailbox, _ = _hosted_identity(token, db)
    if payload.wake_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="Snooze time must be in the future")
    source_key = payload.source_key
    account_id = payload.connected_account_id
    if account_id:
        item = _account(db, mailbox, account_id)
        source_key = str(item.id)
    elif source_key != "hosted":
        raise HTTPException(status_code=422, detail="Connected snoozes require a valid connected_account_id")
    existing = db.scalar(
        select(MailSnooze).where(
            MailSnooze.mailbox_id == mailbox.id,
            MailSnooze.source_key == source_key,
            MailSnooze.folder == payload.folder,
            MailSnooze.message_uid == payload.message_uid,
        )
    )
    row = existing or MailSnooze(
        mailbox_id=mailbox.id,
        connected_account_id=account_id,
        source_key=source_key,
        folder=payload.folder,
        message_uid=payload.message_uid,
    )
    row.message_id = payload.message_id or None
    row.wake_at = payload.wake_at
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": str(row.id), "wake_at": row.wake_at.isoformat(), "source_key": row.source_key}


@router.get("/snoozes")
def list_snoozes(
    token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None,
    db: Session = Depends(get_db),
):
    mailbox, _ = _hosted_identity(token, db)
    rows = db.scalars(
        select(MailSnooze).where(MailSnooze.mailbox_id == mailbox.id).order_by(MailSnooze.wake_at.asc())
    ).all()
    return {
        "items": [
            {
                "id": str(row.id),
                "source_key": row.source_key,
                "connected_account_id": str(row.connected_account_id) if row.connected_account_id else None,
                "folder": row.folder,
                "message_uid": row.message_uid,
                "message_id": row.message_id,
                "wake_at": row.wake_at.isoformat(),
            }
            for row in rows
        ]
    }


@router.delete("/snoozes/{snooze_id}", status_code=204)
def unsnooze(
    snooze_id: UUID,
    token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None,
    db: Session = Depends(get_db),
):
    mailbox, _ = _hosted_identity(token, db)
    row = db.get(MailSnooze, snooze_id)
    if row is None or row.mailbox_id != mailbox.id:
        raise HTTPException(status_code=404, detail="Snoozed message not found")
    db.delete(row)
    db.commit()
