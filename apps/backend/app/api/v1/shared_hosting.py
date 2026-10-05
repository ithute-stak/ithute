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

from app.api.deps import get_current_user, require_platform_owner, require_tenant_permission
from app.core.security import decrypt_secret, encrypt_secret, hash_token
from app.db.session import get_db
from app.models import AuditLog, HostingDatabase, HostingDatabaseFailoverAttempt, HostingDatabaseReplica, HostingEnvironmentVariable, HostingNode, HostingNodeAgent, HostingPostgresGroupFailoverAttempt, HostingPostgresReplicationGroup, HostingPostgresReplicationMember, HostingPostgresReplicationStandby, HostingProject, HostingSource, User
from app.services.hosting_metering import database_allocation_allowed, source_allocation_allowed
from app.services.hosting_placement import select_node, sync_tenant_infrastructure_allocation
from app.services.database_replication import build_database_failover_plan
from app.services.postgres_replication_groups import build_postgres_replication_group_plan
from app.services.external_fencing import (
    queue_external_fence_for_database_failover,
    queue_external_fence_for_postgres_group_failover,
)

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


class PostgresReplicationGroupCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    primary_node_id: UUID
    database_ids: list[UUID] = Field(min_length=1, max_length=500)
    standby_node_ids: list[UUID] = Field(default_factory=list, max_length=16)


class PostgresReplicationGroupFailoverRequest(BaseModel):
    standby_id: UUID


class HostingDatabaseCreate(BaseModel):
    engine: str = Field(pattern=r"^(postgresql|mysql)$")
    name: str = Field(min_length=2, max_length=48)
    project_id: UUID | None = None
    storage_mb: int = Field(default=1024, ge=128, le=102400)
    engine_version: str | None = Field(default=None, max_length=32)
    node_id: UUID | None = None


class DatabaseFailoverRequest(BaseModel):
    replica_id: UUID


class DatabaseFailoverAgentStatus(BaseModel):
    token: str = Field(min_length=20, max_length=64)
    success: bool
    message: str | None = Field(default=None, max_length=2000)


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


