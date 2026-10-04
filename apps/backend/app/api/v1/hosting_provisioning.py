from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_tenant_permission
from app.api.v1.shared_hosting import _safe_db_name, _safe_git_source
from app.core.security import encrypt_secret
from app.db.session import get_db
from app.models import (
    AuditLog,
    Domain,
    DomainStatus,
    EdgeApplication,
    EdgeOrigin,
    EdgeRouteDeployment,
    HostingBuild,
    HostingDatabase,
    HostingDeployment,
    HostingEnvironmentVariable,
    HostingProject,
    HostingProvisioningWorkflow,
    HostingSource,
    User,
)
from app.services.hosting_metering import database_allocation_allowed
from app.services.hosting_placement import select_node
from app.services.hosting_edge_handoff import HostingOriginError, reconcile_project_edge

router = APIRouter(tags=["hosting-provisioning"])
_ENV_KEY_RE = re.compile(r"^[A-Z_][A-Z0-9_]{0,127}$")


class ProvisionRequest(BaseModel):
    database_engine: str | None = Field(default=None, pattern=r"^(postgresql|mysql)$")
    database_name: str | None = Field(default=None, max_length=48)
    database_storage_mb: int = Field(default=1024, ge=128, le=102400)
    environment: dict[str, str] = Field(default_factory=dict)
    create_edge_application: bool = True


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(db: Session, current: User, workflow: HostingProvisioningWorkflow, action: str, metadata: dict | None = None) -> None:
    db.add(AuditLog(
        tenant_id=workflow.tenant_id,
        actor_user_id=current.id,
        action=action,
        resource_type="hosting_provisioning_workflow",
        resource_id=str(workflow.id),
        metadata_json=json.dumps(metadata or {}, sort_keys=True),
    ))


def _upsert_env(db: Session, project_id: UUID, key: str, value: str, current: User, *, secret: bool = True) -> None:
    normalized = key.strip().upper()
    if not _ENV_KEY_RE.fullmatch(normalized):
        raise HTTPException(status_code=422, detail=f"Invalid environment key: {key}")
    if len(value) > 10000:
        raise HTTPException(status_code=422, detail=f"Environment value for {normalized} is too large")
    row = db.scalar(select(HostingEnvironmentVariable).where(
        HostingEnvironmentVariable.project_id == project_id,
        HostingEnvironmentVariable.key == normalized,
    ))
    encrypted = encrypt_secret(value)
    if row is None:
        db.add(HostingEnvironmentVariable(
            project_id=project_id,
            key=normalized,
            encrypted_value=encrypted,
            is_secret=secret,
            created_by_user_id=current.id,
            updated_by_user_id=current.id,
        ))
    else:
        row.encrypted_value = encrypted
        row.is_secret = secret
        row.updated_by_user_id = current.id


def _source(db: Session, project: HostingProject, current: User) -> HostingSource:
    source = db.scalar(
        select(HostingSource)
        .where(HostingSource.project_id == project.id, HostingSource.status == "ready")
        .order_by(HostingSource.created_at.desc())
    )
    if source is not None:
        return source
    if not project.source_repository:
        raise HTTPException(status_code=409, detail="Add a Git or verified ZIP source before starting automatic provisioning")
    repository_url, branch = _safe_git_source(project.source_repository, project.source_branch or "main")
    source = HostingSource(
        tenant_id=project.tenant_id,
        project_id=project.id,
        source_type="git",
        repository_url=repository_url,
        repository_branch=branch,
        status="ready",
        created_by_user_id=current.id,
    )
    db.add(source)
    db.flush()
    return source


def _edge_application(db: Session, project: HostingProject) -> EdgeApplication | None:
    if not project.hostname or project.domain_id is None:
        return None
    return db.scalar(select(EdgeApplication).where(
        EdgeApplication.tenant_id == project.tenant_id,
        EdgeApplication.hostname == project.hostname,
    ))


