from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_platform_owner
from app.db.session import get_db
from app.models import (
    AuditLog,
    Domain,
    HostingNode,
    HostingNodeAgent,
    HostingProject,
    IthuteProduct,
    IthuteSubscriptionGrant,
    Mailbox,
    MembershipStatus,
    SubscriptionGrantStatus,
    Tenant,
    TenantMembership,
    User,
)
from app.services.ithute_operating import ensure_default_products, product_snapshot, utcnow
from app.services.operations_status import OperationsStatusError, operations_status


router = APIRouter(prefix="/platform/ithute", tags=["system-owner"])


class ProductAccessUpdate(BaseModel):
    tenant_id: UUID
    product_id: str = Field(min_length=2, max_length=80)
    plan: str = Field(default="business", min_length=1, max_length=100)
    status: SubscriptionGrantStatus = SubscriptionGrantStatus.active
    features: dict[str, Any] = Field(default_factory=dict)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _ratio(used: int, total: int) -> float:
    return round((used / total) * 100, 1) if total > 0 else 0.0


def _agent_online(agent: HostingNodeAgent | None) -> bool:
    if agent is None or agent.last_seen_at is None:
        return False
    seen = agent.last_seen_at
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    return (utcnow() - seen).total_seconds() <= 180


def _grant_out(grant: IthuteSubscriptionGrant, tenant_names: dict[str, str], product_names: dict[str, str]) -> dict[str, Any]:
    return {
        "id": str(grant.id),
        "subject_type": grant.subject_type,
        "subject_id": grant.subject_id,
        "organization_name": tenant_names.get(grant.subject_id),
        "product_id": grant.product_id,
        "product_name": product_names.get(grant.product_id, grant.product_id),
        "plan": grant.plan,
        "status": grant.status.value,
        "features": grant.features_json or {},
        "starts_at": _iso(grant.starts_at),
        "ends_at": _iso(grant.ends_at),
        "updated_at": _iso(grant.updated_at),
    }


