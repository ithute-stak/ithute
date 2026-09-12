import json
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
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


class WebmailMigrationStart(BaseModel):
    destination_address: str = Field(min_length=3, max_length=320)


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
        # Advanced/manual settings are an explicit user choice; never silently
        # override them merely because the address belongs to a known provider.
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
    """Provider-aware front door for the established external session route.

    This route is registered before the legacy external router. It only changes
    generated/default server values for recognized providers and then delegates
    authentication, rate limiting, security audit and cookie creation to the
    established login implementation.
    """
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
    return db.scalar(
        select(Mailbox).where(
            Mailbox.address == address,
            Mailbox.status == MailboxStatus.active,
        )
    )


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

    return {
        "ready": not issues,
        "issues": issues,
        "source": (
            {
                "address": source.address,
                "provider": profile or {
                    "key": migration_provider_key(source.address, source.imap_host),
                    "name": "External IMAP",
                },
                "imap_host": source.imap_host,
            }
            if source
            else None
        ),
        "destination": (
            {
                "address": destination_address,
                "active": mailbox is not None,
                "mailbox_id": str(mailbox.id) if mailbox else None,
            }
            if destination_address
            else None
        ),
        "behavior": {
            "copies_mail": True,
            "deletes_source": False,
            "preserves_folders": True,
            "safe_to_resume": True,
        },
    }


def _run_migration_job(job_id: str, source: ExternalMailboxConfig) -> None:
    db = SessionLocal()
    try:
        job = db.get(MailMigrationJob, UUID(job_id))
        if job is None:
            return
        mailbox = db.get(Mailbox, job.mailbox_id)
        if mailbox is None or mailbox.status != MailboxStatus.active:
            job.status = "failed"
            job.error = "Destination mailbox is no longer active"
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
            return

        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        db.commit()

        skipped = 0
        try:
            provider = migration_provider_key(source.address, source.imap_host)
            result = migrate_imap_mailbox(
                destination_address=mailbox.address,
                source_provider=provider,
                source_username=source.username,
                source_password=source.password,
                source_host=source.imap_host,
                source_port=source.imap_port,
            )
            job.status = "completed"
            job.folders_total = int(result.get("folders_total", 0))
            job.folders_done = int(result.get("folders_done", 0))
            job.messages_copied = int(result.get("messages_copied", 0))
            job.bytes_copied = int(result.get("bytes_copied", 0))
            skipped = int(result.get("messages_skipped", 0))
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)[:10000]
        job.completed_at = datetime.now(timezone.utc)
        db.add(
            AuditLog(
                tenant_id=mailbox.tenant_id,
                actor_user_id=mailbox.created_by_user_id,
                action="webmail.external.migration",
                resource_type="mail_migration_job",
                resource_id=str(job.id),
                metadata_json=json.dumps(
                    {
                        "source": source.address,
                        "destination": mailbox.address,
                        "status": job.status,
                        "messages_skipped": skipped,
                        "initiated_by": "webmail",
                    }
                ),
            )
        )
        db.commit()
    finally:
        db.close()


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

    running = db.scalar(
        select(MailMigrationJob)
        .where(
            MailMigrationJob.mailbox_id == mailbox.id,
            MailMigrationJob.status.in_(["queued", "running"]),
        )
        .order_by(MailMigrationJob.created_at.desc())
    )
    if running is not None:
        return {
            "queued": True,
            "already_running": True,
            "job": _job_payload(running, mailbox.address),
        }

    provider = migration_provider_key(source.address, source.imap_host)
    job = MailMigrationJob(
        tenant_id=mailbox.tenant_id,
        mailbox_id=mailbox.id,
        source_provider=provider,
        source_host=source.imap_host,
        source_port=source.imap_port,
        source_username=source.username,
        status="queued",
        created_by_user_id=mailbox.created_by_user_id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(_run_migration_job, str(job.id), source)
    return {
        "queued": True,
        "already_running": False,
        "job": _job_payload(job, mailbox.address),
    }


def _job_payload(job: MailMigrationJob, destination: str) -> dict:
    return {
        "id": str(job.id),
        "destination": destination,
        "source_provider": job.source_provider,
        "source_username": job.source_username,
        "status": job.status,
        "folders_total": job.folders_total,
        "folders_done": job.folders_done,
        "messages_copied": job.messages_copied,
        "bytes_copied": job.bytes_copied,
        "error": job.error,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


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
