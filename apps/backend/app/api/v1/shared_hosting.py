from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timezone
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_tenant_permission
from app.core.security import decrypt_secret, encrypt_secret, hash_token
from app.db.session import get_db
from app.models import AuditLog, HostingDatabase, HostingEnvironmentVariable, HostingNode, HostingNodeAgent, HostingProject, HostingSource, User
from app.services.hosting_metering import database_allocation_allowed, source_allocation_allowed
from app.services.hosting_placement import select_node, sync_tenant_infrastructure_allocation

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
_DATABASE_OPERATIONS = {"provision", "rotate", "suspend", "resume", "delete"}


class HostingDatabaseCreate(BaseModel):
    engine: str = Field(pattern=r"^(postgresql|mysql)$")
    name: str = Field(min_length=2, max_length=48)
    project_id: UUID | None = None
    storage_mb: int = Field(default=1024, ge=128, le=102400)
    engine_version: str | None = Field(default=None, max_length=32)
    node_id: UUID | None = None


class DatabaseAgentStatus(BaseModel):
    success: bool
    host: str | None = Field(default=None, max_length=253)
    port: int | None = Field(default=None, ge=1, le=65535)
    engine_version: str | None = Field(default=None, max_length=32)
    message: str | None = Field(default=None, max_length=2000)


class GitSourceCreate(BaseModel):
    repository_url: str = Field(min_length=8, max_length=1000)
    branch: str = Field(default="main", min_length=1, max_length=160)