@router.post("/platform/hosting/postgres-replication-groups", status_code=201)
def create_postgres_replication_group(
    payload: PostgresReplicationGroupCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    database_ids = list(dict.fromkeys(payload.database_ids))
    standby_node_ids = list(dict.fromkeys(payload.standby_node_ids))
    if payload.primary_node_id in standby_node_ids:
        raise HTTPException(status_code=422, detail="Primary node cannot also be a standby")

    primary = db.get(HostingNode, payload.primary_node_id)
    if primary is None:
        raise HTTPException(status_code=404, detail="Primary hosting node not found")

    databases = db.scalars(
        select(HostingDatabase).where(HostingDatabase.id.in_(database_ids))
    ).all()
    if len(databases) != len(database_ids):
        raise HTTPException(status_code=404, detail="One or more PostgreSQL databases were not found")
    if any(row.engine != "postgresql" for row in databases):
        raise HTTPException(status_code=409, detail="Replication groups may contain PostgreSQL databases only")
    if any(row.node_id != primary.id for row in databases):
        raise HTTPException(status_code=409, detail="All replication-group databases must be on the selected primary node")

    existing = db.scalar(
        select(HostingPostgresReplicationMember.database_id)
        .where(HostingPostgresReplicationMember.database_id.in_(database_ids))
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="A selected database already belongs to a PostgreSQL replication group")

    primary_agent = db.get(HostingNodeAgent, primary.id)
    primary_capabilities = {}
    if primary_agent is not None:
        try:
            primary_capabilities = json.loads(primary_agent.capabilities_json or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            primary_capabilities = {}
    primary_postgres = (
        primary_capabilities.get("postgres_physical_replication")
        if isinstance(primary_capabilities, dict) else None
    )
    if (
        not isinstance(primary_postgres, dict)
        or primary_postgres.get("supported") is not True
        or primary_postgres.get("dedicated_cluster") is not True
    ):
        raise HTTPException(status_code=409, detail="Primary node is not a dedicated PostgreSQL physical-replication cluster")

    standby_nodes = []
    for node_id in standby_node_ids:
        node = db.get(HostingNode, node_id)
        if node is None:
            raise HTTPException(status_code=404, detail=f"Standby hosting node {node_id} not found")
        if node.status != "active":
            raise HTTPException(status_code=409, detail=f"Standby hosting node {node.name} is not active")
        already_used = db.scalar(
            select(HostingPostgresReplicationStandby.id).where(
                HostingPostgresReplicationStandby.node_id == node.id
            )
        )
        if already_used is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Standby hosting node {node.name} already belongs to a PostgreSQL physical replication group",
            )
        standby_agent = db.get(HostingNodeAgent, node.id)
        standby_capabilities = {}
        if standby_agent is not None:
            try:
                standby_capabilities = json.loads(standby_agent.capabilities_json or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                standby_capabilities = {}
        standby_postgres = (
            standby_capabilities.get("postgres_physical_replication")
            if isinstance(standby_capabilities, dict) else None
        )
        if (
            not isinstance(standby_postgres, dict)
            or standby_postgres.get("supported") is not True
            or standby_postgres.get("dedicated_cluster") is not True
        ):
            raise HTTPException(
                status_code=409,
                detail=f"Standby hosting node {node.name} is not a dedicated PostgreSQL physical-replication cluster",
            )
        standby_nodes.append(node)

    group = HostingPostgresReplicationGroup(
        name=payload.name.strip(),
        primary_node_id=primary.id,
        status="active",
        created_by_user_id=current.id,
    )
    db.add(group)
    db.flush()
    for database in databases:
        db.add(HostingPostgresReplicationMember(group_id=group.id, database_id=database.id))
    for node in standby_nodes:
        db.add(HostingPostgresReplicationStandby(
            group_id=group.id,
            node_id=node.id,
            status="planned",
            healthy=False,
        ))
    db.flush()
    db.add(AuditLog(
        actor_user_id=current.id,
        action="hosting.postgres_replication_group.create",
        resource_type="hosting_postgres_replication_group",
        resource_id=str(group.id),
        metadata_json=json.dumps({
            "primary_node_id": str(primary.id),
            "database_ids": [str(value) for value in database_ids],
            "standby_node_ids": [str(value) for value in standby_node_ids],
        }, sort_keys=True),
    ))
    db.commit()
    return build_postgres_replication_group_plan(db, group=group)


@router.post("/platform/hosting/postgres-replication-groups/{group_id}/failover", status_code=202)
def request_postgres_replication_group_failover(
    group_id: UUID,
    payload: PostgresReplicationGroupFailoverRequest,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    group = db.scalar(
        select(HostingPostgresReplicationGroup)
        .where(HostingPostgresReplicationGroup.id == group_id)
        .with_for_update()
    )
    if group is None:
        raise HTTPException(status_code=404, detail="PostgreSQL replication group not found")

    standby = db.scalar(
        select(HostingPostgresReplicationStandby).where(
            HostingPostgresReplicationStandby.id == payload.standby_id,
            HostingPostgresReplicationStandby.group_id == group.id,
        )
    )
    if standby is None:
        raise HTTPException(status_code=404, detail="PostgreSQL replication standby not found")

    plan = build_postgres_replication_group_plan(db, group=group)
    evaluation = next(
        (item for item in plan["standbys"] if item["standby_id"] == str(standby.id)),
        None,
    )
    if evaluation is None or not evaluation["eligible"]:
        raise HTTPException(
            status_code=409,
            detail={"message": "Standby is not safe to promote", "evaluation": evaluation},
        )

    active = db.scalar(
        select(HostingPostgresGroupFailoverAttempt.id).where(
            HostingPostgresGroupFailoverAttempt.group_id == group.id,
            HostingPostgresGroupFailoverAttempt.status.in_(
                ["requested", "fence_claimed", "source_fenced", "promote_claimed"]
            ),
        )
    )
    if active is not None:
        raise HTTPException(status_code=409, detail="Replication group already has a failover attempt in progress")

    attempt = HostingPostgresGroupFailoverAttempt(
        group_id=group.id,
        standby_id=standby.id,
        source_node_id=group.primary_node_id,
        target_node_id=standby.node_id,
        status="requested",
        created_by_user_id=current.id,
    )
    db.add(attempt)
    db.flush()
    external_fence = queue_external_fence_for_postgres_group_failover(
        db,
        failover=attempt,
        requested_by_user_id=current.id,
    )
    db.add(AuditLog(
        actor_user_id=current.id,
        action="hosting.postgres_replication_group.failover.request",
        resource_type="hosting_postgres_group_failover",
        resource_id=str(attempt.id),
        metadata_json=json.dumps({
            "group_id": str(group.id),
            "source_node_id": str(group.primary_node_id),
            "target_node_id": str(standby.node_id),
            "standby_id": str(standby.id),
            "external_fence_attempt_id": str(external_fence.id) if external_fence else None,
        }, sort_keys=True),
    ))
    db.commit()
    return {
        "id": str(attempt.id),
        "status": attempt.status,
        "group_id": str(group.id),
        "source_node_id": str(attempt.source_node_id),
        "target_node_id": str(attempt.target_node_id),
    }


@router.post("/hosting/agent/postgres-group-failovers/claim")
def claim_postgres_group_failover(
    x_ithute_hosting_agent: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    agent, node = _agent_from_token(db, x_ithute_hosting_agent)
    agent.last_seen_at = _now()

    source = db.scalar(
        select(HostingPostgresGroupFailoverAttempt)
        .where(
            HostingPostgresGroupFailoverAttempt.source_node_id == node.id,
            HostingPostgresGroupFailoverAttempt.status == "requested",
        )
        .order_by(HostingPostgresGroupFailoverAttempt.created_at.asc())
        .with_for_update(skip_locked=True)
    )
    if source is not None:
        source.status = "fence_claimed"
        source.source_fence_token = secrets.token_urlsafe(32)
        db.commit()
        return {
            "failover": {
                "id": str(source.id),
                "action": "fence_source",
                "token": source.source_fence_token,
                "source_fencing_confirmed": False,
            }
        }

    target = db.scalar(
        select(HostingPostgresGroupFailoverAttempt)
        .where(
            HostingPostgresGroupFailoverAttempt.target_node_id == node.id,
            HostingPostgresGroupFailoverAttempt.status == "source_fenced",
            HostingPostgresGroupFailoverAttempt.source_fenced_at.is_not(None),
        )
        .order_by(HostingPostgresGroupFailoverAttempt.created_at.asc())
        .with_for_update(skip_locked=True)
    )
    if target is not None:
        target.status = "promote_claimed"
        target.target_promote_token = secrets.token_urlsafe(32)
        db.commit()
        return {
            "failover": {
                "id": str(target.id),
                "action": "promote_target",
                "token": target.target_promote_token,
                "source_fencing_confirmed": True,
            }
        }

    db.commit()
    return {"failover": None}


@router.post("/hosting/agent/postgres-group-failovers/{attempt_id}/status")
def report_postgres_group_failover(
    attempt_id: UUID,
    payload: DatabaseFailoverAgentStatus,
    x_ithute_hosting_agent: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    agent, node = _agent_from_token(db, x_ithute_hosting_agent)
    agent.last_seen_at = _now()
    attempt = db.scalar(
        select(HostingPostgresGroupFailoverAttempt)
        .where(HostingPostgresGroupFailoverAttempt.id == attempt_id)
        .with_for_update()
    )
    if attempt is None:
        raise HTTPException(status_code=404, detail="PostgreSQL group failover attempt not found")

    now = _now()
    if attempt.status == "fence_claimed" and attempt.source_node_id == node.id:
        if not attempt.source_fence_token or not secrets.compare_digest(attempt.source_fence_token, payload.token):
            raise HTTPException(status_code=409, detail="Stale PostgreSQL group source-fencing token")
        attempt.source_fence_token = None
        if not payload.success:
            attempt.status = "failed"
            attempt.failure_message = (payload.message or "Source fencing failed").strip()[:2000]
        else:
            attempt.status = "source_fenced"
            attempt.source_fenced_at = now
            attempt.failure_message = None
        db.commit()
        return {"id": str(attempt.id), "status": attempt.status}

    if attempt.status == "promote_claimed" and attempt.target_node_id == node.id:
        if not attempt.target_promote_token or not secrets.compare_digest(attempt.target_promote_token, payload.token):
            raise HTTPException(status_code=409, detail="Stale PostgreSQL group promotion token")
        attempt.target_promote_token = None
        if not payload.success:
            attempt.status = "failed"
            attempt.failure_message = (payload.message or "Group standby promotion failed").strip()[:2000]
            db.commit()
            return {"id": str(attempt.id), "status": attempt.status}
        if attempt.source_fenced_at is None:
            raise HTTPException(status_code=409, detail="Source fencing has not been confirmed")

        group = db.scalar(
            select(HostingPostgresReplicationGroup)
            .where(HostingPostgresReplicationGroup.id == attempt.group_id)
            .with_for_update()
        )
        standby = db.scalar(
            select(HostingPostgresReplicationStandby)
            .where(HostingPostgresReplicationStandby.id == attempt.standby_id)
            .with_for_update()
        )
        if group is None or standby is None:
            raise HTTPException(status_code=409, detail="Replication group failover metadata is incomplete")
        if group.primary_node_id != attempt.source_node_id or standby.node_id != attempt.target_node_id:
            raise HTTPException(status_code=409, detail="Replication group topology changed during failover")

        member_ids = db.scalars(
            select(HostingPostgresReplicationMember.database_id)
            .where(HostingPostgresReplicationMember.group_id == group.id)
        ).all()
        members = db.scalars(
            select(HostingDatabase)
            .where(HostingDatabase.id.in_(member_ids))
            .with_for_update()
        ).all() if member_ids else []
        if len(members) != len(member_ids):
            raise HTTPException(status_code=409, detail="Replication group membership changed during failover")
        if any(row.node_id != attempt.source_node_id for row in members):
            raise HTTPException(status_code=409, detail="One or more member databases moved during failover")

        other_standbys = db.scalars(
            select(HostingPostgresReplicationStandby)
            .where(
                HostingPostgresReplicationStandby.group_id == group.id,
                HostingPostgresReplicationStandby.id != standby.id,
            )
            .with_for_update()
        ).all()

        for database in members:
            database.node_id = attempt.target_node_id
        group.primary_node_id = attempt.target_node_id
        standby.status = "promoted"
        standby.healthy = True
        standby.in_recovery = False
        standby.telemetry_error = None
        for row in other_standbys:
            row.status = "failed"
            row.healthy = False
            row.telemetry_error = "Standby must be reconfigured to follow the newly promoted primary"
        attempt.status = "succeeded"
        attempt.promoted_at = now
        attempt.failure_message = None
        db.add(AuditLog(
            actor_user_id=None,
            action="hosting.postgres_replication_group.failover.complete",
            resource_type="hosting_postgres_group_failover",
            resource_id=str(attempt.id),
            metadata_json=json.dumps({
                "group_id": str(group.id),
                "source_node_id": str(attempt.source_node_id),
                "target_node_id": str(attempt.target_node_id),
                "database_ids": [str(row.id) for row in members],
            }, sort_keys=True),
        ))
        db.commit()
        return {
            "id": str(attempt.id),
            "status": attempt.status,
            "group_id": str(group.id),
            "primary_node_id": str(group.primary_node_id),
            "database_ids": [str(row.id) for row in members],
        }

    raise HTTPException(status_code=409, detail="Group failover action is not claimable by this hosting node")


@router.get("/platform/hosting/postgres-replication-groups/{group_id}/failover-plan")
def postgres_replication_group_failover_plan(
    group_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    group = db.get(HostingPostgresReplicationGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="PostgreSQL replication group not found")
    return build_postgres_replication_group_plan(db, group=group)


@router.get("/tenants/{tenant_id}/hosting/databases/{database_id}/failover-plan")
def database_failover_plan(
    tenant_id: UUID,
    database_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.read", db, current)
    database = _database(db, tenant_id, database_id)
    return build_database_failover_plan(db, database=database)


@router.post("/tenants/{tenant_id}/hosting/databases/{database_id}/failover", status_code=202)
def request_database_failover(
    tenant_id: UUID,
    database_id: UUID,
    payload: DatabaseFailoverRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    database = _database(db, tenant_id, database_id, lock=True)
    grouped = db.scalar(
        select(HostingPostgresReplicationMember.group_id).where(
            HostingPostgresReplicationMember.database_id == database.id
        )
    )
    if grouped is not None:
        raise HTTPException(
            status_code=409,
            detail="Database belongs to a physical PostgreSQL replication group; use group failover",
        )
    if database.engine != "postgresql":
        raise HTTPException(status_code=409, detail="Controlled failover execution currently supports PostgreSQL only")
    if database.node_id is None:
        raise HTTPException(status_code=409, detail="Database primary node is unavailable")

    replica = db.scalar(
        select(HostingDatabaseReplica).where(
            HostingDatabaseReplica.id == payload.replica_id,
            HostingDatabaseReplica.database_id == database.id,
        )
    )
    if replica is None or replica.node_id is None:
        raise HTTPException(status_code=404, detail="Database replica not found")

    plan = build_database_failover_plan(db, database=database)
    evaluation = next((item for item in plan["replicas"] if item["replica_id"] == str(replica.id)), None)
    if evaluation is None or not evaluation["eligible"]:
        raise HTTPException(status_code=409, detail={"message": "Replica is not safe to promote", "evaluation": evaluation})

    active = db.scalar(
        select(HostingDatabaseFailoverAttempt.id).where(
            HostingDatabaseFailoverAttempt.database_id == database.id,
            HostingDatabaseFailoverAttempt.status.in_(["requested", "fence_claimed", "source_fenced", "promote_claimed"]),
        )
    )
    if active is not None:
        raise HTTPException(status_code=409, detail="Database already has a failover attempt in progress")

    attempt = HostingDatabaseFailoverAttempt(
        database_id=database.id,
        replica_id=replica.id,
        source_node_id=database.node_id,
        target_node_id=replica.node_id,
        status="requested",
        created_by_user_id=current.id,
    )
    db.add(attempt)
    db.flush()
    external_fence = queue_external_fence_for_database_failover(
        db,
        failover=attempt,
        requested_by_user_id=current.id,
    )
    _audit(
        db, current, tenant_id, "hosting.database.failover.request",
        "hosting_database_failover_attempt", attempt.id,
        {
            "database_id": str(database.id),
            "source_node_id": str(database.node_id),
            "target_node_id": str(replica.node_id),
            "external_fence_attempt_id": str(external_fence.id) if external_fence else None,
        },
    )
    db.commit()
    return {
        "id": str(attempt.id),
        "status": attempt.status,
        "database_id": str(database.id),
        "source_node_id": str(attempt.source_node_id),
        "target_node_id": str(attempt.target_node_id),
    }


@router.post("/hosting/agent/database-failovers/claim")
def claim_database_failover(
    x_ithute_hosting_agent: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    agent, node = _agent_from_token(db, x_ithute_hosting_agent)
    agent.last_seen_at = _now()

    source = db.scalar(
        select(HostingDatabaseFailoverAttempt)
        .where(
            HostingDatabaseFailoverAttempt.source_node_id == node.id,
            HostingDatabaseFailoverAttempt.status == "requested",
        )
        .order_by(HostingDatabaseFailoverAttempt.created_at.asc())
        .with_for_update(skip_locked=True)
    )
    if source is not None:
        source.status = "fence_claimed"
        source.source_fence_token = secrets.token_urlsafe(32)
        db.commit()
        return {
            "failover": {
                "id": str(source.id),
                "action": "fence_source",
                "token": source.source_fence_token,
                "source_fencing_confirmed": False,
            }
        }

    target = db.scalar(
        select(HostingDatabaseFailoverAttempt)
        .where(
            HostingDatabaseFailoverAttempt.target_node_id == node.id,
            HostingDatabaseFailoverAttempt.status == "source_fenced",
            HostingDatabaseFailoverAttempt.source_fenced_at.is_not(None),
        )
        .order_by(HostingDatabaseFailoverAttempt.created_at.asc())
        .with_for_update(skip_locked=True)
    )
    if target is not None:
        target.status = "promote_claimed"
        target.target_promote_token = secrets.token_urlsafe(32)
        db.commit()
        return {
            "failover": {
                "id": str(target.id),
                "action": "promote_target",
                "token": target.target_promote_token,
                "source_fencing_confirmed": True,
            }
        }

    db.commit()
    return {"failover": None}


@router.post("/hosting/agent/database-failovers/{attempt_id}/status")
def report_database_failover(
    attempt_id: UUID,
    payload: DatabaseFailoverAgentStatus,
    x_ithute_hosting_agent: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    agent, node = _agent_from_token(db, x_ithute_hosting_agent)
    agent.last_seen_at = _now()
    attempt = db.scalar(
        select(HostingDatabaseFailoverAttempt)
        .where(HostingDatabaseFailoverAttempt.id == attempt_id)
        .with_for_update()
    )
    if attempt is None:
        raise HTTPException(status_code=404, detail="Database failover attempt not found")

    now = _now()
    if attempt.status == "fence_claimed" and attempt.source_node_id == node.id:
        if not attempt.source_fence_token or not secrets.compare_digest(attempt.source_fence_token, payload.token):
            raise HTTPException(status_code=409, detail="Stale database source-fencing token")
        attempt.source_fence_token = None
        if not payload.success:
            attempt.status = "failed"
            attempt.failure_message = (payload.message or "Source fencing failed").strip()[:2000]
        else:
            attempt.status = "source_fenced"
            attempt.source_fenced_at = now
            attempt.failure_message = None
        db.commit()
        return {"id": str(attempt.id), "status": attempt.status}

    if attempt.status == "promote_claimed" and attempt.target_node_id == node.id:
        if not attempt.target_promote_token or not secrets.compare_digest(attempt.target_promote_token, payload.token):
            raise HTTPException(status_code=409, detail="Stale database promotion token")
        attempt.target_promote_token = None
        if not payload.success:
            attempt.status = "failed"
            attempt.failure_message = (payload.message or "Replica promotion failed").strip()[:2000]
            db.commit()
            return {"id": str(attempt.id), "status": attempt.status}

        if attempt.source_fenced_at is None:
            raise HTTPException(status_code=409, detail="Source fencing has not been confirmed")
        database = db.get(HostingDatabase, attempt.database_id)
        replica = db.get(HostingDatabaseReplica, attempt.replica_id)
        if database is None or replica is None:
            raise HTTPException(status_code=409, detail="Database failover metadata is incomplete")
        database.node_id = attempt.target_node_id
        replica.role = "primary"
        replica.status = "ready"
        replica.healthy = True
        attempt.status = "succeeded"
        attempt.promoted_at = now
        attempt.failure_message = None
        _audit(
            db, None, database.tenant_id, "hosting.database.failover.complete",
            "hosting_database_failover_attempt", attempt.id,
            {"database_id": str(database.id), "source_node_id": str(attempt.source_node_id), "target_node_id": str(attempt.target_node_id)},
        )
        db.commit()
        return {"id": str(attempt.id), "status": attempt.status, "primary_node_id": str(database.node_id)}

    raise HTTPException(status_code=409, detail="Failover action is not claimable by this hosting node")


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
    if placement["infrastructure_server_id"]:
        sync_tenant_infrastructure_allocation(
            db,
            tenant_id=tenant_id,
            server_id=UUID(placement["infrastructure_server_id"]),
            actor_user_id=current.id,
        )
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
