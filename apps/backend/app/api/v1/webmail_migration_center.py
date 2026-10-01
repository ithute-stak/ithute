from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal, get_db
from app.models import ConnectedMailAccount, MailMigrationJob, Mailbox, MailboxStatus
from app.services.connected_mail import ConnectedMailError, config_for_account
from app.services.mail_migration import migrate_imap_mailbox
from app.services.webmail import WebmailError, session_credentials

router = APIRouter(prefix="/webmail/migrations", tags=["webmail-migration-center"])
HOSTED_COOKIE = settings.webmail_session_cookie_name
MigrationPhase = Literal["initial", "delta", "final"]


def _owner(token: str | None, db: Session) -> Mailbox:
    try:
        address, _ = session_credentials(token or "")
    except WebmailError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    mailbox = db.scalar(select(Mailbox).where(Mailbox.address == address.lower(), Mailbox.status == MailboxStatus.active))
    if mailbox is None:
        raise HTTPException(status_code=401, detail="Sign in to an active Ithute-hosted mailbox")
    return mailbox


def _account(db: Session, mailbox: Mailbox, account_id: UUID) -> ConnectedMailAccount:
    row = db.get(ConnectedMailAccount, account_id)
    if row is None or row.mailbox_id != mailbox.id:
        raise HTTPException(status_code=404, detail="Connected source account not found")
    return row


def _status_parts(value: str) -> tuple[str, str]:
    raw = (value or "queued").strip().lower()
    for phase in ("initial", "delta", "final"):
        suffix = f"_{phase}"
        if raw.endswith(suffix):
            return raw[: -len(suffix)], phase
    return raw, "initial"


def _payload(row: MailMigrationJob, mailbox: Mailbox) -> dict:
    provider = row.source_provider
    account_id = None
    if provider.startswith("connected:"):
        _, account_id, provider = (provider.split(":", 2) + [""])[:3]
    state, phase = _status_parts(row.status)
    return {
        "id": str(row.id),
        "destination": mailbox.address,
        "connected_account_id": account_id,
        "source_provider": provider or "external",
        "source_username": row.source_username,
        "status": state,
        "raw_status": row.status,
        "phase": phase,
        "folders_total": row.folders_total,
        "folders_done": row.folders_done,
        "messages_copied": row.messages_copied,
        "bytes_copied": row.bytes_copied,
        "error": row.error,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "source_is_preserved": True,
        "safe_to_repeat": True,
    }


def _run(job_id: str, account_id: str, phase: MigrationPhase) -> None:
    db = SessionLocal()
    try:
        job = db.get(MailMigrationJob, UUID(job_id))
        account = db.get(ConnectedMailAccount, UUID(account_id))
        if job is None or account is None or account.mailbox_id != job.mailbox_id:
            return
        mailbox = db.get(Mailbox, job.mailbox_id)
        if mailbox is None or mailbox.status != MailboxStatus.active:
            job.status = f"failed_{phase}"
            job.error = "Destination mailbox is no longer active"
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
            return

        job.status = f"running_{phase}"
        job.started_at = datetime.now(timezone.utc)
        job.error = None
        db.commit()
        try:
            config = config_for_account(account, db)
            result = migrate_imap_mailbox(
                destination_address=mailbox.address,
                source_provider=account.provider,
                source_username=config.username,
                source_password=config.password or None,
                oauth2_token=config.access_token or None,
                source_host=config.imap_host,
                source_port=config.imap_port,
                source_security=config.imap_security,
                destination_quota_bytes=mailbox.quota_bytes,
            )
            clean = bool(result.get("clean"))
            job.status = f"completed_{phase}" if clean else f"partial_{phase}"
            job.folders_total = int(result.get("folders_total", 0))
            job.folders_done = int(result.get("folders_done", 0))
            job.messages_copied = int(result.get("messages_copied", 0))
            job.bytes_copied = int(result.get("bytes_copied", 0))
            failures = [str(item) for item in result.get("failure_details", [])]
            if failures:
                job.error = (
                    f"{int(result.get('messages_failed', 0))} source item(s) could not be copied. "
                    + " | ".join(failures[:10])
                )[:10000]
            else:
                job.error = None
            account.last_sync_at = datetime.now(timezone.utc)
            account.status = "active"
            account.last_error = None if clean else (job.error or "Migration completed with source items requiring retry")[:2000]
        except Exception as exc:
            job.status = f"failed_{phase}"
            job.error = str(exc)[:10000]
            account.last_error = str(exc)[:2000]
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


