from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_platform_owner, require_tenant_permission
from app.db.session import get_db
from app.models import (
    AuditLog,
    BillingPlan,
    Domain,
    DomainStatus,
    HOSTING_RULES_VERSION,
    HostingDatabase,
    HostingFailoverAttempt,
    HostingNode,
    HostingNodeHealthState,
    HostingProject,
    SubscriptionStatus,
    TenantSubscription,
    User,
)
from app.services.billing import entitlement_decision, get_subscription
from app.services.hosting_placement import rank_nodes, select_node
from app.services.hosting_failover import failover_attempt_out, request_project_relocation

router = APIRouter(tags=["application-hosting"])

ALLOWED_RUNTIMES = {"static", "node", "python", "php", "dotnet", "java", "go", "ruby", "rust", "dockerfile"}
HOSTING_RULES = [
    "Hosted projects run in Ithute-managed isolated workloads. Customers do not receive root, host SSH, Docker socket, or privileged-container access.",
    "Every project is limited by its package storage, memory, CPU and process allocation; attempting to bypass those limits is prohibited.",
    "Only the Ithute edge proxy may publish customer applications to the Internet. Project workloads may not bind arbitrary public host ports.",
    "Application source must be built by an approved isolated build pipeline. Customer build scripts are not executed with unrestricted access on the production host.",
    "Workloads must run as a non-root application user where the runtime supports it and may write only to storage explicitly allocated to that project.",
    "Crypto-mining, malware, spam, credential theft, open proxies/VPN relays, port scanning and deliberate resource-exhaustion workloads are prohibited.",
    "Databases and secrets must use project-scoped credentials. Control-plane, host, mail, DNS and other tenants' credentials may never be embedded in a hosted project.",
    "Direct outbound bulk SMTP is not part of application hosting. Applications that send email must use an approved Ithute mail/transactional-email path and its limits.",
    "A custom hostname must belong to a verified domain owned by the same organization before Ithute can route public traffic to the project.",
    "Ithute may suspend a workload that threatens platform availability or violates these hosting rules; data removal remains a separate explicit operation.",
]

_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,98}[a-z0-9])?$")


class HostingNodeCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    hostname: str = Field(min_length=3, max_length=253)
    public_ip: str | None = Field(default=None, max_length=64)
    allocatable_storage_mb: int = Field(ge=1024, le=100_000_000)
    allocatable_memory_mb: int = Field(ge=512, le=10_000_000)
    allocatable_cpu_millicores: int = Field(ge=500, le=100_000_000)
    accepts_new_projects: bool = True


class HostingNodeUpdate(BaseModel):
    allocatable_storage_mb: int | None = Field(default=None, ge=1024, le=100_000_000)
    allocatable_memory_mb: int | None = Field(default=None, ge=512, le=10_000_000)
    allocatable_cpu_millicores: int | None = Field(default=None, ge=500, le=100_000_000)
    accepts_new_projects: bool | None = None
    status: str | None = Field(default=None, pattern=r"^(active|draining|offline)$")


class HostingProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str | None = Field(default=None, max_length=100)
    runtime: str = Field(pattern=r"^(static|node|python|php|dotnet|java|go|ruby|rust|dockerfile)$")
    source_repository: str | None = Field(default=None, max_length=1000)
    source_branch: str = Field(default="main", min_length=1, max_length=160)
    domain_id: UUID | None = None
    hostname: str | None = Field(default=None, max_length=253)
    container_port: int = Field(default=8080, ge=1024, le=65535)
    health_path: str = Field(default="/", min_length=1, max_length=500)
    storage_mb: int = Field(default=1024, ge=128, le=10240)
    memory_mb: int = Field(default=512, ge=128, le=8192)
    cpu_millicores: int = Field(default=500, ge=100, le=4000)
    pid_limit: int = Field(default=128, ge=32, le=2048)
    accept_hosting_rules: bool
    node_id: UUID | None = None
    preferred_region: str | None = Field(default=None, max_length=80)


class HostingProjectUpdate(BaseModel):
    source_repository: str | None = Field(default=None, max_length=1000)
    source_branch: str | None = Field(default=None, min_length=1, max_length=160)
    health_path: str | None = Field(default=None, min_length=1, max_length=500)
    container_port: int | None = Field(default=None, ge=1024, le=65535)
    status: str | None = Field(default=None, pattern=r"^(configured|suspended)$")


