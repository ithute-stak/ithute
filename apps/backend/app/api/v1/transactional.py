import json
import secrets
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import authenticate_api_key, get_current_user, require_tenant_permission
from app.core.config import settings
from app.db.session import get_db
from app.models import ApiKey, AuditLog, SmtpCredential, TransactionalMessage, User
from app.services.mailboxes import hash_mailbox_password, normalize_destination
from app.services.transactional_mail import send_message

router = APIRouter(tags=["transactional-email"])


class SmtpCredentialCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    sender_address: str | None = Field(default=None, max_length=320)
    daily_limit: int = Field(default=1000, ge=1, le=1000000)


class SendRequest(BaseModel):
    sender: str
    recipients: list[str] = Field(min_length=1, max_length=100)
    subject: str = Field(min_length=1, max_length=500)
    text: str | None = Field(default=None, max_length=1_000_000)
    html: str | None = Field(default=None, max_length=2_000_000)


def _new_smtp_secret() -> str:
    return "Smtp!" + secrets.token_urlsafe(30) + "Aa9"


@router.post("/tenants/{tenant_id}/smtp-credentials", status_code=201)
def create_smtp_credential(tenant_id: UUID, payload: SmtpCredentialCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "mail.manage", db, current)
    sender = None
    if payload.sender_address:
        try:
            sender = normalize_destination(payload.sender_address)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    raw = _new_smtp_secret()
    username = f"smtp_{tenant_id.hex[:12]}_{secrets.token_hex(4)}"
    row = SmtpCredential(
        tenant_id=tenant_id,
        username=username,
        password_hash=hash_mailbox_password(raw),
        name=payload.name,
        sender_address=sender,
        system_managed=False,
        daily_limit=payload.daily_limit,
        active=True,
        created_by_user_id=current.id,
    )
    db.add(row)
    db.flush()
    db.add(AuditLog(tenant_id=tenant_id, actor_user_id=current.id, action="smtp_credential.create", resource_type="smtp_credential", resource_id=str(row.id)))
    db.commit()
    return {
        "id": str(row.id),
        "username": row.username,
        "password": raw,
        "name": row.name,
        "sender_address": row.sender_address,
        "daily_limit": row.daily_limit,
        "smtp_host": settings.mail_hostname,
        "smtp_port": 587,
        "tls": "STARTTLS",
        "note": "The password is returned once and is not stored in recoverable form.",
    }


@router.get("/tenants/{tenant_id}/smtp-credentials")
def list_smtp_credentials(tenant_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "mail.read", db, current)
    rows = db.scalars(select(SmtpCredential).where(SmtpCredential.tenant_id == tenant_id, SmtpCredential.system_managed.is_(False)).order_by(SmtpCredential.created_at.desc())).all()
    return {"items": [{"id": str(x.id), "username": x.username, "name": x.name, "sender_address": x.sender_address, "daily_limit": x.daily_limit, "active": x.active, "last_used_at": x.last_used_at.isoformat() if x.last_used_at else None, "created_at": x.created_at.isoformat()} for x in rows]}


@router.delete("/tenants/{tenant_id}/smtp-credentials/{credential_id}", status_code=204)
def revoke_smtp_credential(tenant_id: UUID, credential_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "mail.manage", db, current)
    row = db.scalar(select(SmtpCredential).where(SmtpCredential.id == credential_id, SmtpCredential.tenant_id == tenant_id, SmtpCredential.system_managed.is_(False)))
    if row is None:
        raise HTTPException(status_code=404, detail="SMTP credential not found")
    row.active = False
    db.add(AuditLog(tenant_id=tenant_id, actor_user_id=current.id, action="smtp_credential.revoke", resource_type="smtp_credential", resource_id=str(row.id)))
    db.commit()


def _api_key_from_request(request: Request, db: Session) -> ApiKey:
    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Bearer API key required")
    key = authenticate_api_key(authorization.split(" ", 1)[1].strip(), db)
    if key.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant-scoped API key required")
    try:
        scopes = set(json.loads(key.scopes or "[]"))
    except json.JSONDecodeError:
        scopes = set()
    if "mail.send" not in scopes and "*" not in scopes:
        raise HTTPException(status_code=403, detail="API key requires mail.send scope")
    return key


@router.post("/transactional/v1/send", status_code=202)
def transactional_send(payload: SendRequest, request: Request, db: Session = Depends(get_db)):
    key = _api_key_from_request(request, db)
    tenant_id = key.tenant_id
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    sent_today = db.scalar(select(func.count(TransactionalMessage.id)).where(TransactionalMessage.tenant_id == tenant_id, TransactionalMessage.created_at >= start, TransactionalMessage.status != "failed")) or 0
    if int(sent_today) >= settings.transactional_tenant_daily_limit:
        raise HTTPException(status_code=429, detail="Transactional daily sending limit reached")
    try:
        row = send_message(
            db,
            tenant_id=tenant_id,
            api_key_id=key.id,
            sender=payload.sender,
            recipients=payload.recipients,
            subject=payload.subject,
            text_body=payload.text,
            html_body=payload.html,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        db.commit()
        raise HTTPException(status_code=502, detail=f"SMTP submission failed: {exc}") from exc
    db.commit()
    return {"id": str(row.id), "message_id": row.message_id, "status": row.status}


@router.get("/tenants/{tenant_id}/transactional/messages")
def list_transactional_messages(tenant_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "mail.read", db, current)
    rows = db.scalars(select(TransactionalMessage).where(TransactionalMessage.tenant_id == tenant_id).order_by(TransactionalMessage.created_at.desc()).limit(500)).all()
    return {"items": [{"id": str(x.id), "message_id": x.message_id, "sender": x.sender, "recipients": json.loads(x.recipients_json), "subject": x.subject, "status": x.status, "error": x.error, "created_at": x.created_at.isoformat()} for x in rows]}