class ZipSourceRegister(BaseModel):
    original_filename: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0, le=2_147_483_648)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _project(db: Session, tenant_id: UUID, project_id: UUID) -> HostingProject:
    row = db.scalar(select(HostingProject).where(HostingProject.id == project_id, HostingProject.tenant_id == tenant_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Hosted project not found")
    return row


def _database(db: Session, tenant_id: UUID, database_id: UUID, *, lock: bool = False) -> HostingDatabase:
    query = select(HostingDatabase).where(HostingDatabase.id == database_id, HostingDatabase.tenant_id == tenant_id)
    if lock:
        query = query.with_for_update()
    row = db.scalar(query)
    if row is None:
        raise HTTPException(status_code=404, detail="Hosted database not found")
    return row


def _audit(db: Session, current: User | None, tenant_id: UUID, action: str, resource_type: str, resource_id: UUID, metadata: dict | None = None) -> None:
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=current.id if current else None,
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
        "operation": row.operation,
        "failure_message": row.failure_message,
        "claimed_at": row.claimed_at.isoformat() if row.claimed_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
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


def _queue_database_operation(row: HostingDatabase, operation: str) -> None:
    if operation not in _DATABASE_OPERATIONS:
        raise RuntimeError("Unsupported internal database operation")
    row.operation = operation
    row.claimed_at = None
    row.completed_at = None
    row.failure_message = None
    row.status = "deleting" if operation == "delete" else "queued"


def _agent_from_token(db: Session, token: str | None) -> tuple[HostingNodeAgent, HostingNode]:
    raw = (token or "").strip()
    if not raw or not raw.startswith("ith_host_"):
        raise HTTPException(status_code=401, detail="Hosting node agent credential required")
    agent = db.scalar(select(HostingNodeAgent).where(HostingNodeAgent.token_hash == hash_token(raw)))
    if agent is None:
        raise HTTPException(status_code=401, detail="Invalid hosting node agent credential")
    node = db.get(HostingNode, agent.node_id)
    if node is None or node.status == "offline":
        raise HTTPException(status_code=403, detail="Hosting node is unavailable")
    return agent, node


@router.get("/hosting/runtime-catalog")
def runtime_catalog():
    return {
        "items": RUNTIME_CATALOG,
        "source_types": ["git", "zip"],
        "database_engines": ["postgresql", "mysql"],
        "custom_runtime_policy": "Applications outside managed runtimes can use a reviewed Dockerfile build path.",
    }


@router.get("/tenants/{tenant_id}/hosting/databases")
def list_hosting_databases(tenant_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "hosting.read", db, current)
    rows = db.scalars(select(HostingDatabase).where(HostingDatabase.tenant_id == tenant_id).order_by(HostingDatabase.created_at.desc())).all()
    return {"items": [_db_out(row) for row in rows]}


@router.post("/tenants/{tenant_id}/hosting/databases", status_code=201)
def create_hosting_database(tenant_id: UUID, payload: HostingDatabaseCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    allowed, reason, _ = database_allocation_allowed(db, tenant_id, payload.storage_mb)
    if not allowed:
        raise HTTPException(status_code=402, detail=reason)
    project = _project(db, tenant_id, payload.project_id) if payload.project_id else None
    if payload.node_id is not None and not current.is_platform_owner:
        raise HTTPException(status_code=403, detail="Only the platform owner can override automatic database placement")
    if project is not None and project.node_id is not None:
        if payload.node_id is not None and payload.node_id != project.node_id:
            raise HTTPException(status_code=409, detail="A project database must remain on the same hosting node as its application")
        node, placement = select_node(
            db,
            workload="database",
            storage_mb=payload.storage_mb,
            database_engine=payload.engine,
            preferred_node_id=project.node_id,
        tenant_id=tenant_id,
        )
        placement_mode = "project_colocation"
    else:
        node, placement = select_node(
            db,
            workload="database",
            storage_mb=payload.storage_mb,
            database_engine=payload.engine,
            preferred_node_id=payload.node_id if current.is_platform_owner else None,
        tenant_id=tenant_id,
        )
        placement_mode = "manual_override" if payload.node_id else "automatic"
    database_name = _safe_db_name(payload.name)
    duplicate = db.scalar(select(HostingDatabase.id).where(HostingDatabase.tenant_id == tenant_id, HostingDatabase.engine == payload.engine, HostingDatabase.database_name == database_name))
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="A database with this name and engine already exists")

    suffix = secrets.token_hex(4)
    username = f"ith_{database_name[:32]}_{suffix}"[:63]
    raw_password = secrets.token_urlsafe(32)
    row = HostingDatabase(
        tenant_id=tenant_id,
        project_id=project.id if project else None,
        node_id=node.id,
        engine=payload.engine,
        engine_version=payload.engine_version,
        database_name=database_name,
        username=username,
        encrypted_password=encrypt_secret(raw_password),
        pending_encrypted_password=None,
        internal_host=None,
        internal_port=5432 if payload.engine == "postgresql" else 3306,
        storage_mb=payload.storage_mb,
        status="queued",
        operation="provision",
        created_by_user_id=current.id,
    )
    db.add(row)
    db.flush()
    _audit(db, current, tenant_id, "hosting.database.create", "hosting_database", row.id, {"engine": row.engine, "database_name": row.database_name, "project_id": str(row.project_id) if row.project_id else None, "node_id": str(node.id), "storage_mb": row.storage_mb, "placement_mode": placement_mode, "placement_score": placement["score"], "placement_server_id": placement["infrastructure_server_id"]})
    db.commit()
    db.refresh(row)
    result = _db_out(row)
    result["password"] = raw_password
    result["credential_warning"] = "The generated password is returned only on creation. Store it securely; Ithute keeps only an encrypted copy."
    return result


@router.post("/tenants/{tenant_id}/hosting/databases/{database_id}/rotate-password")
def rotate_database_password(tenant_id: UUID, database_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    row = _database(db, tenant_id, database_id, lock=True)
    if row.status != "ready" or row.operation != "none":
        raise HTTPException(status_code=409, detail="Database password can be rotated only while the database is ready and idle")
    raw_password = secrets.token_urlsafe(32)
    row.pending_encrypted_password = encrypt_secret(raw_password)
    _queue_database_operation(row, "rotate")
    _audit(db, current, tenant_id, "hosting.database.rotate.queue", "hosting_database", row.id)
    db.commit()
    result = _db_out(row)
    result["password"] = raw_password
    result["credential_warning"] = "This replacement password is shown once. It becomes the active stored credential only after the hosting node confirms the rotation."
    return result


@router.post("/tenants/{tenant_id}/hosting/databases/{database_id}/suspend")
def suspend_database(tenant_id: UUID, database_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    row = _database(db, tenant_id, database_id, lock=True)
    if row.status != "ready" or row.operation != "none":
        raise HTTPException(status_code=409, detail="Only a ready idle database can be suspended")
    _queue_database_operation(row, "suspend")
    _audit(db, current, tenant_id, "hosting.database.suspend.queue", "hosting_database", row.id)
    db.commit()
    return _db_out(row)


@router.post("/tenants/{tenant_id}/hosting/databases/{database_id}/resume")
def resume_database(tenant_id: UUID, database_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    row = _database(db, tenant_id, database_id, lock=True)
    if row.status != "suspended" or row.operation != "none":
        raise HTTPException(status_code=409, detail="Only a suspended idle database can be resumed")
    _queue_database_operation(row, "resume")
    _audit(db, current, tenant_id, "hosting.database.resume.queue", "hosting_database", row.id)
    db.commit()
    return _db_out(row)


@router.delete("/tenants/{tenant_id}/hosting/databases/{database_id}", status_code=202)
def delete_hosting_database(tenant_id: UUID, database_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    row = _database(db, tenant_id, database_id, lock=True)
    if row.status in {"queued", "working", "deleting"}:
        raise HTTPException(status_code=409, detail="Database already has an operation in progress")
    _queue_database_operation(row, "delete")
    _audit(db, current, tenant_id, "hosting.database.delete.queue", "hosting_database", row.id)
    db.commit()
    return {"accepted": True, "database": _db_out(row)}


@router.post("/hosting/agent/databases/claim")
def claim_database_operation(x_ithute_hosting_agent: str | None = Header(default=None), db: Session = Depends(get_db)):
    agent, node = _agent_from_token(db, x_ithute_hosting_agent)
    agent.last_seen_at = _now()
    row = db.scalar(
        select(HostingDatabase)
        .where(HostingDatabase.node_id == node.id, HostingDatabase.operation != "none", HostingDatabase.status.in_(["queued", "deleting"]))
        .order_by(HostingDatabase.created_at.asc())
        .with_for_update(skip_locked=True)
    )
    if row is None:
        db.commit()
        return {"database": None}
    encrypted_password = row.pending_encrypted_password if row.operation == "rotate" else row.encrypted_password
    if row.operation == "rotate" and not encrypted_password:
        row.status = "failed"
        row.operation = "none"
        row.failure_message = "Pending rotation credential is missing"
        row.completed_at = _now()
        db.commit()
        raise HTTPException(status_code=500, detail="Database rotation credential could not be prepared")
    try:
        password = decrypt_secret(encrypted_password)
    except ValueError as exc:
        row.status = "failed"
        row.operation = "none"
        row.failure_message = "Database credential could not be decrypted"
        row.completed_at = _now()
        if row.pending_encrypted_password is not None:
            row.pending_encrypted_password = None
        db.commit()
        raise HTTPException(status_code=500, detail="Database credential could not be prepared") from exc
    row.status = "working"
    row.claimed_at = _now()
    operation = row.operation
    db.commit()
    return {
        "database": {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "project_id": str(row.project_id) if row.project_id else None,
            "operation": operation,
            "engine": row.engine,
            "engine_version": row.engine_version,
            "database_name": row.database_name,
            "username": row.username,
            "password": password,
            "storage_mb": row.storage_mb,
            "expected_port": row.internal_port,
        }
    }


@router.post("/hosting/agent/databases/{database_id}/status")
def report_database_operation(database_id: UUID, payload: DatabaseAgentStatus, x_ithute_hosting_agent: str | None = Header(default=None), db: Session = Depends(get_db)):
    agent, node = _agent_from_token(db, x_ithute_hosting_agent)
    agent.last_seen_at = _now()
    row = db.scalar(select(HostingDatabase).where(HostingDatabase.id == database_id, HostingDatabase.node_id == node.id).with_for_update())
    if row is None:
        raise HTTPException(status_code=404, detail="Database operation not found for this hosting node")
    if row.status != "working" or row.operation == "none":
        raise HTTPException(status_code=409, detail="Database does not have a claimed operation")
    operation = row.operation
    now = _now()
    if not payload.success:
        row.status = "failed"
        row.operation = "none"
        row.failure_message = (payload.message or "Hosting node reported database operation failure").strip()[:2000]
        row.completed_at = now
        if operation == "rotate":
            row.pending_encrypted_password = None
        _audit(db, None, row.tenant_id, f"hosting.database.{operation}.failed", "hosting_database", row.id, {"node_id": str(node.id), "message": row.failure_message})
        db.commit()
        db.refresh(row)
        return _db_out(row)

    if operation == "delete":
        tenant_id = row.tenant_id
        resource_id = row.id
        _audit(db, None, tenant_id, "hosting.database.delete.complete", "hosting_database", resource_id, {"node_id": str(node.id)})
        db.delete(row)
        db.commit()
        return {"deleted": True, "id": str(resource_id)}

    if operation == "rotate":
        if row.pending_encrypted_password is None:
            row.status = "failed"
            row.operation = "none"
            row.failure_message = "Hosting node completed rotation but pending credential is missing"
            row.completed_at = now
            _audit(db, None, row.tenant_id, "hosting.database.rotate.failed", "hosting_database", row.id, {"node_id": str(node.id), "message": row.failure_message})
            db.commit()
            db.refresh(row)
            return _db_out(row)
        row.encrypted_password = row.pending_encrypted_password
        row.pending_encrypted_password = None

    row.internal_host = payload.host or row.internal_host
    row.internal_port = payload.port or row.internal_port
    row.engine_version = payload.engine_version or row.engine_version
    row.status = "suspended" if operation == "suspend" else "ready"
    row.operation = "none"
    row.failure_message = None
    row.completed_at = now

    # Automatic provisioning can create a project-scoped database before the
    # hosting agent knows its final internal host. Once provisioning completes,
    # reconcile connection metadata into the existing encrypted environment
    # store so the next application deployment receives usable credentials.
    if row.project_id and row.status == "ready" and row.internal_host:
        try:
            password = decrypt_secret(row.encrypted_password)
        except ValueError:
            password = None
        values = {
            "DATABASE_HOST": (row.internal_host, False),
            "DATABASE_PORT": (str(row.internal_port), False),
            "DATABASE_NAME": (row.database_name, False),
            "DATABASE_USER": (row.username, True),
        }
        if password is not None:
            scheme = "postgresql" if row.engine == "postgresql" else "mysql"
            values["DATABASE_PASSWORD"] = (password, True)
            values["DATABASE_URL"] = (
                f"{scheme}://{row.username}:{password}@{row.internal_host}:{row.internal_port}/{row.database_name}",
                True,
            )
        for key, (value, secret) in values.items():
            env = db.scalar(select(HostingEnvironmentVariable).where(
                HostingEnvironmentVariable.project_id == row.project_id,
                HostingEnvironmentVariable.key == key,
            ))
            encrypted = encrypt_secret(value)
            if env is None:
                env = HostingEnvironmentVariable(
                    project_id=row.project_id,
                    key=key,
                    encrypted_value=encrypted,
                    is_secret=secret,
                    created_by_user_id=row.created_by_user_id,
                    updated_by_user_id=row.created_by_user_id,
                )
                db.add(env)
            else:
                env.encrypted_value = encrypted
                env.is_secret = secret
                env.updated_by_user_id = row.created_by_user_id

    _audit(db, None, row.tenant_id, f"hosting.database.{operation}.complete", "hosting_database", row.id, {"node_id": str(node.id), "host": row.internal_host, "port": row.internal_port})
    db.commit()
    db.refresh(row)
    return _db_out(row)


@router.get("/tenants/{tenant_id}/hosting/projects/{project_id}/sources")
def list_project_sources(tenant_id: UUID, project_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "hosting.read", db, current)
    _project(db, tenant_id, project_id)
    rows = db.scalars(select(HostingSource).where(HostingSource.tenant_id == tenant_id, HostingSource.project_id == project_id).order_by(HostingSource.created_at.desc())).all()
    return {"items": [_source_out(row) for row in rows]}


@router.post("/tenants/{tenant_id}/hosting/projects/{project_id}/sources/git", status_code=201)
def register_git_source(tenant_id: UUID, project_id: UUID, payload: GitSourceCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    project = _project(db, tenant_id, project_id)
    repository_url, branch = _safe_git_source(payload.repository_url, payload.branch)
    row = HostingSource(tenant_id=tenant_id, project_id=project.id, source_type="git", repository_url=repository_url, repository_branch=branch, status="ready", created_by_user_id=current.id)
    db.add(row)
    db.flush()
    project.source_repository = repository_url
    project.source_branch = branch
    _audit(db, current, tenant_id, "hosting.source.git.register", "hosting_source", row.id, {"project_id": str(project.id), "branch": branch})
    db.commit()
    db.refresh(row)
    return _source_out(row)


@router.post("/tenants/{tenant_id}/hosting/projects/{project_id}/sources/zip", status_code=201)
def register_zip_source(tenant_id: UUID, project_id: UUID, payload: ZipSourceRegister, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    project = _project(db, tenant_id, project_id)
    filename = payload.original_filename.strip()
    if not filename.lower().endswith(".zip") or "/" in filename or "\\" in filename or filename in {".", ".."}:
        raise HTTPException(status_code=422, detail="ZIP source filename must be a plain .zip filename")
    allowed, reason, _ = source_allocation_allowed(db, tenant_id, payload.size_bytes)
    if not allowed:
        raise HTTPException(status_code=402, detail=reason)
    object_key = f"hosting/{tenant_id}/{project_id}/{secrets.token_urlsafe(24)}.zip"
    row = HostingSource(tenant_id=tenant_id, project_id=project.id, source_type="zip", upload_object_key=object_key, original_filename=filename, sha256=payload.sha256.lower() if payload.sha256 else None, size_bytes=payload.size_bytes, status="uploading", created_by_user_id=current.id)
    db.add(row)
    db.flush()
    _audit(db, current, tenant_id, "hosting.source.zip.register", "hosting_source", row.id, {"project_id": str(project.id), "filename": filename, "size_bytes": row.size_bytes})
    db.commit()
    db.refresh(row)
    result = _source_out(row)
    result["upload_object_key"] = object_key
    result["next_step"] = "Upload bytes through the isolated hosting upload service; the source remains unavailable to builders until checksum verification marks it ready."
    return result
