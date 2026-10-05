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


def hosting_resource_meter(db: Session, tenant_id: UUID, *, lock_subscription: bool = False) -> dict:
    subscription_query = select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id)
    if lock_subscription:
        subscription_query = subscription_query.with_for_update()
    subscription = db.scalar(subscription_query)
    usage = hosting_resource_usage(db, tenant_id)
    if subscription is None:
        return {"usage": usage, "limits": None, "subscription_status": None}
    plan = db.get(BillingPlan, subscription.plan_id)
    if plan is None or not plan.is_active:
        return {"usage": usage, "limits": None, "subscription_status": str(subscription.status.value)}
    return {
        "usage": usage,
        "limits": _effective_limits(plan),
        "subscription_status": str(subscription.status.value),
        "plan": {
            "id": str(plan.id),
            "code": plan.code,
            "name": plan.name,
            "allow_metered_overages": bool(plan.allow_metered_overages),
            "overage_database_minor": int(plan.overage_database_minor or 0),
            "overage_database_storage_gb_minor": int(plan.overage_database_storage_gb_minor or 0),
            "overage_source_storage_gb_minor": int(plan.overage_source_storage_gb_minor or 0),
        },
    }


def database_allocation_allowed(db: Session, tenant_id: UUID, requested_storage_mb: int) -> tuple[bool, str, dict]:
    meter = hosting_resource_meter(db, tenant_id, lock_subscription=True)
    limits = meter.get("limits")
    if limits is None:
        return False, "Organization has no active hosting package", meter
    usage = meter["usage"]
    requested_bytes = int(requested_storage_mb) * 1024 * 1024
    count_over = usage["database_count"] + 1 > limits["database_count"]
    storage_over = usage["database_storage_bytes"] + requested_bytes > limits["database_storage_bytes"]
    if not count_over and not storage_over:
        return True, "within plan", meter

    plan = meter.get("plan") or {}
    metered = bool(plan.get("allow_metered_overages"))
    count_priced = not count_over or int(plan.get("overage_database_minor") or 0) > 0
    storage_priced = not storage_over or int(plan.get("overage_database_storage_gb_minor") or 0) > 0
    if metered and count_priced and storage_priced:
        return True, "metered overage", meter
    if count_over:
        return False, "Hosted database count limit reached", meter
    return False, "Hosted database storage limit reached", meter


def source_allocation_allowed(db: Session, tenant_id: UUID, requested_bytes: int) -> tuple[bool, str, dict]:
    meter = hosting_resource_meter(db, tenant_id, lock_subscription=True)
    limits = meter.get("limits")
    if limits is None:
        return False, "Organization has no active hosting package", meter
    usage = meter["usage"]
    over = usage["source_storage_bytes"] + int(requested_bytes) > limits["source_storage_bytes"]
    if not over:
        return True, "within plan", meter

    plan = meter.get("plan") or {}
    if bool(plan.get("allow_metered_overages")) and int(plan.get("overage_source_storage_gb_minor") or 0) > 0:
        return True, "metered overage", meter
    return False, "Hosted source storage limit reached", meter

