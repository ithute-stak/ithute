from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_tenant_permission
from app.api.v1.shared_hosting import _safe_git_source
from app.core.security import encrypt_secret
from app.db.session import get_db
from app.models import AuditLog, HostingProject, HostingSource, HostingSourceCredential, User

router = APIRouter(tags=["hosting-source-credentials"])


class GitCredentialCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    provider: str = Field(pattern=r"^(github|gitlab|bitbucket|generic)$")
    auth_type: str = Field(pattern=r"^(https_token|ssh_key)$")
    username: str | None = Field(default=None, max_length=255)
    secret: str = Field(min_length=12, max_length=20000)


class PrivateGitSourceCreate(BaseModel):
    repository_url: str = Field(min_length=8, max_length=1000)
    branch: str = Field(default="main", min_length=1, max_length=160)
    credential_id: UUID


def _project(db: Session, tenant_id: UUID, project_id: UUID) -> HostingProject:
    row = db.scalar(select(HostingProject).where(HostingProject.id == project_id, HostingProject.tenant_id == tenant_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Hosted project not found")
    return row


def _credential(db: Session, tenant_id: UUID, project_id: UUID, credential_id: UUID) -> HostingSourceCredential:
    row = db.scalar(
        select(HostingSourceCredential).where(
            HostingSourceCredential.id == credential_id,
            HostingSourceCredential.tenant_id == tenant_id,
            HostingSourceCredential.project_id == project_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Git credential not found for this project")
    return row


def _credential_out(row: HostingSourceCredential) -> dict:
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "project_id": str(row.project_id),
        "name": row.name,
        "provider": row.provider,
        "auth_type": row.auth_type,
        "username": row.username,
        "status": row.status,
        "has_secret": True,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _validate_secret(auth_type: str, secret: str) -> str:
    value = secret.strip()
    if "\x00" in value:
        raise HTTPException(status_code=422, detail="Git credential contains an invalid NUL character")
    if auth_type == "ssh_key":
        if "PRIVATE KEY-----" not in value or not value.startswith("-----BEGIN ") or not value.endswith("-----"):
            raise HTTPException(status_code=422, detail="SSH credential must be a PEM/OpenSSH private key")
    elif any(ch in value for ch in "\r\n"):
        raise HTTPException(status_code=422, detail="HTTPS token must be a single-line secret")
    return value


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


@router.get("/tenants/{tenant_id}/hosting/projects/{project_id}/source-credentials")
def list_source_credentials(tenant_id: UUID, project_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "hosting.read", db, current)
    _project(db, tenant_id, project_id)
    rows = db.scalars(
        select(HostingSourceCredential)
        .where(HostingSourceCredential.tenant_id == tenant_id, HostingSourceCredential.project_id == project_id)
        .order_by(HostingSourceCredential.created_at.desc())
    ).all()
    return {"items": [_credential_out(row) for row in rows]}


@router.post("/tenants/{tenant_id}/hosting/projects/{project_id}/source-credentials", status_code=201)
def create_source_credential(tenant_id: UUID, project_id: UUID, payload: GitCredentialCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    project = _project(db, tenant_id, project_id)
    secret = _validate_secret(payload.auth_type, payload.secret)
    username = payload.username.strip() if payload.username else None
    if payload.auth_type == "https_token" and payload.provider == "generic" and not username:
        raise HTTPException(status_code=422, detail="Generic HTTPS Git credentials require a username")
    row = HostingSourceCredential(
        tenant_id=tenant_id,
        project_id=project.id,
        name=payload.name.strip(),
        provider=payload.provider,
        auth_type=payload.auth_type,
        username=username,
        encrypted_secret=encrypt_secret(secret),
        status="active",
        created_by_user_id=current.id,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A Git credential with this name already exists for the project") from exc
    _audit(db, current, tenant_id, "hosting.source_credential.create", "hosting_source_credential", row.id, {"project_id": str(project.id), "provider": row.provider, "auth_type": row.auth_type})
    db.commit()
    db.refresh(row)
    return _credential_out(row)


@router.delete("/tenants/{tenant_id}/hosting/projects/{project_id}/source-credentials/{credential_id}", status_code=204)
def revoke_source_credential(tenant_id: UUID, project_id: UUID, credential_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    row = _credential(db, tenant_id, project_id, credential_id)
    if row.status != "revoked":
        row.status = "revoked"
        _audit(db, current, tenant_id, "hosting.source_credential.revoke", "hosting_source_credential", row.id, {"project_id": str(project_id)})
        db.commit()


@router.post("/tenants/{tenant_id}/hosting/projects/{project_id}/sources/private-git", status_code=201)
def register_private_git_source(tenant_id: UUID, project_id: UUID, payload: PrivateGitSourceCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    project = _project(db, tenant_id, project_id)
    credential = _credential(db, tenant_id, project_id, payload.credential_id)
    if credential.status != "active":
        raise HTTPException(status_code=409, detail="Git credential is revoked")
    repository_url, branch = _safe_git_source(payload.repository_url, payload.branch)
    row = HostingSource(
        tenant_id=tenant_id,
        project_id=project.id,
        credential_id=credential.id,
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
    _audit(db, current, tenant_id, "hosting.source.private_git.register", "hosting_source", row.id, {"project_id": str(project.id), "credential_id": str(credential.id), "provider": credential.provider, "branch": branch})
    db.commit()
    db.refresh(row)
    return {
        "id": str(row.id),
        "project_id": str(project.id),
        "source_type": "git",
        "repository_url": row.repository_url,
        "repository_branch": row.repository_branch,
        "credential_id": str(credential.id),
        "credential_name": credential.name,
        "credential_provider": credential.provider,
        "status": row.status,
    }
