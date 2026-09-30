from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_tenant_permission
from app.core.security import decrypt_secret, encrypt_secret
from app.db.session import get_db
from app.models import (
    AuditLog,
    HostingProject,
    HostingSource,
    HostingSourceWebhook,
    HostingWebhookDelivery,
    User,
)
from app.services.hosting_webhooks import queue_webhook_build

router = APIRouter(tags=["hosting-git-webhooks"])
MAX_WEBHOOK_BODY_BYTES = 2 * 1024 * 1024
DELIVERY_RETENTION_DAYS = 30


class WebhookConfigure(BaseModel):
    provider: str = Field(pattern=r"^(github|gitlab|bitbucket|generic)$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _source(db: Session, tenant_id: UUID, project_id: UUID, source_id: UUID) -> HostingSource:
    row = db.scalar(
        select(HostingSource).where(
            HostingSource.id == source_id,
            HostingSource.tenant_id == tenant_id,
            HostingSource.project_id == project_id,
            HostingSource.source_type == "git",
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Git source not found in this project")
    return row


def _webhook_out(row: HostingSourceWebhook) -> dict:
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "project_id": str(row.project_id),
        "source_id": str(row.source_id),
        "provider": row.provider,
        "status": row.status,
        "pending_rebuild": row.pending_rebuild,
        "webhook_path": f"/api/v1/hosting/webhooks/{row.id}",
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _hmac_signature(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _verify_signature(provider: str, secret: str, body: bytes, headers) -> str:
    if provider == "gitlab":
        supplied = (headers.get("x-gitlab-token") or "").strip()
        if not supplied or not secrets.compare_digest(supplied, secret):
            raise HTTPException(status_code=401, detail="Invalid GitLab webhook token")
        return (headers.get("x-gitlab-event") or "").strip()

    if provider == "github":
        supplied = (headers.get("x-hub-signature-256") or "").strip().lower()
        if not supplied or not secrets.compare_digest(supplied, _hmac_signature(secret, body)):
            raise HTTPException(status_code=401, detail="Invalid GitHub webhook signature")
        return (headers.get("x-github-event") or "").strip()

    if provider == "bitbucket":
        supplied = (headers.get("x-hub-signature") or "").strip().lower()
        if not supplied or not secrets.compare_digest(supplied, _hmac_signature(secret, body)):
            raise HTTPException(status_code=401, detail="Invalid Bitbucket webhook signature")
        return (headers.get("x-event-key") or "").strip()

    supplied = (headers.get("x-ithute-signature") or "").strip().lower()
    if not supplied or not secrets.compare_digest(supplied, _hmac_signature(secret, body)):
        raise HTTPException(status_code=401, detail="Invalid generic webhook signature")
    return (headers.get("x-ithute-event") or "push").strip()


def _delivery_id(provider: str, event_name: str, body: bytes, headers) -> str:
    candidates = {
        "github": headers.get("x-github-delivery"),
        "gitlab": headers.get("x-gitlab-event-uuid") or headers.get("x-request-id"),
        "bitbucket": headers.get("x-request-uuid"),
        "generic": headers.get("x-ithute-delivery"),
    }
    supplied = str(candidates.get(provider) or "").strip()
    if supplied:
        return supplied[:160]
    return hashlib.sha256(provider.encode() + b"\x00" + event_name.encode() + b"\x00" + body).hexdigest()


def _branch_and_commit(provider: str, event_name: str, payload: dict, expected_branch: str) -> tuple[bool, str | None]:
    target_ref = f"refs/heads/{expected_branch}"
    if provider == "github":
        if event_name != "push":
            return False, None
        if str(payload.get("ref") or "") != target_ref:
            return False, None
        return True, str(payload.get("after") or "").strip().lower() or None

    if provider == "gitlab":
        if event_name.lower() not in {"push hook", "push"}:
            return False, None
        if str(payload.get("ref") or "") != target_ref:
            return False, None
        return True, str(payload.get("checkout_sha") or payload.get("after") or "").strip().lower() or None

    if provider == "bitbucket":
        if event_name != "repo:push":
            return False, None
        changes = payload.get("push", {}).get("changes", []) if isinstance(payload.get("push"), dict) else []
        for change in changes if isinstance(changes, list) else []:
            new = change.get("new") if isinstance(change, dict) else None
            if not isinstance(new, dict) or str(new.get("type") or "") != "branch" or str(new.get("name") or "") != expected_branch:
                continue
            target = new.get("target")
            commit = str(target.get("hash") or "").strip().lower() if isinstance(target, dict) else None
            return True, commit or None
        return False, None

    if event_name.lower() != "push":
        return False, None
    ref = str(payload.get("ref") or "")
    if ref not in {expected_branch, target_ref}:
        return False, None
    return True, str(payload.get("commit") or payload.get("after") or "").strip().lower() or None


def _safe_commit(value: str | None) -> str | None:
    if not value:
        return None
    commit = value.lower()
    if not (7 <= len(commit) <= 64) or any(ch not in "0123456789abcdef" for ch in commit):
        return None
    return commit


@router.get("/tenants/{tenant_id}/hosting/projects/{project_id}/sources/{source_id}/webhook")
def get_source_webhook(
    tenant_id: UUID,
    project_id: UUID,
    source_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.read", db, current)
    _source(db, tenant_id, project_id, source_id)
    row = db.scalar(select(HostingSourceWebhook).where(HostingSourceWebhook.source_id == source_id))
    return {"webhook": _webhook_out(row) if row else None}


@router.put("/tenants/{tenant_id}/hosting/projects/{project_id}/sources/{source_id}/webhook")
def create_or_rotate_source_webhook(
    tenant_id: UUID,
    project_id: UUID,
    source_id: UUID,
    payload: WebhookConfigure,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    source = _source(db, tenant_id, project_id, source_id)
    raw = "ith_hook_" + secrets.token_urlsafe(36)
    row = db.scalar(select(HostingSourceWebhook).where(HostingSourceWebhook.source_id == source.id).with_for_update())
    if row is None:
        row = HostingSourceWebhook(
            tenant_id=tenant_id,
            project_id=project_id,
            source_id=source.id,
            provider=payload.provider,
            encrypted_secret=encrypt_secret(raw),
            status="active",
            created_by_user_id=current.id,
        )
        db.add(row)
    else:
        row.provider = payload.provider
        row.encrypted_secret = encrypt_secret(raw)
        row.status = "active"
        row.pending_rebuild = False
        row.pending_commit = None
        row.created_by_user_id = current.id
    db.flush()
    db.add(AuditLog(
        tenant_id=tenant_id,
        actor_user_id=current.id,
        action="hosting.source.webhook.configure",
        resource_type="hosting_source_webhook",
        resource_id=str(row.id),
        metadata_json=json.dumps({"source_id": str(source.id), "provider": row.provider}, sort_keys=True),
    ))
    db.commit()
    db.refresh(row)
    result = _webhook_out(row)
    result["secret"] = raw
    result["warning"] = "Webhook secret is shown once. Configure it in the Git provider and do not store it in source code."
    return result


@router.delete("/tenants/{tenant_id}/hosting/projects/{project_id}/sources/{source_id}/webhook", status_code=204)
def disable_source_webhook(
    tenant_id: UUID,
    project_id: UUID,
    source_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    _source(db, tenant_id, project_id, source_id)
    row = db.scalar(select(HostingSourceWebhook).where(HostingSourceWebhook.source_id == source_id).with_for_update())
    if row is not None and row.status != "disabled":
        row.status = "disabled"
        row.pending_rebuild = False
        row.pending_commit = None
        db.add(AuditLog(
            tenant_id=tenant_id,
            actor_user_id=current.id,
            action="hosting.source.webhook.disable",
            resource_type="hosting_source_webhook",
            resource_id=str(row.id),
            metadata_json=json.dumps({"source_id": str(source_id)}, sort_keys=True),
        ))
        db.commit()


@router.post("/hosting/webhooks/{webhook_id}", status_code=202)
async def receive_source_webhook(webhook_id: UUID, request: Request, response: Response, db: Session = Depends(get_db)):
    length_header = request.headers.get("content-length")
    try:
        declared_length = int(length_header) if length_header else 0
    except ValueError:
        declared_length = 0
    if declared_length > MAX_WEBHOOK_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Webhook payload exceeds 2 MiB")
    body = await request.body()
    if len(body) > MAX_WEBHOOK_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Webhook payload exceeds 2 MiB")

    webhook = db.scalar(
        select(HostingSourceWebhook)
        .where(HostingSourceWebhook.id == webhook_id)
        .with_for_update()
    )
    if webhook is None or webhook.status != "active":
        raise HTTPException(status_code=404, detail="Webhook not found")
    source = db.get(HostingSource, webhook.source_id)
    project = db.get(HostingProject, webhook.project_id)
    if source is None or project is None or source.source_type != "git":
        raise HTTPException(status_code=404, detail="Webhook source is unavailable")
    try:
        secret = decrypt_secret(webhook.encrypted_secret)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="Webhook secret is unavailable") from exc

    event_name = _verify_signature(webhook.provider, secret, body, request.headers)
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Webhook body must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Webhook JSON must be an object")

    delivery_id = _delivery_id(webhook.provider, event_name, body, request.headers)
    duplicate = db.scalar(
        select(HostingWebhookDelivery.id).where(
            HostingWebhookDelivery.webhook_id == webhook.id,
            HostingWebhookDelivery.delivery_id == delivery_id,
        )
    )
    if duplicate is not None:
        return {"accepted": True, "duplicate": True, "queued": False}

    matched, commit = _branch_and_commit(webhook.provider, event_name, payload, source.repository_branch or "main")
    db.add(HostingWebhookDelivery(webhook_id=webhook.id, delivery_id=delivery_id, event_name=event_name[:80] or "unknown"))
    db.execute(delete(HostingWebhookDelivery).where(HostingWebhookDelivery.received_at < _now() - timedelta(days=DELIVERY_RETENTION_DAYS)))
    if not matched:
        db.commit()
        return {"accepted": True, "duplicate": False, "queued": False, "reason": "event_or_branch_not_selected"}

    safe_commit = _safe_commit(commit)
    build = queue_webhook_build(db, webhook=webhook, source=source, project=project, commit=safe_commit)
    db.add(AuditLog(
        tenant_id=webhook.tenant_id,
        actor_user_id=webhook.created_by_user_id,
        action="hosting.source.webhook.push",
        resource_type="hosting_source_webhook",
        resource_id=str(webhook.id),
        metadata_json=json.dumps({
            "source_id": str(source.id),
            "provider": webhook.provider,
            "delivery_id": delivery_id,
            "commit": safe_commit,
            "queued": build is not None,
            "pending_rebuild": webhook.pending_rebuild,
        }, sort_keys=True),
    ))
    db.commit()
    if build is not None:
        db.refresh(build)
    return {
        "accepted": True,
        "duplicate": False,
        "queued": build is not None,
        "build_id": str(build.id) if build else None,
        "pending_rebuild": webhook.pending_rebuild,
    }