@router.get("/system-owner/overview")
def system_owner_overview(
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
) -> dict[str, Any]:
    _ = current
    products = ensure_default_products(db)
    product_cards = [product_snapshot(db, product) for product in products]
    tenants = list(db.scalars(select(Tenant).order_by(Tenant.name)))
    memberships = list(db.scalars(select(TenantMembership)))
    projects = list(db.scalars(select(HostingProject)))
    grants = list(db.scalars(select(IthuteSubscriptionGrant)))
    nodes = list(db.scalars(select(HostingNode).order_by(HostingNode.name)))
    agents = {row.node_id: row for row in db.scalars(select(HostingNodeAgent))}

    members_by_tenant: dict[UUID, int] = defaultdict(int)
    for row in memberships:
        if row.status == MembershipStatus.active:
            members_by_tenant[row.tenant_id] += 1

    projects_by_tenant: dict[UUID, list[HostingProject]] = defaultdict(list)
    projects_by_node: dict[UUID, list[HostingProject]] = defaultdict(list)
    for project in projects:
        projects_by_tenant[project.tenant_id].append(project)
        if project.node_id:
            projects_by_node[project.node_id].append(project)

    grant_products_by_tenant: dict[str, list[dict[str, str]]] = defaultdict(list)
    product_name = {product.id: product.name for product in products}
    for grant in grants:
        if grant.subject_type not in {"tenant", "organization"}:
            continue
        grant_products_by_tenant[grant.subject_id].append(
            {"id": grant.product_id, "name": product_name.get(grant.product_id, grant.product_id), "status": grant.status.value, "plan": grant.plan}
        )

    organizations: list[dict[str, Any]] = []
    for tenant in tenants:
        tenant_id = str(tenant.id)
        organizations.append(
            {
                "id": tenant_id,
                "name": tenant.name,
                "slug": tenant.slug,
                "status": tenant.status.value,
                "members": members_by_tenant.get(tenant.id, 0),
                "hosted_projects": len(projects_by_tenant.get(tenant.id, [])),
                "domains": db.scalar(select(func.count()).select_from(Domain).where(Domain.tenant_id == tenant.id)) or 0,
                "mailboxes": db.scalar(select(func.count()).select_from(Mailbox).where(Mailbox.tenant_id == tenant.id)) or 0,
                "products": sorted(grant_products_by_tenant.get(tenant_id, []), key=lambda item: item["name"]),
                "created_at": _iso(tenant.created_at),
            }
        )

    infrastructure: list[dict[str, Any]] = []
    alerts: list[dict[str, str]] = []
    for node in nodes:
        assigned = projects_by_node.get(node.id, [])
        storage_used = sum(project.storage_mb for project in assigned if project.status != "suspended")
        memory_used = sum(project.memory_mb for project in assigned if project.status != "suspended")
        cpu_used = sum(project.cpu_millicores for project in assigned if project.status != "suspended")
        agent = agents.get(node.id)
        online = _agent_online(agent)
        storage_pct = _ratio(storage_used, node.allocatable_storage_mb)
        memory_pct = _ratio(memory_used, node.allocatable_memory_mb)
        cpu_pct = _ratio(cpu_used, node.allocatable_cpu_millicores)
        if not online:
            alerts.append({"severity": "high", "title": f"{node.name} agent is not reporting", "detail": "Hosting-node heartbeat is stale or missing."})
        for label, value in (("storage", storage_pct), ("memory", memory_pct), ("CPU", cpu_pct)):
            if value >= 90:
                alerts.append({"severity": "high", "title": f"{node.name} {label} allocation is {value:.0f}%", "detail": "Review package allocation before placing another hosted project on this node."})
            elif value >= 75:
                alerts.append({"severity": "medium", "title": f"{node.name} {label} allocation is {value:.0f}%", "detail": "Capacity is approaching the operating reserve."})
        infrastructure.append(
            {
                "id": str(node.id),
                "name": node.name,
                "hostname": node.hostname,
                "public_ip": node.public_ip,
                "status": node.status,
                "accepts_new_projects": node.accepts_new_projects,
                "agent_online": online,
                "agent_version": agent.agent_version if agent else None,
                "last_seen_at": _iso(agent.last_seen_at) if agent else None,
                "projects": len(assigned),
                "capacity": {
                    "storage_mb": node.allocatable_storage_mb,
                    "memory_mb": node.allocatable_memory_mb,
                    "cpu_millicores": node.allocatable_cpu_millicores,
                },
                "allocated": {"storage_mb": storage_used, "memory_mb": memory_used, "cpu_millicores": cpu_used},
                "allocation_percent": {"storage": storage_pct, "memory": memory_pct, "cpu": cpu_pct},
            }
        )

    for card in product_cards:
        if card["status"] in {"offline", "degraded"}:
            alerts.append({"severity": "high" if card["status"] == "offline" else "medium", "title": f"{card['name']} is {card['status']}", "detail": card.get("last_error") or "Latest product heartbeat needs attention."})

    try:
        core_operations: dict[str, Any] = operations_status()
    except OperationsStatusError as exc:
        core_operations = {"status": "unknown", "services": {}, "error": str(exc)}
        alerts.append({"severity": "medium", "title": "Operations telemetry unavailable", "detail": "Prometheus status could not be read from the control plane."})

    recent_audit = [
        {
            "id": str(row.id),
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "tenant_id": str(row.tenant_id) if row.tenant_id else None,
            "created_at": _iso(row.created_at),
        }
        for row in db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(20))
    ]

    active_grants = sum(1 for grant in grants if grant.status in {SubscriptionGrantStatus.active, SubscriptionGrantStatus.demo})
    return {
        "totals": {
            "organizations": len(tenants),
            "active_users": db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True))) or 0,
            "products": len(products),
            "product_access_grants": active_grants,
            "hosted_projects": len(projects),
            "hosting_nodes": len(nodes),
            "domains": db.scalar(select(func.count()).select_from(Domain)) or 0,
            "mailboxes": db.scalar(select(func.count()).select_from(Mailbox)) or 0,
        },
        "organizations": organizations,
        "infrastructure": infrastructure,
        "products": product_cards,
        "core_operations": core_operations,
        "alerts": alerts[:40],
        "recent_audit": recent_audit,
        "generated_at": utcnow().isoformat(),
    }


@router.get("/system-owner/product-access")
def list_product_access(
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
) -> dict[str, Any]:
    _ = current
    products = ensure_default_products(db)
    tenants = list(db.scalars(select(Tenant).order_by(Tenant.name)))
    tenant_names = {str(tenant.id): tenant.name for tenant in tenants}
    product_names = {product.id: product.name for product in products}
    rows = list(db.scalars(select(IthuteSubscriptionGrant).order_by(IthuteSubscriptionGrant.updated_at.desc())))
    return {
        "organizations": [{"id": str(tenant.id), "name": tenant.name, "status": tenant.status.value} for tenant in tenants],
        "products": [{"id": product.id, "name": product.name, "public_url": product.public_url, "auth_mode": product.auth_mode} for product in products],
        "grants": [_grant_out(row, tenant_names, product_names) for row in rows],
    }