def _stage_out(db: Session, workflow: HostingProvisioningWorkflow) -> dict:
    project = db.get(HostingProject, workflow.project_id)
    source = db.get(HostingSource, workflow.source_id) if workflow.source_id else None
    database = db.get(HostingDatabase, workflow.database_id) if workflow.database_id else None
    build = db.get(HostingBuild, workflow.build_id) if workflow.build_id else None
    deployment = None
    if project is not None:
        deployment = db.scalar(
            select(HostingDeployment)
            .where(HostingDeployment.project_id == project.id)
            .order_by(HostingDeployment.created_at.desc())
            .limit(1)
        )
    edge = _edge_application(db, project) if project else None
    route = db.scalar(select(EdgeRouteDeployment).where(EdgeRouteDeployment.application_id == edge.id)) if edge else None
    origin = db.scalar(select(EdgeOrigin).where(EdgeOrigin.application_id == edge.id, EdgeOrigin.enabled.is_(True)).limit(1)) if edge else None

    # A healthy deployment can hand its controlled private/VPN origin directly
    # to the edge layer. Reconciliation is safe to repeat while DNS/TLS settles.
    edge_state = None
    if project and deployment and deployment.status == "healthy" and deployment.origin_url and project.hostname:
        try:
            edge_state = reconcile_project_edge(db, project, deployment.origin_url)
            edge = _edge_application(db, project)
            route = db.scalar(select(EdgeRouteDeployment).where(EdgeRouteDeployment.application_id == edge.id)) if edge else None
            origin = db.scalar(select(EdgeOrigin).where(EdgeOrigin.application_id == edge.id, EdgeOrigin.enabled.is_(True)).limit(1)) if edge else None
        except HostingOriginError as exc:
            edge_state = {"status": "pending_origin", "error": str(exc), "hostname": project.hostname}

    stages = {
        "placement": {"status": "ready" if project and project.node_id else "pending"},
        "source": {"status": source.status if source else "pending"},
        "database": {"status": database.status if database else "not_requested"},
        "build": {"status": build.status if build else "pending"},
        "deployment": {"status": deployment.status if deployment else "waiting_for_build"},
        "edge": {
            "status": (
                "not_requested" if not project or not project.hostname
                else edge_state.get("status") if edge_state
                else route.status if route
                else "pending_origin" if edge and not origin
                else "pending_route" if edge
                else "pending"
            ),
            "hostname": project.hostname if project else None,
            "application_id": str(edge.id) if edge else None,
            "origin_url": deployment.origin_url if deployment else None,
            "error": edge_state.get("error") if edge_state else (route.error if route else None),
        },
    }

    failures = []
    if source and source.status == "failed":
        failures.append(source.failure_message or "Source preparation failed")
    if database and database.status == "failed":
        failures.append(database.failure_message or "Database provisioning failed")
    if build and build.status == "failed":
        failures.append(build.failure_message or "Application build failed")
    if deployment and deployment.status == "failed":
        failures.append(deployment.failure_message or "Application deployment failed")
    if route and route.status == "error":
        failures.append(route.error or "Edge route activation failed")

    database_ready = database is None or database.status in {"ready", "suspended"}
    deployment_ready = deployment is not None and deployment.status == "healthy"
    edge_ready = not project or not project.hostname or (route is not None and route.status == "active")
    if failures:
        status = "failed"
    elif database_ready and deployment_ready and edge_ready:
        status = "completed"
    elif build and build.status in {"queued", "claimed", "building"}:
        status = "building"
    elif deployment and deployment.status in {"queued", "claimed", "running"}:
        status = "deploying"
    elif project and project.hostname and deployment_ready:
        status = "edge_pending"
    else:
        status = "provisioning"

    workflow.status = status
    workflow.failure_message = "; ".join(failures)[:2000] if failures else None
    if status == "completed" and workflow.completed_at is None:
        workflow.completed_at = _now()
    return {
        "id": str(workflow.id),
        "tenant_id": str(workflow.tenant_id),
        "project_id": str(workflow.project_id),
        "status": status,
        "failure_message": workflow.failure_message,
        "stages": stages,
        "created_at": workflow.created_at.isoformat() if workflow.created_at else None,
        "updated_at": workflow.updated_at.isoformat() if workflow.updated_at else None,
        "completed_at": workflow.completed_at.isoformat() if workflow.completed_at else None,
    }