def _running_job(db: Session, mailbox: Mailbox) -> MailMigrationJob | None:
    return db.scalar(
        select(MailMigrationJob)
        .where(
            MailMigrationJob.mailbox_id == mailbox.id,
            or_(
                MailMigrationJob.status == "queued",
                MailMigrationJob.status == "running",
                MailMigrationJob.status.like("queued_%"),
                MailMigrationJob.status.like("running_%"),
            ),
        )
        .order_by(MailMigrationJob.created_at.desc())
    )


def _new_job(db: Session, mailbox: Mailbox, account: ConnectedMailAccount, phase: MigrationPhase) -> MailMigrationJob:
    try:
        config = config_for_account(account, db)
    except ConnectedMailError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    job = MailMigrationJob(
        tenant_id=mailbox.tenant_id,
        mailbox_id=mailbox.id,
        source_provider=f"connected:{account.id}:{account.provider}",
        source_host=config.imap_host,
        source_port=config.imap_port,
        source_username=account.address,
        status=f"queued_{phase}",
        created_by_user_id=mailbox.created_by_user_id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.get("")
def list_jobs(token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None, db: Session = Depends(get_db)):
    mailbox = _owner(token, db)
    rows = db.scalars(
        select(MailMigrationJob)
        .where(MailMigrationJob.mailbox_id == mailbox.id)
        .order_by(MailMigrationJob.created_at.desc())
        .limit(50)
    ).all()
    return {
        "items": [_payload(row, mailbox) for row in rows],
        "cutover": {
            "steps": ["initial", "delta", "final"],
            "source_mail_is_never_deleted": True,
            "repeat_runs_are_deduplicated": True,
        },
    }


@router.get("/{job_id}")
def get_job(job_id: UUID, token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None, db: Session = Depends(get_db)):
    mailbox = _owner(token, db)
    row = db.get(MailMigrationJob, job_id)
    if row is None or row.mailbox_id != mailbox.id:
        raise HTTPException(status_code=404, detail="Migration job not found")
    return _payload(row, mailbox)


@router.post("/connected/{account_id}", status_code=202)
def start_connected(
    account_id: UUID,
    background_tasks: BackgroundTasks,
    phase: MigrationPhase = Query(default="initial"),
    token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None,
    db: Session = Depends(get_db),
):
    mailbox = _owner(token, db)
    account = _account(db, mailbox, account_id)
    if account.address.lower() == mailbox.address.lower():
        raise HTTPException(status_code=422, detail="Source and destination must be different mailboxes")
    running = _running_job(db, mailbox)
    if running is not None:
        return {"queued": True, "already_running": True, "job": _payload(running, mailbox)}

    if phase in {"delta", "final"}:
        prior = db.scalar(
            select(MailMigrationJob)
            .where(
                MailMigrationJob.mailbox_id == mailbox.id,
                MailMigrationJob.source_provider.like(f"connected:{account.id}:%"),
                or_(MailMigrationJob.status.like("completed_%"), MailMigrationJob.status.like("partial_%"), MailMigrationJob.status == "completed"),
            )
            .order_by(MailMigrationJob.created_at.desc())
        )
        if prior is None:
            raise HTTPException(status_code=409, detail="Run the initial mailbox copy before starting a delta or final sync")

    job = _new_job(db, mailbox, account, phase)
    background_tasks.add_task(_run, str(job.id), str(account.id), phase)
    return {"queued": True, "already_running": False, "job": _payload(job, mailbox)}


@router.post("/{job_id}/resume", status_code=202)
def resume(
    job_id: UUID,
    background_tasks: BackgroundTasks,
    token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None,
    db: Session = Depends(get_db),
):
    mailbox = _owner(token, db)
    row = db.get(MailMigrationJob, job_id)
    if row is None or row.mailbox_id != mailbox.id:
        raise HTTPException(status_code=404, detail="Migration job not found")
    state, phase = _status_parts(row.status)
    if state not in {"failed", "partial"}:
        raise HTTPException(status_code=409, detail="Only failed or partial migration runs need to be resumed")
    if not row.source_provider.startswith("connected:"):
        raise HTTPException(status_code=409, detail="Reconnect the original source mailbox before resuming this older migration")
    parts = row.source_provider.split(":", 2)
    account = _account(db, mailbox, UUID(parts[1]))
    row.status = f"queued_{phase}"
    row.error = None
    row.completed_at = None
    db.commit()
    background_tasks.add_task(_run, str(row.id), str(account.id), phase)
    return {"queued": True, "job": _payload(row, mailbox)}
