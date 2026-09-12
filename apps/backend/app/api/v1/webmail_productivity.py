from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import encrypt_secret, hash_token
from app.db.session import get_db
from app.models import ConnectedMailAccount, Mailbox, MailboxRule, MailboxStatus, ScheduledMail
from app.services.connected_mail import (
    ConnectedMailError,
    config_for_account,
    messages as connected_messages,
    move_message as connected_move,
    set_flags as connected_flags,
)
from app.services.scheduled_mail import start_scheduled_mail_worker
from app.services.webmail import (
    WebmailError,
    _redis as webmail_redis,
    messages as hosted_messages,
    move_message as hosted_move,
    session_credentials,
    set_flags as hosted_flags,
)


router = APIRouter(prefix="/webmail", tags=["webmail-productivity"])
HOSTED_COOKIE = settings.webmail_session_cookie_name
RULE_ACTIONS = {"mark_read", "mark_unread", "star", "unstar", "move_to"}


class RuleIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    enabled: bool = True
    connected_account_id: UUID | None = None
    conditions: dict[str, Any] = Field(default_factory=dict)
    actions: list[dict[str, Any]] = Field(min_length=1, max_length=20)


class RulePatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    enabled: bool | None = None
    conditions: dict[str, Any] | None = None
    actions: list[dict[str, Any]] | None = Field(default=None, min_length=1, max_length=20)


