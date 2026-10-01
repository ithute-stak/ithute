import json
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.v1 import external_webmail as legacy_external
from app.core.config import settings
from app.db.session import SessionLocal, get_db
from app.models import AuditLog, MailMigrationJob, Mailbox, MailboxStatus
from app.services.external_webmail import ExternalMailboxConfig, ExternalWebmailError, session_config
from app.services.mail_migration import migrate_imap_mailbox
from app.services.mail_provider_detection import (
    detect_mail_provider,
    migration_provider_key,
    provider_detection_payload,
)
from app.services.webmail import WebmailError, session_credentials

router = APIRouter(prefix="/webmail/external", tags=["external-webmail-smart"])
EXTERNAL_COOKIE = f"{settings.webmail_session_cookie_name}_external"
HOSTED_COOKIE = settings.webmail_session_cookie_name
MigrationPhase = Literal["initial", "delta", "final"]


class WebmailMigrationStart(BaseModel):
    destination_address: str = Field(min_length=3, max_length=320)
    phase: MigrationPhase = "initial"


def _looks_generated(host: str, domain: str, role: str) -> bool:
    value = (host or "").strip().lower()
    if not value:
        return True
    names = {f"mail.{domain}"}
    if role == "imap":
        names.add(f"imap.{domain}")
    else:
        names.add(f"smtp.{domain}")
    return value in names


def _provider_adjusted_login(payload: legacy_external.ExternalLogin) -> tuple[legacy_external.ExternalLogin, dict]:
    address = str(payload.address).strip().lower()
    detection = provider_detection_payload(address)
    provider = detection["provider"]
    if not detection["detected"]:
        return payload, detection

    domain = address.rsplit("@", 1)[1]
    imap_generated = _looks_generated(payload.imap_host, domain, "imap")
    smtp_generated = _looks_generated(payload.smtp_host, domain, "smtp")
    if not (imap_generated and smtp_generated):
        return payload, detection

    adjusted = payload.model_copy(
        update={
            "username": payload.username.strip() or address,
            "imap_host": provider["imap_host"],
            "imap_port": provider["imap_port"],
            "imap_security": provider["imap_security"],
            "smtp_host": provider["smtp_host"],
            "smtp_port": provider["smtp_port"],
            "smtp_security": provider["smtp_security"],
        }
    )
    return adjusted, detection


@router.get("/provider-detect")
def provider_detect(address: str = Query(min_length=3, max_length=320)):
    try:
        return provider_detection_payload(address)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/session")
