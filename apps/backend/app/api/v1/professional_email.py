import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_tenant_permission
from app.core.config import settings
from app.db.session import get_db
from app.models import (
    AuditLog,
    Domain,
    MailMigrationJob,
    Mailbox,
    MailboxDelegate,
    MailboxPolicy,
    MailboxRecoveryJob,
    MailboxStatus,
    ReputationSnapshot,
    User,
)
from app.services.backup_recovery import RecoveryServiceError, recover_mailbox
from app.services.mail_migration import migrate_imap_mailbox, provider_endpoint
from app.services.mailboxes import normalize_destination
from app.services.reputation import reputation_check

router = APIRouter(prefix="/tenants/{tenant_id}/professional-email", tags=["professional-email"])


class DelegateCreate(BaseModel):
    delegate_address: str
    permissions: list[str] = Field(default_factory=lambda: ["lookup", "read", "write", "insert", "post"])


class PolicyUpdate(BaseModel):
    vacation_enabled: bool = False
    vacation_subject: str | None = Field(default=None, max_length=240)
    vacation_body: str | None = Field(default=None, max_length=10000)
    sieve_script: str | None = Field(default=None, max_length=50000)


class MigrationRun(BaseModel):
    mailbox_id: UUID
    source_provider: str = Field(pattern=r"^(google|microsoft365|office365|cpanel|imap)$")
    source_username: str = Field(min_length=1, max_length=320)
    source_password: str | None = Field(default=None, max_length=1024)
    oauth2_token: str | None = Field(default=None, max_length=8192)
    source_host: str | None = Field(default=None, max_length=253)
    source_port: int | None = Field(default=None, ge=1, le=65535)


class BulkMigrationRun(BaseModel):
    items: list[MigrationRun] = Field(min_length=1, max_length=100)


class RecoveryRequest(BaseModel):
    snapshot_id: str | None = Field(default=None, max_length=128)


_PERMISSION_MAP = {
    "lookup": "l",
    "read": "r",
    "write": "w",
    "insert": "i",
    "post": "p",
    "expunge": "e",
    "create": "k",
    "delete": "x",
}