class ScheduledAttachment(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(default="application/octet-stream", min_length=1, max_length=255)
    content_b64: str = Field(min_length=1, max_length=25_000_000)


class ScheduleIn(BaseModel):
    connected_account_id: UUID | None = None
    to: list[EmailStr] = Field(min_length=1, max_length=100)
    cc: list[EmailStr] = Field(default_factory=list, max_length=100)
    bcc: list[EmailStr] = Field(default_factory=list, max_length=100)
    subject: str = Field(default="", max_length=998)
    body_text: str = Field(default="", max_length=2_000_000)
    body_html: str = Field(default="", max_length=2_000_000)
    attachments: list[ScheduledAttachment] = Field(default_factory=list, max_length=20)
    scheduled_at: datetime


def _owner(token: str | None, db: Session) -> tuple[Mailbox, str]:
    try:
        address, password = session_credentials(token or "")
    except WebmailError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    mailbox = db.scalar(select(Mailbox).where(Mailbox.address == address.lower(), Mailbox.status == MailboxStatus.active))
    if mailbox is None:
        raise HTTPException(status_code=401, detail="Sign in to an active Ithute-hosted mailbox")
    return mailbox, password


def _owned_account(db: Session, mailbox: Mailbox, account_id: UUID) -> ConnectedMailAccount:
    account = db.get(ConnectedMailAccount, account_id)
    if account is None or account.mailbox_id != mailbox.id:
        raise HTTPException(status_code=404, detail="Connected account not found")
    return account


def _validate_conditions(value: dict[str, Any]) -> dict[str, Any]:
    allowed = {"from_contains", "to_contains", "subject_contains", "has_attachment", "unread"}
    clean = {key: item for key, item in value.items() if key in allowed}
    for key in ("from_contains", "to_contains", "subject_contains"):
        if key in clean:
            clean[key] = str(clean[key]).strip()[:320]
            if not clean[key]:
                clean.pop(key, None)
    for key in ("has_attachment", "unread"):
        if key in clean:
            clean[key] = bool(clean[key])
    if not clean:
        raise HTTPException(status_code=422, detail="Add at least one supported rule condition")
    return clean


def _validate_actions(value: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw in value:
        action = str(raw.get("type") or "").strip().lower()
        if action not in RULE_ACTIONS:
            raise HTTPException(status_code=422, detail=f"Unsupported mail rule action: {action or 'missing'}")
        item: dict[str, Any] = {"type": action}
        if action == "move_to":
            folder = str(raw.get("folder") or "").strip()[:255]
            if not folder:
                raise HTTPException(status_code=422, detail="move_to rules require a destination folder")
            item["folder"] = folder
        result.append(item)
    if not result:
        raise HTTPException(status_code=422, detail="Add at least one rule action")
    return result


def _rule_payload(rule: MailboxRule) -> dict:
    return {
        "id": str(rule.id),
        "name": rule.name,
        "enabled": rule.enabled,
        "connected_account_id": str(rule.connected_account_id) if rule.connected_account_id else None,
        "conditions": rule.conditions_json,
        "actions": rule.actions_json,
        "run_count": rule.run_count,
        "last_run_at": rule.last_run_at.isoformat() if rule.last_run_at else None,
        "last_error": rule.last_error,
    }


def _matches(row: dict, conditions: dict[str, Any]) -> bool:
    if "from_contains" in conditions and conditions["from_contains"].lower() not in str(row.get("from") or "").lower():
        return False
    if "to_contains" in conditions and conditions["to_contains"].lower() not in str(row.get("to") or "").lower():
        return False
    if "subject_contains" in conditions and conditions["subject_contains"].lower() not in str(row.get("subject") or "").lower():
        return False
    if "has_attachment" in conditions and bool(row.get("attachments")) != bool(conditions["has_attachment"]):
        return False
    if "unread" in conditions and (not bool(row.get("seen"))) != bool(conditions["unread"]):
        return False
    return True


def _processed_key(rule: MailboxRule, row: dict) -> str:
    identity = str(row.get("message_id") or row.get("uid") or "")
    return f"webmail:rule-applied:{rule.id}:{hash_token(identity)}"


def _apply_actions_hosted(mailbox: Mailbox, password: str, row: dict, actions: list[dict]) -> None:
    uid = str(row["uid"])
    folder = "INBOX"
    for action in actions:
        kind = action["type"]
        if kind == "mark_read":
            hosted_flags(mailbox.address, password, uid, folder, seen=True)
        elif kind == "mark_unread":
            hosted_flags(mailbox.address, password, uid, folder, seen=False)
        elif kind == "star":
            hosted_flags(mailbox.address, password, uid, folder, flagged=True)
        elif kind == "unstar":
            hosted_flags(mailbox.address, password, uid, folder, flagged=False)
        elif kind == "move_to":
            hosted_move(mailbox.address, password, uid, folder, str(action["folder"]))
            break


def _apply_actions_connected(account: ConnectedMailAccount, db: Session, row: dict, actions: list[dict]) -> None:
    config = config_for_account(account, db)
    uid = str(row["uid"])
    folder = "INBOX"
    for action in actions:
        kind = action["type"]
        if kind == "mark_read":
            connected_flags(config, uid, folder, seen=True)
        elif kind == "mark_unread":
            connected_flags(config, uid, folder, seen=False)
        elif kind == "star":
            connected_flags(config, uid, folder, flagged=True)
        elif kind == "unstar":
            connected_flags(config, uid, folder, flagged=False)
        elif kind == "move_to":
            connected_move(config, uid, folder, str(action["folder"]))
            break


@router.get("/rules")
def list_rules(token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None, db: Session = Depends(get_db)):
    mailbox, _ = _owner(token, db)
    rows = db.scalars(select(MailboxRule).where(MailboxRule.mailbox_id == mailbox.id).order_by(MailboxRule.name)).all()
    return {"items": [_rule_payload(row) for row in rows]}


@router.post("/rules", status_code=201)
def create_rule(payload: RuleIn, token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None, db: Session = Depends(get_db)):
    mailbox, _ = _owner(token, db)
    if payload.connected_account_id:
        _owned_account(db, mailbox, payload.connected_account_id)
    rule = MailboxRule(
        mailbox_id=mailbox.id,
        connected_account_id=payload.connected_account_id,
        name=" ".join(payload.name.split()),
        enabled=payload.enabled,
        conditions_json=_validate_conditions(payload.conditions),
        actions_json=_validate_actions(payload.actions),
    )
    db.add(rule)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A rule with this name already exists") from exc
    db.refresh(rule)
    return _rule_payload(rule)


@router.patch("/rules/{rule_id}")
def update_rule(rule_id: UUID, payload: RulePatch, token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None, db: Session = Depends(get_db)):
    mailbox, _ = _owner(token, db)
    rule = db.get(MailboxRule, rule_id)
    if rule is None or rule.mailbox_id != mailbox.id:
        raise HTTPException(status_code=404, detail="Mail rule not found")
    if payload.name is not None:
        rule.name = " ".join(payload.name.split())
    if payload.enabled is not None:
        rule.enabled = payload.enabled
    if payload.conditions is not None:
        rule.conditions_json = _validate_conditions(payload.conditions)
    if payload.actions is not None:
        rule.actions_json = _validate_actions(payload.actions)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A rule with this name already exists") from exc
    return _rule_payload(rule)


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: UUID, token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None, db: Session = Depends(get_db)):
    mailbox, _ = _owner(token, db)
    rule = db.get(MailboxRule, rule_id)
    if rule is None or rule.mailbox_id != mailbox.id:
        raise HTTPException(status_code=404, detail="Mail rule not found")
    db.delete(rule)
    db.commit()


@router.post("/rules/run")
def run_rules(token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None, db: Session = Depends(get_db)):
    mailbox, password = _owner(token, db)
    rules = db.scalars(
        select(MailboxRule).where(MailboxRule.mailbox_id == mailbox.id, MailboxRule.enabled.is_(True)).order_by(MailboxRule.created_at)
    ).all()
    applied = 0
    checked = 0
    store = webmail_redis()
    for rule in rules:
        try:
            if rule.connected_account_id:
                account = _owned_account(db, mailbox, rule.connected_account_id)
                rows = connected_messages(config_for_account(account, db), "INBOX", 100, 0, "").get("items", [])
            else:
                rows = hosted_messages(mailbox.address, password, "INBOX", 100, 0, "").get("items", [])
            for row in rows:
                checked += 1
                if not _matches(row, dict(rule.conditions_json or {})):
                    continue
                key = _processed_key(rule, row)
                if store.get(key):
                    continue
                if rule.connected_account_id:
                    _apply_actions_connected(account, db, row, list(rule.actions_json or []))
                else:
                    _apply_actions_hosted(mailbox, password, row, list(rule.actions_json or []))
                store.setex(key, 30 * 86400, "1")
                applied += 1
                rule.run_count += 1
            rule.last_run_at = datetime.now(timezone.utc)
            rule.last_error = None
        except (WebmailError, ConnectedMailError, Exception) as exc:
            rule.last_error = str(exc)[:2000]
        db.commit()
    return {"rules": len(rules), "messages_checked": checked, "actions_applied": applied}


def _scheduled_payload(row: ScheduledMail) -> dict:
    return {
        "id": str(row.id),
        "connected_account_id": str(row.connected_account_id) if row.connected_account_id else None,
        "source_key": row.source_key,
        "to": row.to_json,
        "cc": row.cc_json,
        "bcc": row.bcc_json,
        "subject": row.subject,
        "scheduled_at": row.scheduled_at.isoformat(),
        "status": row.status,
        "error": row.error,
        "sent_at": row.sent_at.isoformat() if row.sent_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/scheduled")
def list_scheduled(token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None, db: Session = Depends(get_db)):
    mailbox, _ = _owner(token, db)
    rows = db.scalars(select(ScheduledMail).where(ScheduledMail.mailbox_id == mailbox.id).order_by(ScheduledMail.scheduled_at.desc()).limit(100)).all()
    return {"items": [_scheduled_payload(row) for row in rows]}


@router.post("/scheduled", status_code=201)
def schedule_message(payload: ScheduleIn, token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None, db: Session = Depends(get_db)):
    mailbox, password = _owner(token, db)
    now = datetime.now(timezone.utc)
    scheduled_at = payload.scheduled_at
    if scheduled_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="scheduled_at must include a timezone")
    if scheduled_at <= now + timedelta(seconds=15):
        raise HTTPException(status_code=422, detail="Schedule mail at least 15 seconds in the future")
    if scheduled_at > now + timedelta(days=365):
        raise HTTPException(status_code=422, detail="Scheduled mail cannot be more than one year in the future")

    account = None
    if payload.connected_account_id:
        account = _owned_account(db, mailbox, payload.connected_account_id)
        if account.status not in {"active", "error"}:
            raise HTTPException(status_code=409, detail="Connected account needs attention before scheduling mail")

    attachments = [item.model_dump() for item in payload.attachments]
    total_b64 = sum(len(item.get("content_b64") or "") for item in attachments)
    if total_b64 > 22_000_000:
        raise HTTPException(status_code=413, detail="Scheduled attachments are too large")

    row = ScheduledMail(
        mailbox_id=mailbox.id,
        connected_account_id=account.id if account else None,
        source_key=str(account.id) if account else "hosted",
        to_json=[str(item) for item in payload.to],
        cc_json=[str(item) for item in payload.cc],
        bcc_json=[str(item) for item in payload.bcc],
        subject=payload.subject,
        body_text=payload.body_text,
        body_html=payload.body_html,
        attachments_json=attachments,
        auth_secret_encrypted=None if account else encrypt_secret(password),
        scheduled_at=scheduled_at,
        status="queued",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    start_scheduled_mail_worker()
    return _scheduled_payload(row)


@router.post("/scheduled/{job_id}/cancel")
def cancel_scheduled(job_id: UUID, token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None, db: Session = Depends(get_db)):
    mailbox, _ = _owner(token, db)
    row = db.get(ScheduledMail, job_id)
    if row is None or row.mailbox_id != mailbox.id:
        raise HTTPException(status_code=404, detail="Scheduled message not found")
    if row.status not in {"queued", "failed"}:
        raise HTTPException(status_code=409, detail="This scheduled message can no longer be cancelled")
    row.status = "cancelled"
    row.auth_secret_encrypted = None
    db.commit()
    return _scheduled_payload(row)


@router.post("/scheduled/{job_id}/retry")
def retry_scheduled(job_id: UUID, token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None, db: Session = Depends(get_db)):
    mailbox, password = _owner(token, db)
    row = db.get(ScheduledMail, job_id)
    if row is None or row.mailbox_id != mailbox.id:
        raise HTTPException(status_code=404, detail="Scheduled message not found")
    if row.status != "failed":
        raise HTTPException(status_code=409, detail="Only failed scheduled messages can be retried")
    row.status = "queued"
    row.error = None
    row.scheduled_at = datetime.now(timezone.utc) + timedelta(seconds=20)
    if row.connected_account_id is None:
        row.auth_secret_encrypted = encrypt_secret(password)
    db.commit()
    start_scheduled_mail_worker()
    return _scheduled_payload(row)


# Start the lightweight scheduler when this router is imported. Multiple API
# replicas are safe: database row locks ensure only one process claims a due
# message, and stale claims are recovered after 15 minutes.
start_scheduled_mail_worker()