class HostingFailoverPolicyUpdate(BaseModel):
    policy: str = Field(pattern=r"^(manual|stateless_auto)$")
    confirm_local_data_disposable: bool = False


class HostingRelocationRequest(BaseModel):
    target_node_id: UUID | None = None


def _slug(value: str) -> str:
    candidate = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")[:100]
    if not candidate or not _SLUG_RE.fullmatch(candidate):
        raise HTTPException(status_code=422, detail="Invalid project slug")
    return candidate


def _normalize_hostname(value: str) -> str:
    host = value.strip().rstrip(".").lower()
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise HTTPException(status_code=422, detail="Invalid project hostname") from exc
    if len(host) > 253 or not host or any(not label or len(label) > 63 for label in host.split(".")):
        raise HTTPException(status_code=422, detail="Invalid project hostname")
    return host


def _audit(db: Session, current: User, action: str, resource_type: str, resource_id: str, tenant_id: UUID | None = None, metadata: dict | None = None) -> None:
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=current.id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata_json=json.dumps(metadata or {}, sort_keys=True),
        )
    )


def _subscription_plan(db: Session, tenant_id: UUID) -> tuple[TenantSubscription, BillingPlan]:
    subscription = get_subscription(db, tenant_id)
    if subscription is None:
        raise HTTPException(status_code=402, detail="Organization has no hosting subscription")
    plan = db.get(BillingPlan, subscription.plan_id)
    if plan is None or not plan.is_active:
        raise HTTPException(status_code=402, detail="Organization hosting package is unavailable")
    now = datetime.now(timezone.utc)
    if subscription.status == SubscriptionStatus.canceled:
        raise HTTPException(status_code=402, detail="Organization hosting subscription is canceled")
    if subscription.status == SubscriptionStatus.past_due and (subscription.grace_ends_at is None or subscription.grace_ends_at <= now):
        raise HTTPException(status_code=402, detail="Organization hosting payment grace period has expired")
    if subscription.status not in {SubscriptionStatus.trialing, SubscriptionStatus.active, SubscriptionStatus.past_due}:
        raise HTTPException(status_code=402, detail="Organization subscription does not allow hosting")
    return subscription, plan


def _node_allocated(db: Session, node_id: UUID) -> dict:
    row = db.execute(
        select(
            func.coalesce(func.sum(HostingProject.storage_mb), 0),
            func.coalesce(func.sum(HostingProject.memory_mb), 0),
            func.coalesce(func.sum(HostingProject.cpu_millicores), 0),
            func.count(HostingProject.id),
        ).where(HostingProject.node_id == node_id)
    ).one()
    database_storage = int(
        db.scalar(
            select(func.coalesce(func.sum(HostingDatabase.storage_mb), 0)).where(
                HostingDatabase.node_id == node_id,
                HostingDatabase.status != "deleting",
            )
        )
        or 0
    )
    reserved = db.execute(
        select(
            func.coalesce(func.sum(HostingProject.storage_mb), 0),
            func.coalesce(func.sum(HostingProject.memory_mb), 0),
            func.coalesce(func.sum(HostingProject.cpu_millicores), 0),
            func.count(HostingProject.id),
        )
        .join(HostingFailoverAttempt, HostingFailoverAttempt.project_id == HostingProject.id)
        .where(
            HostingFailoverAttempt.target_node_id == node_id,
            HostingFailoverAttempt.status.in_(["pending", "deploying", "edge_pending"]),
            HostingProject.node_id != node_id,
        )
    ).one()
    return {
        "storage_mb": int(row[0]) + database_storage + int(reserved[0]),
        "application_storage_mb": int(row[0]),
        "database_storage_mb": database_storage,
        "failover_reserved_storage_mb": int(reserved[0]),
        "memory_mb": int(row[1]) + int(reserved[1]),
        "cpu_millicores": int(row[2]) + int(reserved[2]),
        "projects": int(row[3]) + int(reserved[3]),
    }


def _node_out(db: Session, node: HostingNode) -> dict:
    allocated = _node_allocated(db, node.id)
    return {
        "id": str(node.id),
        "name": node.name,
        "hostname": node.hostname,
        "public_ip": node.public_ip,
        "status": node.status,
        "accepts_new_projects": node.accepts_new_projects,
        "allocatable": {
            "storage_mb": node.allocatable_storage_mb,
            "memory_mb": node.allocatable_memory_mb,
            "cpu_millicores": node.allocatable_cpu_millicores,
        },
        "allocated": allocated,
        "available": {
            "storage_mb": max(0, node.allocatable_storage_mb - allocated["storage_mb"]),
            "memory_mb": max(0, node.allocatable_memory_mb - allocated["memory_mb"]),
            "cpu_millicores": max(0, node.allocatable_cpu_millicores - allocated["cpu_millicores"]),
        },
    }


