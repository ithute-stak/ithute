from __future__ import annotations

import json
import re
import secrets
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_tenant_permission
from app.core.security import encrypt_secret
from app.db.session import get_db
from app.models import AuditLog, HostingDatabase, HostingProject, HostingSource, User

router = APIRouter(tags=["shared-hosting"])

RUNTIME_CATALOG = [
    {"id": "static", "name": "Static HTML/CSS/JavaScript", "managed": True},
    {"id": "node", "name": "Node.js", "managed": True},
    {"id": "python", "name": "Python", "managed": True},
    {"id": "php", "name": "PHP", "managed": True},
    {"id": "dotnet", "name": ".NET", "managed": True},
    {"id": "java", "name": "Java", "managed": True},
    {"id": "go", "name": "Go", "managed": True},
    {"id": "ruby", "name": "Ruby", "managed": True},
    {"id": "rust", "name": "Rust", "managed": True},
    {"id": "dockerfile", "name": "Custom Dockerfile", "managed": False},
]

_DB_IDENT_RE = re.compile(r"^[a-z][a-z0-9_]{1,47}$")
_GIT_SCHEMES = ("https://", "ssh://", "git@")
_BRANCH_RE = re.compile(r"^[^\x00-\x20~^:?*\\]+$")


class HostingDatabaseCreate(BaseModel):
    engine: str = Field(pattern=r"^(postgresql|mysql)$")
    name: str = Field(min_length=2, max_length=48)
    project_id: UUID | None = None
    storage_mb: int = Field(default=1024, ge=128, le=102400)
    engine_version: str | None = Field(default=None, max_length=32)


class GitSourceCreate(BaseModel):
    repository_url: str = Field(min_length=8, max_length=1000)
    branch: str = Field(default="main", min_length=1, max_length=160)


class ZipSourceRegister(BaseModel):
    original_filename: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0, le=2_147_483_648)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")


def _project(db: Session, tenant_id: UUID, project_id: UUID) -> HostingProject:
    row = db.scalar(select(HostingProject).where(HostingProject.id == project_id, HostingProject.tenant_id == tenant_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Hosted project not found")
    return row


def _audit(db: Session, current: User, tenant_id: UUID, action: str, resource_type: str, resource_id: UUID, metadata: dict | None = None) -> None:
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=current.id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id),
            metadata_json=json.dumps(metadata or {}, sort_keys=True),
        )
    )


def _db_out(row: HostingDatabase) -> dict:
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "project_id": str(row.project_id) if row.project_id else None,
        "node_id": str(row.node_id) if row.node_id else None,
        "engine": row.engine,
        "engine_version": row.engine_version,
        "database_name": row.database_name,
        "username": row.username,
        "host": row.internal_host,
        "port": row.internal_port,
        "storage_mb": row.storage_mb,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _source_out(row: HostingSource) -> dict:
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "project_id": str(row.project_id) if row.project_id else None,
        "source_type": row.source_type,
        "repository_url": row.repository_url,
        "repository_branch": row.repository_branch,
        "repository_commit": row.repository_commit,
        "original_filename": row.original_filename,
        "sha256": row.sha256,
        "size_bytes": row.size_bytes,
        "status": row.status,
        "failure_message": row.failure_message,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _safe_db_name(value: str) -> str:
    name = re.sub(r"[^a-z0-9_]+", "_", value.strip().lower()).strip("_")[:48]
    if not _DB_IDENT_RE.fullmatch(name):
        raise HTTPException(status_code=422, detail="Database name must begin with a letter and contain only lowercase letters, numbers and underscores")
    return name


def _safe_git_source(repository_url: str, branch: str) -> tuple[str, str]:
    repository_url = repository_url.strip()
    branch = branch.strip()
    if not repository_url.startswith(_GIT_SCHEMES):
        raise HTTPException(status_code=422, detail="Repository URL must use HTTPS or SSH Git transport")
    if repository_url.startswith(("https://", "ssh://")):
        parsed = urlsplit(repository_url)
        if not parsed.hostname:
            raise HTTPException(status_code=422, detail="Repository URL must contain a valid host")
        if parsed.password is not None or (repository_url.startswith("https://") and parsed.username is not None):
            raise HTTPException(status_code=422, detail="Do not embed Git credentials in the repository URL; use an encrypted deployment credential")
    elif not re.fullmatch(r"git@[A-Za-z0-9.-]+:[A-Za-z0-9._~/-]+", repository_url):
        raise HTTPException(status_code=422, detail="Invalid SSH Git repository URL")
    if not branch or not _BRANCH_RE.fullmatch(branch) or branch.startswith("-") or branch.endswith((".", "/")) or ".." in branch or "//" in branch:
        raise HTTPException(status_code=422, detail="Invalid Git branch name")
    return repository_url, branch


@router.get("/hosting/runtime-catalog")
def runtime_catalog():
    return {
        "items": RUNTIME_CATALOG,
        "source_types": ["git", "zip"],
        "database_engines": ["postgresql", "mysql"],
        "custom_runtime_policy": "Applications outside managed runtimes can use a reviewed Dockerfile build path.",
    }