def _mailbox(db: Session, tenant_id: UUID, mailbox_id: UUID) -> Mailbox:
    row = db.scalar(select(Mailbox).where(Mailbox.id == mailbox_id, Mailbox.tenant_id == tenant_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Mailbox not found")
    return row


def _mailbox_home(address: str) -> Path:
    local, domain = address.lower().split("@", 1)
    return Path(settings.mail_data_path) / domain / local


def _sync_acl(db: Session, mailbox: Mailbox) -> None:
    home = _mailbox_home(mailbox.address)
    maildir = home / "Maildir"
    maildir.mkdir(parents=True, exist_ok=True)
    os.chown(home, 5000, 5000)
    os.chown(maildir, 5000, 5000)
    delegates = db.scalars(select(MailboxDelegate).where(MailboxDelegate.mailbox_id == mailbox.id).order_by(MailboxDelegate.delegate_address)).all()
    lines = []
    for delegate in delegates:
        rights = "".join(_PERMISSION_MAP[p] for p in delegate.permissions.split(",") if p in _PERMISSION_MAP)
        lines.append(f"user={delegate.delegate_address} {rights or 'lr'}")
    path = maildir / "dovecot-acl"
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    os.chown(path, 5000, 5000)


def _sieve_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _sync_policy(mailbox: Mailbox, policy: MailboxPolicy) -> None:
    home = _mailbox_home(mailbox.address)
    home.mkdir(parents=True, exist_ok=True)
    os.chown(home, 5000, 5000)
    parts: list[str] = []
    if policy.vacation_enabled:
        subject = _sieve_escape(policy.vacation_subject or "Out of office")
        body = (policy.vacation_body or "I am currently away from email.").replace("\r", "")
        body = "\n".join(line if line != "." else ".." for line in body.split("\n"))
        parts.append('require ["vacation"];')
        parts.append(f'vacation :days 1 :subject "{subject}" text:\n{body}\n.\n;')
    if policy.sieve_script:
        parts.append(policy.sieve_script.strip())
    sieve_path = home / ".dovecot.sieve"
    sieve_path.write_text("\n\n".join(parts) + ("\n" if parts else ""), encoding="utf-8")
    os.chown(sieve_path, 5000, 5000)


@router.get("/mailboxes/{mailbox_id}/delegates")
def list_delegates(tenant_id: UUID, mailbox_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "mail.read", db, current)
    _mailbox(db, tenant_id, mailbox_id)
    rows = db.scalars(select(MailboxDelegate).where(MailboxDelegate.mailbox_id == mailbox_id).order_by(MailboxDelegate.delegate_address)).all()
    return {"items": [{"id": str(x.id), "delegate_address": x.delegate_address, "permissions": x.permissions.split(","), "created_at": x.created_at.isoformat()} for x in rows]}


@router.post("/mailboxes/{mailbox_id}/delegates", status_code=201)
def add_delegate(tenant_id: UUID, mailbox_id: UUID, payload: DelegateCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "mail.manage", db, current)
    mailbox = _mailbox(db, tenant_id, mailbox_id)
    if mailbox.status != MailboxStatus.active:
        raise HTTPException(status_code=409, detail="Mailbox must be active")
    try:
        delegate_address = normalize_destination(payload.delegate_address)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if delegate_address == mailbox.address:
        raise HTTPException(status_code=422, detail="Mailbox cannot delegate to itself")
    delegate_mailbox = db.scalar(select(Mailbox).where(Mailbox.tenant_id == tenant_id, Mailbox.address == delegate_address, Mailbox.status == MailboxStatus.active))
    if delegate_mailbox is None:
        raise HTTPException(status_code=409, detail="Delegate must be an active mailbox in this tenant")
    permissions = [p for p in dict.fromkeys(payload.permissions) if p in _PERMISSION_MAP]
    if not permissions:
        raise HTTPException(status_code=422, detail="At least one valid permission is required")
    existing = db.scalar(select(MailboxDelegate).where(MailboxDelegate.mailbox_id == mailbox_id, MailboxDelegate.delegate_address == delegate_address))
    if existing:
        existing.permissions = ",".join(permissions)
        row = existing
    else:
        row = MailboxDelegate(
            tenant_id=tenant_id,
            mailbox_id=mailbox_id,
            delegate_address=delegate_address,
            permissions=",".join(permissions),
            created_by_user_id=current.id,
        )
        db.add(row)
    db.flush()
    _sync_acl(db, mailbox)
    db.add(AuditLog(tenant_id=tenant_id, actor_user_id=current.id, action="mailbox.delegate.upsert", resource_type="mailbox", resource_id=str(mailbox_id), metadata_json=json.dumps({"delegate": delegate_address})))
    db.commit()
    return {"id": str(row.id), "delegate_address": row.delegate_address, "permissions": row.permissions.split(",")}


@router.delete("/mailboxes/{mailbox_id}/delegates/{delegate_id}", status_code=204)
def delete_delegate(tenant_id: UUID, mailbox_id: UUID, delegate_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "mail.manage", db, current)
    mailbox = _mailbox(db, tenant_id, mailbox_id)
    row = db.scalar(select(MailboxDelegate).where(MailboxDelegate.id == delegate_id, MailboxDelegate.mailbox_id == mailbox_id, MailboxDelegate.tenant_id == tenant_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Delegate not found")
    db.delete(row)
    db.flush()
    _sync_acl(db, mailbox)
    db.add(AuditLog(tenant_id=tenant_id, actor_user_id=current.id, action="mailbox.delegate.delete", resource_type="mailbox", resource_id=str(mailbox_id)))
    db.commit()


@router.get("/mailboxes/{mailbox_id}/policy")
def get_policy(tenant_id: UUID, mailbox_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "mail.read", db, current)
    _mailbox(db, tenant_id, mailbox_id)
    row = db.scalar(select(MailboxPolicy).where(MailboxPolicy.mailbox_id == mailbox_id))
    if row is None:
        return {"vacation_enabled": False, "vacation_subject": None, "vacation_body": None, "sieve_script": None}
    return {"vacation_enabled": row.vacation_enabled, "vacation_subject": row.vacation_subject, "vacation_body": row.vacation_body, "sieve_script": row.sieve_script, "updated_at": row.updated_at.isoformat()}


@router.put("/mailboxes/{mailbox_id}/policy")
def update_policy(tenant_id: UUID, mailbox_id: UUID, payload: PolicyUpdate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "mail.manage", db, current)
    mailbox = _mailbox(db, tenant_id, mailbox_id)
    row = db.scalar(select(MailboxPolicy).where(MailboxPolicy.mailbox_id == mailbox_id))
    if row is None:
        row = MailboxPolicy(tenant_id=tenant_id, mailbox_id=mailbox_id, updated_by_user_id=current.id)
        db.add(row)
    row.vacation_enabled = payload.vacation_enabled
    row.vacation_subject = payload.vacation_subject
    row.vacation_body = payload.vacation_body
    row.sieve_script = payload.sieve_script
    row.updated_by_user_id = current.id
    db.flush()
    _sync_policy(mailbox, row)
    db.add(AuditLog(tenant_id=tenant_id, actor_user_id=current.id, action="mailbox.policy.update", resource_type="mailbox", resource_id=str(mailbox_id)))
    db.commit()
    return {"saved": True, "mailbox": mailbox.address}


def _run_migration(db: Session, tenant_id: UUID, current: User, payload: MigrationRun) -> dict:
    mailbox = _mailbox(db, tenant_id, payload.mailbox_id)
    if mailbox.status != MailboxStatus.active:
        raise HTTPException(status_code=409, detail=f"{mailbox.address} must be active before migration")
    try:
        host, port = provider_endpoint(payload.source_provider, payload.source_host, payload.source_port)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    job = MailMigrationJob(
        tenant_id=tenant_id,
        mailbox_id=mailbox.id,
        source_provider=payload.source_provider,
        source_host=host,
        source_port=port,
        source_username=payload.source_username,
        status="running",
        started_at=datetime.now(timezone.utc),
        created_by_user_id=current.id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        result = migrate_imap_mailbox(
            destination_address=mailbox.address,
            source_provider=payload.source_provider,
            source_username=payload.source_username,
            source_password=payload.source_password,
            oauth2_token=payload.oauth2_token,
            source_host=host,
            source_port=port,
        )
        job.status = "completed"
        job.folders_total = result["folders_total"]
        job.folders_done = result["folders_done"]
        job.messages_copied = result["messages_copied"]
        job.bytes_copied = result["bytes_copied"]
        job.completed_at = datetime.now(timezone.utc)
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)[:10000]
        job.completed_at = datetime.now(timezone.utc)
    db.add(AuditLog(tenant_id=tenant_id, actor_user_id=current.id, action="mailbox.migration.run", resource_type="mail_migration_job", resource_id=str(job.id), metadata_json=json.dumps({"status": job.status, "mailbox": mailbox.address})))
    db.commit()
    return {"id": str(job.id), "mailbox": mailbox.address, "status": job.status, "folders_total": job.folders_total, "folders_done": job.folders_done, "messages_copied": job.messages_copied, "bytes_copied": job.bytes_copied, "error": job.error}


@router.post("/migrations/run")
def run_migration(tenant_id: UUID, payload: MigrationRun, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "mail.manage", db, current)
    return _run_migration(db, tenant_id, current, payload)


@router.post("/migrations/bulk/run")
def run_bulk_migration(tenant_id: UUID, payload: BulkMigrationRun, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "mail.manage", db, current)
    return {"items": [_run_migration(db, tenant_id, current, item) for item in payload.items]}


@router.get("/migrations")
def list_migrations(tenant_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "mail.read", db, current)
    rows = db.scalars(select(MailMigrationJob).where(MailMigrationJob.tenant_id == tenant_id).order_by(MailMigrationJob.created_at.desc()).limit(200)).all()
    return {"items": [{"id": str(x.id), "mailbox_id": str(x.mailbox_id), "source_provider": x.source_provider, "source_host": x.source_host, "source_username": x.source_username, "status": x.status, "folders_total": x.folders_total, "folders_done": x.folders_done, "messages_copied": x.messages_copied, "bytes_copied": x.bytes_copied, "error": x.error, "created_at": x.created_at.isoformat()} for x in rows]}


@router.post("/mailboxes/{mailbox_id}/recover")
def recover(tenant_id: UUID, mailbox_id: UUID, payload: RecoveryRequest, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "mail.manage", db, current)
    mailbox = _mailbox(db, tenant_id, mailbox_id)
    job = MailboxRecoveryJob(tenant_id=tenant_id, mailbox_id=mailbox.id, snapshot_id=payload.snapshot_id, status="running", requested_by_user_id=current.id)
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        result = recover_mailbox(mailbox.address, payload.snapshot_id)
        job.status = "completed"
        job.restored_files = int(result.get("restored_files", 0))
        job.completed_at = datetime.now(timezone.utc)
    except RecoveryServiceError as exc:
        job.status = "failed"
        job.error = str(exc)
        job.completed_at = datetime.now(timezone.utc)
    db.add(AuditLog(tenant_id=tenant_id, actor_user_id=current.id, action="mailbox.recovery.run", resource_type="mailbox_recovery_job", resource_id=str(job.id), metadata_json=json.dumps({"mailbox": mailbox.address, "status": job.status})))
    db.commit()
    if job.status == "failed":
        raise HTTPException(status_code=502, detail=job.error or "Mailbox recovery failed")
    return {"id": str(job.id), "status": job.status, "restored_files": job.restored_files}


@router.get("/recovery-jobs")
def list_recovery_jobs(tenant_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "mail.read", db, current)
    rows = db.scalars(select(MailboxRecoveryJob).where(MailboxRecoveryJob.tenant_id == tenant_id).order_by(MailboxRecoveryJob.created_at.desc()).limit(100)).all()
    return {"items": [{"id": str(x.id), "mailbox_id": str(x.mailbox_id), "snapshot_id": x.snapshot_id, "status": x.status, "restored_files": x.restored_files, "error": x.error, "created_at": x.created_at.isoformat()} for x in rows]}


@router.post("/domains/{domain_id}/reputation-scan")
def reputation_scan(tenant_id: UUID, domain_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "mail.read", db, current)
    domain = db.scalar(select(Domain).where(Domain.id == domain_id, Domain.tenant_id == tenant_id))
    if domain is None:
        raise HTTPException(status_code=404, detail="Domain not found")
    if not settings.mail_public_ip:
        raise HTTPException(status_code=409, detail="MAIL_PUBLIC_IP is not configured")
    result = reputation_check(settings.mail_public_ip, settings.mail_hostname)
    row = ReputationSnapshot(
        tenant_id=tenant_id,
        domain_id=domain.id,
        mail_ip=settings.mail_public_ip,
        ptr_ok=result["ptr_ok"],
        fcrdns_ok=result["fcrdns_ok"],
        dnsbl_hits_json=json.dumps(result["dnsbl_hits"]),
        score=result["score"],
    )
    db.add(row)
    db.commit()
    return {"id": str(row.id), "domain": domain.ascii_name, **result}


@router.get("/reputation")
def reputation_history(tenant_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "mail.read", db, current)
    rows = db.scalars(select(ReputationSnapshot).where(ReputationSnapshot.tenant_id == tenant_id).order_by(ReputationSnapshot.created_at.desc()).limit(100)).all()
    return {"items": [{"id": str(x.id), "domain_id": str(x.domain_id) if x.domain_id else None, "mail_ip": x.mail_ip, "ptr_ok": x.ptr_ok, "fcrdns_ok": x.fcrdns_ok, "dnsbl_hits": json.loads(x.dnsbl_hits_json or "[]"), "score": x.score, "created_at": x.created_at.isoformat()} for x in rows]}