@router.put("/system-owner/product-access")
def set_product_access(
    payload: ProductAccessUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
) -> dict[str, Any]:
    tenant = db.get(Tenant, payload.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    products = ensure_default_products(db)
    product = next((item for item in products if item.id == payload.product_id), None)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    subject_id = str(tenant.id)
    grant = db.scalar(
        select(IthuteSubscriptionGrant).where(
            IthuteSubscriptionGrant.subject_type == "tenant",
            IthuteSubscriptionGrant.subject_id == subject_id,
            IthuteSubscriptionGrant.product_id == product.id,
        )
    )
    if grant is None:
        grant = IthuteSubscriptionGrant(subject_type="tenant", subject_id=subject_id, product_id=product.id)
        db.add(grant)
    grant.plan = payload.plan.strip()
    grant.status = payload.status
    grant.features_json = payload.features
    db.add(
        AuditLog(
            tenant_id=tenant.id,
            actor_user_id=current.id,
            action="ithute.product_access.update",
            resource_type="ithute_subscription_grant",
            resource_id=str(grant.id) if grant.id else None,
            metadata_json=json.dumps({"product_id": product.id, "plan": grant.plan, "status": grant.status.value}, sort_keys=True),
        )
    )
    db.commit()
    db.refresh(grant)
    return {
        "id": str(grant.id),
        "organization": {"id": subject_id, "name": tenant.name},
        "product": {"id": product.id, "name": product.name},
        "plan": grant.plan,
        "status": grant.status.value,
        "sso_mode": "central_oidc" if product.auth_mode == "central" else product.auth_mode,
        "launch_url": product.public_url,
    }


@router.get("/access/my-apps")
def my_organization_apps(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    products = ensure_default_products(db)
    if current.is_platform_owner:
        result = []
        for product in products:
            card = product_snapshot(db, product)
            card["license"] = {"plan": "platform-owner", "status": "active", "features": {}, "source": "system-owner"}
            card["launch_url"] = product.public_url
            card["sso_mode"] = "central_oidc" if product.auth_mode == "central" else product.auth_mode
            result.append(card)
        return result

    direct_subject = str(current.auth_user_id or current.id)
    tenant_ids = [
        str(value)
        for value in db.scalars(
            select(TenantMembership.tenant_id).where(
                TenantMembership.user_id == current.id,
                TenantMembership.status == MembershipStatus.active,
            )
        )
    ]
    conditions = [
        (IthuteSubscriptionGrant.subject_type == "user") & (IthuteSubscriptionGrant.subject_id == direct_subject)
    ]
    if tenant_ids:
        conditions.append(
            (IthuteSubscriptionGrant.subject_type.in_(["tenant", "organization"]))
            & (IthuteSubscriptionGrant.subject_id.in_(tenant_ids))
        )
    grants = list(
        db.scalars(
            select(IthuteSubscriptionGrant).where(
                or_(*conditions),
                IthuteSubscriptionGrant.status.in_([SubscriptionGrantStatus.demo, SubscriptionGrantStatus.active]),
            )
        )
    )

    chosen: dict[str, IthuteSubscriptionGrant] = {}
    for grant in grants:
        previous = chosen.get(grant.product_id)
        if previous is None or (grant.subject_type == "user" and previous.subject_type != "user"):
            chosen[grant.product_id] = grant

    # Mailbox/DNS remains the control-centre product for an authenticated Ithute account.
    allowed_ids = set(chosen)
    allowed_ids.add("mailbox-dns")
    result: list[dict[str, Any]] = []
    for product in products:
        if product.id not in allowed_ids:
            continue
        card = product_snapshot(db, product)
        grant = chosen.get(product.id)
        card["license"] = (
            {
                "plan": grant.plan,
                "status": grant.status.value,
                "features": grant.features_json or {},
                "source": "user" if grant.subject_type == "user" else "organization",
            }
            if grant
            else {"plan": "control-centre", "status": "active", "features": {}, "source": "default"}
        )
        card["launch_url"] = product.public_url
        card["sso_mode"] = "central_oidc" if product.auth_mode == "central" else product.auth_mode
        result.append(card)
    return result