@router.get("/tenants/{tenant_id}/hosting/databases")
def list_hosting_databases(
    tenant_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.read", db, current)
    rows = db.scalars(
        select(HostingDatabase)
        .where(HostingDatabase.tenant_id == tenant_id)
        .order_by(HostingDatabase.created_at.desc())
    ).all()
    return {"items": [_db_out(row) for row in rows]}


@router.post("/tenants/{tenant_id}/hosting/databases", status_code=201)
def create_hosting_database(
    tenant_id: UUID,
    payload: HostingDatabaseCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    project = _project(db, tenant_id, payload.project_id) if payload.project_id else None
    database_name = _safe_db_name(payload.name)
    duplicate = db.scalar(
        select(HostingDatabase.id).where(
            HostingDatabase.tenant_id == tenant_id,
            HostingDatabase.engine == payload.engine,
            HostingDatabase.database_name == database_name,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="A database with this name and engine already exists")

    suffix = secrets.token_hex(4)
    username = f"ith_{database_name[:32]}_{suffix}"[:63]
    raw_password = secrets.token_urlsafe(32)
    row = HostingDatabase(
        tenant_id=tenant_id,
        project_id=project.id if project else None,
        node_id=project.node_id if project else None,
        engine=payload.engine,
        engine_version=payload.engine_version,
        database_name=database_name,
        username=username,
        encrypted_password=encrypt_secret(raw_password),
        internal_host=None,
        internal_port=5432 if payload.engine == "postgresql" else 3306,
        storage_mb=payload.storage_mb,
        status="provisioning",
        created_by_user_id=current.id,
    )
    db.add(row)
    db.flush()
    _audit(
        db,
        current,
        tenant_id,
        "hosting.database.create",
        "hosting_database",
        row.id,
        {"engine": row.engine, "database_name": row.database_name, "project_id": str(row.project_id) if row.project_id else None},
    )
    db.commit()
    db.refresh(row)
    result = _db_out(row)
    result["password"] = raw_password
    result["credential_warning"] = "The generated password is returned only on creation. Store it securely; Ithute keeps only an encrypted copy."
    return result


@router.get("/tenants/{tenant_id}/hosting/projects/{project_id}/sources")
def list_project_sources(
    tenant_id: UUID,
    project_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.read", db, current)
    _project(db, tenant_id, project_id)
    rows = db.scalars(
        select(HostingSource)
        .where(HostingSource.tenant_id == tenant_id, HostingSource.project_id == project_id)
        .order_by(HostingSource.created_at.desc())
    ).all()
    return {"items": [_source_out(row) for row in rows]}


@router.post("/tenants/{tenant_id}/hosting/projects/{project_id}/sources/git", status_code=201)
def register_git_source(
    tenant_id: UUID,
    project_id: UUID,
    payload: GitSourceCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    project = _project(db, tenant_id, project_id)
    repository_url, branch = _safe_git_source(payload.repository_url, payload.branch)
    row = HostingSource(
        tenant_id=tenant_id,
        project_id=project.id,
        source_type="git",
        repository_url=repository_url,
        repository_branch=branch,
        status="ready",
        created_by_user_id=current.id,
    )
    db.add(row)
    db.flush()
    project.source_repository = repository_url
    project.source_branch = branch
    _audit(db, current, tenant_id, "hosting.source.git.register", "hosting_source", row.id, {"project_id": str(project.id), "branch": branch})
    db.commit()
    db.refresh(row)
    return _source_out(row)


@router.post("/tenants/{tenant_id}/hosting/projects/{project_id}/sources/zip", status_code=201)
def register_zip_source(
    tenant_id: UUID,
    project_id: UUID,
    payload: ZipSourceRegister,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    project = _project(db, tenant_id, project_id)
    filename = payload.original_filename.strip()
    if not filename.lower().endswith(".zip") or "/" in filename or "\\" in filename or filename in {".", ".."}:
        raise HTTPException(status_code=422, detail="ZIP source filename must be a plain .zip filename")
    object_key = f"hosting/{tenant_id}/{project_id}/{secrets.token_urlsafe(24)}.zip"
    row = HostingSource(
        tenant_id=tenant_id,
        project_id=project.id,
        source_type="zip",
        upload_object_key=object_key,
        original_filename=filename,
        sha256=payload.sha256.lower() if payload.sha256 else None,
        size_bytes=payload.size_bytes,
        status="uploading",
        created_by_user_id=current.id,
    )
    db.add(row)
    db.flush()
    _audit(db, current, tenant_id, "hosting.source.zip.register", "hosting_source", row.id, {"project_id": str(project.id), "filename": filename, "size_bytes": row.size_bytes})
    db.commit()
    db.refresh(row)
    result = _source_out(row)
    result["upload_object_key"] = object_key
    result["next_step"] = "Upload bytes through the isolated hosting upload service; the source remains unavailable to builders until checksum verification marks it ready."
    return result