def _project_out(project: HostingProject) -> dict:
    return {
        "id": str(project.id),
        "tenant_id": str(project.tenant_id),
        "node_id": str(project.node_id) if project.node_id else None,
        "domain_id": str(project.domain_id) if project.domain_id else None,
        "name": project.name,
        "slug": project.slug,
        "hostname": project.hostname,
        "runtime": project.runtime,
        "source_repository": project.source_repository,
        "source_branch": project.source_branch,
        "container_port": project.container_port,
        "health_path": project.health_path,
        "storage_mb": project.storage_mb,
        "memory_mb": project.memory_mb,
        "cpu_millicores": project.cpu_millicores,
        "pid_limit": project.pid_limit,
        "status": project.status,
        "failover_policy": project.failover_policy,
        "rules_version": project.rules_version,
        "rules_accepted_at": project.rules_accepted_at.isoformat(),
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
        "isolation": {
            "root_access": False,
            "host_ssh": False,
            "docker_socket": False,
            "privileged": False,
            "public_host_ports": False,
            "ingress": "Ithute edge proxy only",
            "build_policy": "approved isolated builder only",
        },
    }


@router.get("/hosting/rules")
def hosting_rules():
    return {
        "version": HOSTING_RULES_VERSION,
        "title": "Ithute shared application hosting rules",
        "service_type": "managed shared application hosting (not a root VPS)",
        "allowed_runtimes": sorted(ALLOWED_RUNTIMES),
        "rules": HOSTING_RULES,
    }