def smart_login(
    payload: legacy_external.ExternalLogin,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    adjusted, detection = _provider_adjusted_login(payload)
    result = legacy_external.login(adjusted, request, response, db)
    result["provider_detected"] = bool(detection["detected"])
    result["provider"] = detection["provider"]
    return result


def _source_config(token: str | None) -> ExternalMailboxConfig | None:
    if not token:
        return None
    try:
        return session_config(token)
    except ExternalWebmailError:
        return None


def _hosted_address(token: str | None) -> str | None:
    if not token:
        return None
    try:
        address, _ = session_credentials(token)
        return address.strip().lower()
    except WebmailError:
        return None


def _active_mailbox(db: Session, address: str | None) -> Mailbox | None:
    if not address:
        return None
    return db.scalar(select(Mailbox).where(Mailbox.address == address, Mailbox.status == MailboxStatus.active))


def _status_parts(value: str) -> tuple[str, str]:
    raw = (value or "queued").strip().lower()
    for phase in ("initial", "delta", "final"):
        suffix = f"_{phase}"
        if raw.endswith(suffix):
            return raw[: -len(suffix)], phase
    return raw, "initial"


def _job_payload(job: MailMigrationJob, destination: str) -> dict:
    state, phase = _status_parts(job.status)
    return {
        "id": str(job.id),
        "destination": destination,
        "source_provider": job.source_provider,
        "source_username": job.source_username,
        "status": state,
        "raw_status": job.status,
        "phase": phase,
        "folders_total": job.folders_total,
        "folders_done": job.folders_done,
        "messages_copied": job.messages_copied,
        "bytes_copied": job.bytes_copied,
        "error": job.error,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "source_is_preserved": True,
        "safe_to_repeat": True,
    }


@router.get("/migration/readiness")
def migration_readiness(
    external_token: Annotated[str | None, Cookie(alias=EXTERNAL_COOKIE)] = None,
    hosted_token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None,
    db: Session = Depends(get_db),
):
    source = _source_config(external_token)
    destination_address = _hosted_address(hosted_token)
    mailbox = _active_mailbox(db, destination_address)
    profile = None
    if source:
        try:
            detected = detect_mail_provider(source.address)
            profile = detected.public_dict() if detected else None
        except ValueError:
            profile = None

    issues: list[str] = []
    if source is None:
        issues.append("Connect the Gmail or external mailbox first.")
    if destination_address is None:
        issues.append("Sign in to the Ithute business mailbox that will receive the migrated mail.")
    elif mailbox is None:
        issues.append("The signed-in destination is not an active Ithute-hosted mailbox.")
    if source and destination_address and source.address.lower() == destination_address.lower():
        issues.append("Source and destination mailboxes must be different.")

    prior = []
    if mailbox is not None:
        rows = db.scalars(
            select(MailMigrationJob)
            .where(MailMigrationJob.mailbox_id == mailbox.id)
            .order_by(MailMigrationJob.created_at.desc())
            .limit(20)
        ).all()
        prior = [_job_payload(row, mailbox.address) for row in rows]

    initial_done = any(item["phase"] == "initial" and item["status"] in {"completed", "partial"} for item in prior)
    final_clean = any(item["phase"] == "final" and item["status"] == "completed" for item in prior)
    return {
        "ready": not issues,
        "issues": issues,
        "source": ({
            "address": source.address,
            "provider": profile or {"key": migration_provider_key(source.address, source.imap_host), "name": "External IMAP"},
            "imap_host": source.imap_host,
        } if source else None),
        "destination": ({
            "address": destination_address,
            "active": mailbox is not None,
            "mailbox_id": str(mailbox.id) if mailbox else None,
        } if destination_address else None),
        "behavior": {
            "copies_mail": True,
            "deletes_source": False,
            "preserves_folders": True,
            "preserves_message_dates": True,
            "safe_to_resume": True,
            "deduplicates_repeat_syncs": True,
            "contacts_and_calendars_included": False,
        },
        "cutover": {
            "initial_done": initial_done,
            "final_clean": final_clean,
            "steps": ["initial", "delta", "final"],
        },
    }


def _run_migration_job(job_id: str, source: ExternalMailboxConfig, phase: MigrationPhase) -> None:
    db = SessionLocal()
    try:
        job = db.get(MailMigrationJob, UUID(job_id))
        if job is None:
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

        skipped = 0
        failed = 0
        try:
            provider = migration_provider_key(source.address, source.imap_host)
            result = migrate_imap_mailbox(
                destination_address=mailbox.address,
                source_provider=provider,
                source_username=source.username,
                source_password=source.password,
                source_host=source.imap_host,
                source_port=source.imap_port,
                source_security=source.imap_security,
                destination_quota_bytes=mailbox.quota_bytes,
            )
            job.folders_total = int(result.get("folders_total", 0))
            job.folders_done = int(result.get("folders_done", 0))
            job.messages_copied = int(result.get("messages_copied", 0))
            job.bytes_copied = int(result.get("bytes_copied", 0))
            skipped = int(result.get("messages_skipped", 0))
            failed = int(result.get("messages_failed", 0))
            failures = [str(value) for value in result.get("failure_details", [])]
            clean = bool(result.get("clean"))
            job.status = f"completed_{phase}" if clean else f"partial_{phase}"
            job.error = None if clean else (
                f"{failed} source item(s) require retry. " + " | ".join(failures[:10])
            )[:10000]
        except Exception as exc:
            job.status = f"failed_{phase}"
            job.error = str(exc)[:10000]

        job.completed_at = datetime.now(timezone.utc)
        db.add(AuditLog(
            tenant_id=mailbox.tenant_id,
            actor_user_id=mailbox.created_by_user_id,
            action="webmail.external.migration",
            resource_type="mail_migration_job",
            resource_id=str(job.id),
            metadata_json=json.dumps({
                "source": source.address,
                "destination": mailbox.address,
                "phase": phase,
                "status": job.status,
                "messages_skipped": skipped,
                "messages_failed": failed,
                "source_deleted": False,
                "initiated_by": "webmail",
            }),
        ))
        db.commit()
    finally:
        db.close()


def _running_job(db: Session, mailbox: Mailbox) -> MailMigrationJob | None:
    return db.scalar(
        select(MailMigrationJob)
        .where(
            MailMigrationJob.mailbox_id == mailbox.id,
            or_(
                MailMigrationJob.status.in_(["queued", "running"]),
                MailMigrationJob.status.like("queued_%"),
                MailMigrationJob.status.like("running_%"),
            ),
        )
        .order_by(MailMigrationJob.created_at.desc())
    )


def _prior_sync(db: Session, mailbox: Mailbox, source: ExternalMailboxConfig) -> MailMigrationJob | None:
    return db.scalar(
        select(MailMigrationJob)
        .where(
            MailMigrationJob.mailbox_id == mailbox.id,
            MailMigrationJob.source_username == source.username,
            or_(
                MailMigrationJob.status == "completed",
                MailMigrationJob.status.like("completed_%"),
                MailMigrationJob.status.like("partial_%"),
            ),
        )
        .order_by(MailMigrationJob.created_at.desc())
    )


@router.post("/migration/start", status_code=202)
def start_migration(
    payload: WebmailMigrationStart,
    background_tasks: BackgroundTasks,
    external_token: Annotated[str | None, Cookie(alias=EXTERNAL_COOKIE)] = None,
    hosted_token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None,
    db: Session = Depends(get_db),
):
    source = _source_config(external_token)
    if source is None:
        raise HTTPException(status_code=401, detail="Connect the source external mailbox before starting migration")

    destination_address = _hosted_address(hosted_token)
    if destination_address is None:
        raise HTTPException(status_code=401, detail="Sign in to the destination Ithute business mailbox first")
    if payload.destination_address.strip().lower() != destination_address:
        raise HTTPException(status_code=409, detail="Destination confirmation does not match the signed-in business mailbox")
    if source.address.lower() == destination_address:
        raise HTTPException(status_code=422, detail="Source and destination mailboxes must be different")

    mailbox = _active_mailbox(db, destination_address)
    if mailbox is None:
        raise HTTPException(status_code=409, detail="Destination mailbox is not active")

    running = _running_job(db, mailbox)
    if running is not None:
        return {"queued": True, "already_running": True, "job": _job_payload(running, mailbox.address)}

    if payload.phase in {"delta", "final"} and _prior_sync(db, mailbox, source) is None:
        raise HTTPException(status_code=409, detail="Run the initial mailbox copy before starting a delta or final sync")

    provider = migration_provider_key(source.address, source.imap_host)
    job = MailMigrationJob(
        tenant_id=mailbox.tenant_id,
        mailbox_id=mailbox.id,
        source_provider=provider,
        source_host=source.imap_host,
        source_port=source.imap_port,
        source_username=source.username,
        status=f"queued_{payload.phase}",
        created_by_user_id=mailbox.created_by_user_id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(_run_migration_job, str(job.id), source, payload.phase)
    return {"queued": True, "already_running": False, "job": _job_payload(job, mailbox.address)}


@router.post("/migration/jobs/{job_id}/resume", status_code=202)
def resume_migration(
    job_id: UUID,
    background_tasks: BackgroundTasks,
    external_token: Annotated[str | None, Cookie(alias=EXTERNAL_COOKIE)] = None,
    hosted_token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None,
    db: Session = Depends(get_db),
):
    source = _source_config(external_token)
    destination_address = _hosted_address(hosted_token)
    mailbox = _active_mailbox(db, destination_address)
    if source is None or mailbox is None:
        raise HTTPException(status_code=401, detail="Reconnect the source mailbox and sign in to the Ithute destination mailbox")
    job = db.get(MailMigrationJob, job_id)
    if job is None or job.mailbox_id != mailbox.id:
        raise HTTPException(status_code=404, detail="Migration job not found")
    state, phase = _status_parts(job.status)
    if state not in {"failed", "partial"}:
        raise HTTPException(status_code=409, detail="Only failed or partial migration runs need to be resumed")
    if job.source_username.lower() != source.username.lower():
        raise HTTPException(status_code=409, detail="Reconnect the same source mailbox that created this migration")
    if _running_job(db, mailbox) is not None:
        raise HTTPException(status_code=409, detail="Another migration sync is already running")
    job.status = f"queued_{phase}"
    job.error = None
    job.completed_at = None
    db.commit()
    db.refresh(job)
    background_tasks.add_task(_run_migration_job, str(job.id), source, phase)
    return {"queued": True, "job": _job_payload(job, mailbox.address)}


@router.get("/migration/jobs")
def migration_jobs(
    hosted_token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None,
    db: Session = Depends(get_db),
):
    destination_address = _hosted_address(hosted_token)
    mailbox = _active_mailbox(db, destination_address)
    if mailbox is None:
        raise HTTPException(status_code=401, detail="Sign in to an active Ithute business mailbox")
    rows = db.scalars(
        select(MailMigrationJob)
        .where(MailMigrationJob.mailbox_id == mailbox.id)
        .order_by(MailMigrationJob.created_at.desc())
        .limit(20)
    ).all()
    return {"items": [_job_payload(row, mailbox.address) for row in rows]}


@router.get("/migration/jobs/{job_id}")
def migration_job(
    job_id: UUID,
    hosted_token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None,
    db: Session = Depends(get_db),
):
    destination_address = _hosted_address(hosted_token)
    mailbox = _active_mailbox(db, destination_address)
    if mailbox is None:
        raise HTTPException(status_code=401, detail="Sign in to an active Ithute business mailbox")
    job = db.get(MailMigrationJob, job_id)
    if job is None or job.mailbox_id != mailbox.id:
        raise HTTPException(status_code=404, detail="Migration job not found")
    return _job_payload(job, mailbox.address)