@router.post("/tenants/{tenant_id}/hosting/projects/{project_id}/provision", status_code=202)
def provision_project(
    tenant_id: UUID,
    project_id: UUID,
    payload: ProvisionRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    project = db.scalar(select(HostingProject).where(
        HostingProject.id == project_id,
        HostingProject.tenant_id == tenant_id,
    ).with_for_update())
    if project is None:
        raise HTTPException(status_code=404, detail="Hosted project not found")
    if project.status == "suspended":
        raise HTTPException(status_code=409, detail="Resume the project before provisioning it")
    if project.node_id is None:
        raise HTTPException(status_code=409, detail="Project has not been assigned to a hosting node")

    active = db.scalar(select(HostingProvisioningWorkflow).where(
        HostingProvisioningWorkflow.project_id == project.id,
        HostingProvisioningWorkflow.status.in_(["queued", "provisioning", "building", "deploying", "edge_pending"]),
    ).order_by(HostingProvisioningWorkflow.created_at.desc()))
    if active is not None:
        result = _stage_out(db, active)
        db.commit()
        return result

    source = _source(db, project, current)
    workflow = HostingProvisioningWorkflow(
        tenant_id=tenant_id,
        project_id=project.id,
        source_id=source.id,
        status="provisioning",
        request_json=json.dumps(payload.model_dump(), sort_keys=True),
        requested_by_user_id=current.id,
    )
    db.add(workflow)
    db.flush()

    for key, value in payload.environment.items():
        _upsert_env(db, project.id, key, str(value), current, secret=True)

    database = None
    if payload.database_engine:
        allowed, reason, _ = database_allocation_allowed(db, tenant_id, payload.database_storage_mb)
        if not allowed:
            raise HTTPException(status_code=402, detail=reason)
        db_name = _safe_db_name(payload.database_name or f"{project.slug}_db")
        duplicate = db.scalar(select(HostingDatabase).where(
            HostingDatabase.tenant_id == tenant_id,
            HostingDatabase.engine == payload.database_engine,
            HostingDatabase.database_name == db_name,
        ))
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="A database with this name and engine already exists")
        node, _ = select_node(
            db,
            workload="database",
            storage_mb=payload.database_storage_mb,
            database_engine=payload.database_engine,
            preferred_node_id=project.node_id,
        )
        suffix = secrets.token_hex(4)
        username = f"ith_{db_name[:32]}_{suffix}"[:63]
        raw_password = secrets.token_urlsafe(32)
        database = HostingDatabase(
            tenant_id=tenant_id,
            project_id=project.id,
            node_id=node.id,
            engine=payload.database_engine,
            database_name=db_name,
            username=username,
            encrypted_password=encrypt_secret(raw_password),
            internal_port=5432 if payload.database_engine == "postgresql" else 3306,
            storage_mb=payload.database_storage_mb,
            status="queued",
            operation="provision",
            created_by_user_id=current.id,
        )
        db.add(database)
        db.flush()
        workflow.database_id = database.id
        _upsert_env(db, project.id, "DATABASE_ENGINE", database.engine, current, secret=False)
        _upsert_env(db, project.id, "DATABASE_NAME", database.database_name, current, secret=False)
        _upsert_env(db, project.id, "DATABASE_USER", database.username, current, secret=True)
        _upsert_env(db, project.id, "DATABASE_PASSWORD", raw_password, current, secret=True)
        _upsert_env(db, project.id, "DATABASE_PORT", str(database.internal_port), current, secret=False)

    active_build = db.scalar(select(HostingBuild.id).where(
        HostingBuild.project_id == project.id,
        HostingBuild.status.in_(["queued", "claimed", "building"]),
    ))
    if active_build is not None:
        raise HTTPException(status_code=409, detail="This project already has a build in progress")
    build = HostingBuild(
        tenant_id=tenant_id,
        project_id=project.id,
        source_id=source.id,
        runtime=project.runtime,
        status="queued",
        requested_by_user_id=current.id,
    )
    db.add(build)
    db.flush()
    workflow.build_id = build.id

    if payload.create_edge_application and project.hostname and project.domain_id:
        domain = db.scalar(select(Domain).where(Domain.id == project.domain_id, Domain.tenant_id == tenant_id))
        if domain is None or domain.status != DomainStatus.verified or domain.ownership_verified_at is None:
            raise HTTPException(status_code=409, detail="Verify the project domain before automatic edge/HTTPS provisioning")
        edge = _edge_application(db, project)
        if edge is None:
            edge = EdgeApplication(
                tenant_id=tenant_id,
                domain_id=domain.id,
                hostname=project.hostname,
                mode="protected",
                enabled=True,
                tls_mode="automatic",
                minimum_tls_version="TLSv1.2",
                health_path=project.health_path,
                expected_status=200,
            )
            db.add(edge)
            try:
                db.flush()
            except IntegrityError as exc:
                db.rollback()
                raise HTTPException(status_code=409, detail="An edge application already exists for this hostname") from exc

    _audit(db, current, workflow, "hosting.provisioning.start", {
        "source_id": str(source.id),
        "database_id": str(database.id) if database else None,
        "build_id": str(build.id),
        "hostname": project.hostname,
    })
    db.commit()
    db.refresh(workflow)
    result = _stage_out(db, workflow)
    db.commit()
    return result


@router.get("/tenants/{tenant_id}/hosting/projects/{project_id}/provisioning")
def provisioning_status(
    tenant_id: UUID,
    project_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.read", db, current)
    workflow = db.scalar(select(HostingProvisioningWorkflow).where(
        HostingProvisioningWorkflow.tenant_id == tenant_id,
        HostingProvisioningWorkflow.project_id == project_id,
    ).order_by(HostingProvisioningWorkflow.created_at.desc()))
    if workflow is None:
        return {"workflow": None}
    result = _stage_out(db, workflow)
    db.commit()
    return {"workflow": result}