@router.get("/platform/hosting/nodes")
def list_hosting_nodes(db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    nodes = db.scalars(select(HostingNode).order_by(HostingNode.name)).all()
    return {"items": [_node_out(db, node) for node in nodes]}


@router.post("/platform/hosting/nodes", status_code=201)
def create_hosting_node(payload: HostingNodeCreate, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    name = payload.name.strip()
    if db.scalar(select(HostingNode.id).where(func.lower(HostingNode.name) == name.lower())) is not None:
        raise HTTPException(status_code=409, detail="A hosting node with this name already exists")
    node = HostingNode(
        name=name,
        hostname=_normalize_hostname(payload.hostname),
        public_ip=payload.public_ip.strip() if payload.public_ip else None,
        allocatable_storage_mb=payload.allocatable_storage_mb,
        allocatable_memory_mb=payload.allocatable_memory_mb,
        allocatable_cpu_millicores=payload.allocatable_cpu_millicores,
        accepts_new_projects=payload.accepts_new_projects,
        created_by_user_id=current.id,
    )
    db.add(node)
    db.flush()
    _audit(db, current, "hosting.node.create", "hosting_node", str(node.id), metadata={"name": node.name})
    db.commit()
    db.refresh(node)
    return _node_out(db, node)


@router.patch("/platform/hosting/nodes/{node_id}")
def update_hosting_node(node_id: UUID, payload: HostingNodeUpdate, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    node = db.get(HostingNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Hosting node not found")
    changes = payload.model_dump(exclude_unset=True)
    allocated = _node_allocated(db, node.id)
    proposed_storage = changes.get("allocatable_storage_mb", node.allocatable_storage_mb)
    proposed_memory = changes.get("allocatable_memory_mb", node.allocatable_memory_mb)
    proposed_cpu = changes.get("allocatable_cpu_millicores", node.allocatable_cpu_millicores)
    if proposed_storage < allocated["storage_mb"] or proposed_memory < allocated["memory_mb"] or proposed_cpu < allocated["cpu_millicores"]:
        raise HTTPException(status_code=409, detail="Node capacity cannot be reduced below resources already allocated to projects")
    for key, value in changes.items():
        setattr(node, key, value)

    manual_state_change = bool({"status", "accepts_new_projects"} & set(changes))
    if manual_state_change:
        health_state = db.get(HostingNodeHealthState, node.id)
        if health_state is not None:
            health_state.automation_enabled = False
            health_state.last_transition = "manual_hold"
            health_state.last_transition_at = datetime.now(timezone.utc)
            health_state.last_reason = "Node scheduling state changed manually by platform owner"

    _audit(db, current, "hosting.node.update", "hosting_node", str(node.id), metadata={
        "changed_fields": sorted(changes),
        "automation_disabled": manual_state_change,
    })
    db.commit()
    db.refresh(node)
    return _node_out(db, node)


@router.get("/platform/hosting/placement-preview")
def placement_preview(
    workload: str = "application",
    storage_mb: int = 1024,
    memory_mb: int = 512,
    cpu_millicores: int = 500,
    database_engine: str | None = None,
    preferred_region: str | None = None,
    tenant_id: UUID | None = None,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    if workload not in {"application", "database"}:
        raise HTTPException(status_code=422, detail="workload must be application or database")
    ranked = rank_nodes(
        db,
        workload=workload,
        storage_mb=max(0, storage_mb),
        memory_mb=max(0, memory_mb),
        cpu_millicores=max(0, cpu_millicores),
        database_engine=database_engine,
        preferred_region=preferred_region,
        tenant_id=tenant_id,
    )
    return {
        "items": [
            {
                key: value
                for key, value in row.items()
                if key != "node"
            }
            for row in ranked
        ]
    }


@router.get("/platform/hosting/failovers")
def list_platform_failovers(
    status: str | None = None,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    query = select(HostingFailoverAttempt).order_by(HostingFailoverAttempt.created_at.desc()).limit(200)
    if status:
        query = query.where(HostingFailoverAttempt.status == status)
    rows = db.scalars(query).all()
    items = []
    for row in rows:
        project = db.get(HostingProject, row.project_id)
        source = db.get(HostingNode, row.source_node_id)
        target = db.get(HostingNode, row.target_node_id) if row.target_node_id else None
        item = failover_attempt_out(row)
        item.update({
            "project_name": project.name if project else None,
            "tenant_id": str(project.tenant_id) if project else None,
            "source_node_name": source.name if source else None,
            "target_node_name": target.name if target else None,
            "failover_policy": project.failover_policy if project else None,
        })
        items.append(item)
    return {
        "items": items,
        "failover_after_seconds": int(os.getenv("ITHUTE_HOSTING_FAILOVER_AFTER_SECONDS", "300")),
    }


@router.put("/tenants/{tenant_id}/hosting/projects/{project_id}/failover-policy")
def update_project_failover_policy(
    tenant_id: UUID,
    project_id: UUID,
    payload: HostingFailoverPolicyUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    project = db.scalar(
        select(HostingProject)
        .where(HostingProject.id == project_id, HostingProject.tenant_id == tenant_id)
        .with_for_update()
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Hosted project not found")
    if payload.policy == "stateless_auto" and not payload.confirm_local_data_disposable:
        raise HTTPException(
            status_code=422,
            detail="Confirm that project-local /data is disposable before enabling stateless automatic failover",
        )
    project.failover_policy = payload.policy
    if payload.policy == "stateless_auto" and project.node_id is not None:
        recovery_rows = db.scalars(
            select(HostingFailoverAttempt).where(
                HostingFailoverAttempt.project_id == project.id,
                HostingFailoverAttempt.source_node_id == project.node_id,
                HostingFailoverAttempt.status == "recovery_required",
            )
        ).all()
        for row in recovery_rows:
            row.status = "superseded"
            row.completed_at = datetime.now(timezone.utc)
            row.reason = "Superseded after explicit stateless auto-failover opt-in."
    _audit(
        db,
        current,
        "hosting.project.failover_policy.update",
        "hosting_project",
        str(project.id),
        tenant_id=tenant_id,
        metadata={"policy": payload.policy},
    )
    db.commit()
    return {
        "project_id": str(project.id),
        "failover_policy": project.failover_policy,
        "local_data_contract": "disposable" if project.failover_policy == "stateless_auto" else "preserve/manual recovery",
    }


@router.get("/tenants/{tenant_id}/hosting/projects/{project_id}/failovers")
def list_project_failovers(
    tenant_id: UUID,
    project_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.read", db, current)
    project = db.scalar(select(HostingProject).where(HostingProject.id == project_id, HostingProject.tenant_id == tenant_id))
    if project is None:
        raise HTTPException(status_code=404, detail="Hosted project not found")
    rows = db.scalars(
        select(HostingFailoverAttempt)
        .where(HostingFailoverAttempt.project_id == project.id)
        .order_by(HostingFailoverAttempt.created_at.desc())
        .limit(100)
    ).all()
    return {"items": [failover_attempt_out(row) for row in rows]}


@router.post("/tenants/{tenant_id}/hosting/projects/{project_id}/relocate", status_code=202)
def relocate_project(
    tenant_id: UUID,
    project_id: UUID,
    payload: HostingRelocationRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    project = db.scalar(
        select(HostingProject)
        .where(HostingProject.id == project_id, HostingProject.tenant_id == tenant_id)
        .with_for_update()
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Hosted project not found")
    try:
        attempt = request_project_relocation(
            db,
            project,
            preferred_target_node_id=payload.target_node_id,
            reason="manual_rebalance",
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(
        db,
        current,
        "hosting.project.relocation.request",
        "hosting_project",
        str(project.id),
        tenant_id=tenant_id,
        metadata={
            "attempt_id": str(attempt.id),
            "source_node_id": str(attempt.source_node_id),
            "target_node_id": str(attempt.target_node_id) if attempt.target_node_id else None,
        },
    )
    db.commit()
    db.refresh(attempt)
    return failover_attempt_out(attempt)


@router.get("/tenants/{tenant_id}/hosting/summary")
def hosting_summary(tenant_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "hosting.read", db, current)
    _, plan = _subscription_plan(db, tenant_id)
    decision = entitlement_decision(db, tenant_id, "hosting_storage", requested_storage_bytes=0)
    return {
        "package": {
            "code": plan.code,
            "name": plan.name,
            "hosted_projects": plan.included_hosted_projects,
            "hosting_storage_mb": plan.hosting_storage_mb,
            "memory_mb_per_project": plan.hosting_memory_mb_per_project,
            "cpu_millicores_per_project": plan.hosting_cpu_millicores_per_project,
            "pids_per_project": plan.hosting_pids_per_project,
        },
        "usage": decision["usage"],
        "rules_version": HOSTING_RULES_VERSION,
        "service_type": "managed shared application hosting",
    }


@router.get("/tenants/{tenant_id}/hosting/projects")
def list_hosting_projects(tenant_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "hosting.read", db, current)
    rows = db.scalars(select(HostingProject).where(HostingProject.tenant_id == tenant_id).order_by(HostingProject.created_at.desc())).all()
    return {"items": [_project_out(row) for row in rows]}


@router.post("/tenants/{tenant_id}/hosting/projects", status_code=201)
def create_hosting_project(
    tenant_id: UUID,
    payload: HostingProjectCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    if not payload.accept_hosting_rules:
        raise HTTPException(status_code=422, detail="You must accept the current Ithute hosting rules before creating a hosted project")
    if payload.runtime not in ALLOWED_RUNTIMES:
        raise HTTPException(status_code=422, detail="Unsupported hosting runtime")
    if not payload.health_path.startswith("/") or "\r" in payload.health_path or "\n" in payload.health_path:
        raise HTTPException(status_code=422, detail="Health path must start with /")

    _, plan = _subscription_plan(db, tenant_id)
    requested_bytes = payload.storage_mb * 1024 * 1024
    decision = entitlement_decision(db, tenant_id, "hosting_project", requested_storage_bytes=requested_bytes)
    if not decision["allowed"]:
        raise HTTPException(status_code=402, detail=f"Hosting package limit reached: {decision['reason']}")
    if payload.memory_mb > plan.hosting_memory_mb_per_project:
        raise HTTPException(status_code=422, detail="Requested memory exceeds this package's per-project limit")
    if payload.cpu_millicores > plan.hosting_cpu_millicores_per_project:
        raise HTTPException(status_code=422, detail="Requested CPU exceeds this package's per-project limit")
    if payload.pid_limit > plan.hosting_pids_per_project:
        raise HTTPException(status_code=422, detail="Requested process limit exceeds this package's per-project limit")

    domain = None
    hostname = None
    if payload.domain_id is not None:
        domain = db.scalar(select(Domain).where(Domain.id == payload.domain_id, Domain.tenant_id == tenant_id))
        if domain is None:
            raise HTTPException(status_code=404, detail="Hosting domain not found in this organization")
        if domain.status != DomainStatus.verified or domain.ownership_verified_at is None:
            raise HTTPException(status_code=409, detail="A hosted project can use only a verified organization domain")
        hostname = _normalize_hostname(payload.hostname or domain.ascii_name)
        zone = domain.ascii_name.rstrip(".").lower()
        if hostname != zone and not hostname.endswith("." + zone):
            raise HTTPException(status_code=422, detail="Project hostname must be inside the selected organization domain")
    elif payload.hostname:
        raise HTTPException(status_code=422, detail="Select a verified domain before assigning a public hostname")

    project_slug = _slug(payload.slug or payload.name)
    if db.scalar(select(HostingProject.id).where(HostingProject.tenant_id == tenant_id, HostingProject.slug == project_slug)) is not None:
        raise HTTPException(status_code=409, detail="A hosted project with this slug already exists in the organization")
    if hostname and db.scalar(select(HostingProject.id).where(HostingProject.hostname == hostname)) is not None:
        raise HTTPException(status_code=409, detail="This public hostname is already assigned to another hosted project")

    preferred_node_id = payload.node_id if current.is_platform_owner else None
    if payload.node_id is not None and not current.is_platform_owner:
        raise HTTPException(status_code=403, detail="Only the platform owner can override automatic workload placement")
    node, placement = select_node(
        db,
        workload="application",
        storage_mb=payload.storage_mb,
        memory_mb=payload.memory_mb,
        cpu_millicores=payload.cpu_millicores,
        preferred_node_id=preferred_node_id,
        preferred_region=payload.preferred_region,
    tenant_id=tenant_id,
    )
    now = datetime.now(timezone.utc)
    project = HostingProject(
        tenant_id=tenant_id,
        node_id=node.id,
        domain_id=domain.id if domain else None,
        name=payload.name.strip(),
        slug=project_slug,
        hostname=hostname,
        runtime=payload.runtime,
        source_repository=payload.source_repository.strip() if payload.source_repository else None,
        source_branch=payload.source_branch.strip(),
        container_port=payload.container_port,
        health_path=payload.health_path,
        storage_mb=payload.storage_mb,
        memory_mb=payload.memory_mb,
        cpu_millicores=payload.cpu_millicores,
        pid_limit=payload.pid_limit,
        status="configured",
        rules_version=HOSTING_RULES_VERSION,
        rules_accepted_at=now,
        rules_accepted_by_user_id=current.id,
        created_by_user_id=current.id,
    )
    db.add(project)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Project slug or hostname is already in use") from exc
    if placement["infrastructure_server_id"]:
        sync_tenant_infrastructure_allocation(
            db,
            tenant_id=tenant_id,
            server_id=UUID(placement["infrastructure_server_id"]),
            actor_user_id=current.id,
        )
    _audit(
        db,
        current,
        "hosting.project.create",
        "hosting_project",
        str(project.id),
        tenant_id=tenant_id,
        metadata={
            "runtime": project.runtime,
            "node_id": str(node.id),
            "storage_mb": project.storage_mb,
            "memory_mb": project.memory_mb,
            "cpu_millicores": project.cpu_millicores,
            "rules_version": project.rules_version,
            "placement_mode": "manual_override" if preferred_node_id else "automatic",
            "placement_score": placement["score"],
            "placement_server_id": placement["infrastructure_server_id"],
            "placement_preferred_region": payload.preferred_region,
            "placement_region": placement["location"]["server_region"],
            "placement_region_match": placement["location"]["region_match"],
        },
    )
    db.commit()
    db.refresh(project)
    return _project_out(project)


@router.patch("/tenants/{tenant_id}/hosting/projects/{project_id}")
def update_hosting_project(
    tenant_id: UUID,
    project_id: UUID,
    payload: HostingProjectUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    project = db.scalar(select(HostingProject).where(HostingProject.id == project_id, HostingProject.tenant_id == tenant_id))
    if project is None:
        raise HTTPException(status_code=404, detail="Hosted project not found")
    changes = payload.model_dump(exclude_unset=True)
    if "health_path" in changes and (not changes["health_path"].startswith("/") or "\r" in changes["health_path"] or "\n" in changes["health_path"]):
        raise HTTPException(status_code=422, detail="Health path must start with /")
    for key, value in changes.items():
        if key == "source_repository" and value is not None:
            value = value.strip()
        if key == "source_branch" and value is not None:
            value = value.strip()
        setattr(project, key, value)
    _audit(db, current, "hosting.project.update", "hosting_project", str(project.id), tenant_id=tenant_id, metadata={"changed_fields": sorted(changes)})
    db.commit()
    db.refresh(project)
    return _project_out(project)
