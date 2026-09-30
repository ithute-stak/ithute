from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_tenant_permission
from app.core.security import hash_token
from app.db.session import get_db
from app.models import AuditLog, HostingSource, User

router = APIRouter(tags=["hosting-uploads"])
MAX_ZIP_BYTES = 2 * 1024 * 1024 * 1024
MAX_UNPACKED_BYTES = 2 * 1024 * 1024 * 1024
MAX_FILES = 100_000
UPLOAD_TTL_MINUTES = 30
MAX_STORAGE_INVENTORY_KEYS = 100_000


class UploadAuthorize(BaseModel):
    upload_token: str = Field(min_length=20, max_length=256)


class UploadComplete(BaseModel):
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(gt=0, le=MAX_ZIP_BYTES)
    unpacked_size_bytes: int = Field(ge=0, le=MAX_UNPACKED_BYTES)
    file_count: int = Field(ge=1, le=MAX_FILES)


class UploadFailure(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _service_auth(token: str | None) -> None:
    expected = os.getenv("ITHUTE_HOSTING_UPLOAD_SERVICE_TOKEN", "").strip()
    supplied = (token or "").strip()
    if not expected or not expected.startswith("ith_upload_"):
        raise HTTPException(status_code=503, detail="Hosting upload service is not configured")
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid hosting upload service credential")


def _source(db: Session, source_id: UUID, *, lock: bool = False) -> HostingSource:
    query = select(HostingSource).where(HostingSource.id == source_id, HostingSource.source_type == "zip")
    if lock:
        query = query.with_for_update()
    row = db.scalar(query)
    if row is None:
        raise HTTPException(status_code=404, detail="ZIP source not found")
    return row


def _audit(db: Session, source: HostingSource, action: str, actor_user_id: UUID | None, metadata: dict | None = None) -> None:
    import json
    db.add(AuditLog(
        tenant_id=source.tenant_id,
        actor_user_id=actor_user_id,
        action=action,
        resource_type="hosting_source",
        resource_id=str(source.id),
        metadata_json=json.dumps(metadata or {}, sort_keys=True),
    ))


@router.post("/tenants/{tenant_id}/hosting/projects/{project_id}/sources/{source_id}/upload-ticket")
def create_upload_ticket(
    tenant_id: UUID,
    project_id: UUID,
    source_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    row = _source(db, source_id, lock=True)
    if row.tenant_id != tenant_id or row.project_id != project_id:
        raise HTTPException(status_code=404, detail="ZIP source not found in this project")
    if row.status not in {"uploading", "failed"}:
        raise HTTPException(status_code=409, detail="Only an unverified ZIP source can receive an upload ticket")
    if not row.upload_object_key or not row.size_bytes or row.size_bytes > MAX_ZIP_BYTES:
        raise HTTPException(status_code=409, detail="ZIP source metadata is incomplete or exceeds the upload limit")

    raw = "ith_zip_" + secrets.token_urlsafe(36)
    expires_at = _now() + timedelta(minutes=UPLOAD_TTL_MINUTES)
    row.upload_token_hash = hash_token(raw)
    row.upload_expires_at = expires_at
    row.status = "uploading"
    row.failure_message = None
    _audit(db, row, "hosting.source.zip.ticket", current.id, {"expires_at": expires_at.isoformat()})
    db.commit()

    base = os.getenv("ITHUTE_HOSTING_UPLOAD_PUBLIC_URL", "").strip().rstrip("/")
    return {
        "source_id": str(row.id),
        "upload_token": raw,
        "upload_url": f"{base}/v1/uploads/{row.id}" if base else None,
        "expires_at": expires_at.isoformat(),
        "method": "PUT",
        "content_type": "application/zip",
        "warning": "This one-time upload credential expires in 30 minutes and is invalidated after verification or failure.",
    }


@router.post("/hosting/upload/storage/inventory")
def upload_storage_inventory(
    x_ithute_upload_service: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Return only storage object keys that still belong to source records.

    This endpoint is service-authenticated and intentionally excludes tenant,
    user and project metadata. The cleanup worker uses it to identify local
    verified files that are true filesystem orphans. Referenced archives are
    never eligible for automatic cleanup here, regardless of age.
    """
    _service_auth(x_ithute_upload_service)
    keys = db.scalars(
        select(HostingSource.upload_object_key)
        .where(
            HostingSource.source_type == "zip",
            HostingSource.upload_object_key.is_not(None),
        )
        .order_by(HostingSource.created_at.desc())
        .limit(MAX_STORAGE_INVENTORY_KEYS)
    ).all()
    if len(keys) >= MAX_STORAGE_INVENTORY_KEYS:
        raise HTTPException(status_code=503, detail="ZIP storage inventory exceeds the safe cleanup inventory limit")
    return {"referenced_object_keys": [str(key) for key in keys if key]}


@router.post("/hosting/upload/sources/{source_id}/authorize")
def authorize_upload(
    source_id: UUID,
    payload: UploadAuthorize,
    x_ithute_upload_service: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    _service_auth(x_ithute_upload_service)
    row = _source(db, source_id, lock=True)
    now = _now()
    if row.status != "uploading" or not row.upload_token_hash or not row.upload_expires_at:
        raise HTTPException(status_code=409, detail="ZIP source is not accepting uploads")
    if row.upload_expires_at <= now:
        row.upload_token_hash = None
        row.upload_expires_at = None
        row.status = "failed"
        row.failure_message = "ZIP upload ticket expired"
        db.commit()
        raise HTTPException(status_code=410, detail="ZIP upload ticket expired")
    if not secrets.compare_digest(row.upload_token_hash, hash_token(payload.upload_token.strip())):
        raise HTTPException(status_code=401, detail="Invalid ZIP upload credential")
    return {
        "source_id": str(row.id),
        "object_key": row.upload_object_key,
        "expected_sha256": row.sha256,
        "expected_size_bytes": row.size_bytes,
        "max_size_bytes": MAX_ZIP_BYTES,
        "max_unpacked_size_bytes": MAX_UNPACKED_BYTES,
        "max_files": MAX_FILES,
    }


@router.post("/hosting/upload/sources/{source_id}/complete")
def complete_upload(
    source_id: UUID,
    payload: UploadComplete,
    x_ithute_upload_service: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    _service_auth(x_ithute_upload_service)
    row = _source(db, source_id, lock=True)
    if row.status != "uploading" or not row.upload_token_hash:
        raise HTTPException(status_code=409, detail="ZIP source is not awaiting verification")
    if row.size_bytes is not None and payload.size_bytes != row.size_bytes:
        raise HTTPException(status_code=422, detail="Uploaded ZIP size does not match registered source metadata")
    if row.sha256 is not None and payload.sha256 != row.sha256:
        raise HTTPException(status_code=422, detail="Uploaded ZIP checksum does not match registered source metadata")
    row.sha256 = payload.sha256
    row.size_bytes = payload.size_bytes
    row.unpacked_size_bytes = payload.unpacked_size_bytes
    row.file_count = payload.file_count
    row.verified_at = _now()
    row.status = "ready"
    row.failure_message = None
    row.upload_token_hash = None
    row.upload_expires_at = None
    _audit(db, row, "hosting.source.zip.verified", None, {"sha256": payload.sha256, "size_bytes": payload.size_bytes, "unpacked_size_bytes": payload.unpacked_size_bytes, "file_count": payload.file_count})
    db.commit()
    return {"verified": True, "source_id": str(row.id), "status": row.status}


@router.post("/hosting/upload/sources/{source_id}/failed")
def fail_upload(
    source_id: UUID,
    payload: UploadFailure,
    x_ithute_upload_service: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    _service_auth(x_ithute_upload_service)
    row = _source(db, source_id, lock=True)
    if row.status == "ready":
        raise HTTPException(status_code=409, detail="Verified ZIP source cannot be failed by the upload service")
    row.status = "failed"
    row.failure_message = payload.message.strip()[:2000]
    row.upload_token_hash = None
    row.upload_expires_at = None
    _audit(db, row, "hosting.source.zip.failed", None, {"message": row.failure_message})
    db.commit()
    return {"verified": False, "source_id": str(row.id), "status": row.status}
