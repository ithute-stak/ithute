from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BillingPlan, HostingDatabase, HostingSource, TenantSubscription

_ACTIVE_SOURCE_STATUSES = {"uploading", "ready", "building"}


def _effective_limits(plan: BillingPlan) -> dict[str, int]:
    projects = int(plan.included_hosted_projects or 0)
    if projects <= 0:
        return {
            "database_count": 0,
            "database_storage_bytes": 0,
            "source_storage_bytes": 0,
        }
    database_limit = int(plan.hosting_database_limit or max(1, projects * 2))
    database_storage_mb = int(plan.hosting_database_storage_mb or plan.hosting_storage_mb or 0)
    source_storage_mb = int(plan.hosting_source_storage_mb or plan.hosting_storage_mb or 0)
    return {
        "database_count": max(0, database_limit),
        "database_storage_bytes": max(0, database_storage_mb) * 1024 * 1024,
        "source_storage_bytes": max(0, source_storage_mb) * 1024 * 1024,
    }


def hosting_resource_usage(db: Session, tenant_id: UUID) -> dict[str, int]:
    database_count = db.scalar(
        select(func.count(HostingDatabase.id)).where(HostingDatabase.tenant_id == tenant_id)
    ) or 0
    database_storage_mb = db.scalar(
        select(func.coalesce(func.sum(HostingDatabase.storage_mb), 0)).where(HostingDatabase.tenant_id == tenant_id)
    ) or 0
    source_storage_bytes = db.scalar(
        select(func.coalesce(func.sum(HostingSource.size_bytes), 0)).where(
            HostingSource.tenant_id == tenant_id,
            HostingSource.source_type == "zip",
            HostingSource.status.in_(_ACTIVE_SOURCE_STATUSES),
        )
    ) or 0
    return {
        "database_count": int(database_count),
        "database_storage_bytes": int(database_storage_mb) * 1024 * 1024,
        "source_storage_bytes": int(source_storage_bytes),
    }


def hosting_resource_meter(db: Session, tenant_id: UUID) -> dict:
    usage = hosting_resource_usage(db, tenant_id)
    subscription = db.scalar(select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id))
    if subscription is None:
        return {"usage": usage, "limits": None, "subscription_status": None}
    plan = db.get(BillingPlan, subscription.plan_id)
    if plan is None or not plan.is_active:
        return {"usage": usage, "limits": None, "subscription_status": str(subscription.status.value)}
    return {
        "usage": usage,
        "limits": _effective_limits(plan),
        "subscription_status": str(subscription.status.value),
        "plan": {"id": str(plan.id), "code": plan.code, "name": plan.name},
    }


def database_allocation_allowed(db: Session, tenant_id: UUID, requested_storage_mb: int) -> tuple[bool, str, dict]:
    meter = hosting_resource_meter(db, tenant_id)
    limits = meter.get("limits")
    if limits is None:
        return False, "Organization has no active hosting package", meter
    usage = meter["usage"]
    requested_bytes = int(requested_storage_mb) * 1024 * 1024
    if usage["database_count"] + 1 > limits["database_count"]:
        return False, "Hosted database count limit reached", meter
    if usage["database_storage_bytes"] + requested_bytes > limits["database_storage_bytes"]:
        return False, "Hosted database storage limit reached", meter
    return True, "within plan", meter


def source_allocation_allowed(db: Session, tenant_id: UUID, requested_bytes: int) -> tuple[bool, str, dict]:
    meter = hosting_resource_meter(db, tenant_id)
    limits = meter.get("limits")
    if limits is None:
        return False, "Organization has no active hosting package", meter
    usage = meter["usage"]
    if usage["source_storage_bytes"] + int(requested_bytes) > limits["source_storage_bytes"]:
        return False, "Hosted source storage limit reached", meter
    return True, "within plan", meter
