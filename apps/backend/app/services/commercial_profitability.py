from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    BillingContract,
    BillingPlan,
    Domain,
    HostingDatabase,
    HostingProject,
    InfrastructureCommercialProfile,
    InfrastructureServer,
    Mailbox,
    SubscriptionStatus,
    Tenant,
    TenantInfrastructureAllocation,
    TenantSubscription,
)
from app.services.billing import calculate_overage, tenant_usage


def _monthly_plan_revenue(plan: BillingPlan, contract: BillingContract | None) -> int:
    if contract and contract.billing_interval == "annual":
        annual = int(plan.annual_price_minor if plan.annual_price_minor is not None else plan.monthly_price_minor * 12)
        return annual // 12
    return int(plan.monthly_price_minor)


def _server_monthly_cost(profile: InfrastructureCommercialProfile | None) -> int:
    if profile is None:
        return 0
    return sum(
        max(0, int(value or 0))
        for value in (
            profile.provider_cost_minor,
            profile.backup_cost_minor,
            profile.bandwidth_cost_minor,
            profile.other_cost_minor,
        )
    )


def _allocation_costs(db: Session) -> tuple[dict[UUID, int], dict[UUID, dict], list[dict]]:
    tenant_costs: dict[UUID, int] = defaultdict(int)
    tenant_server_details: dict[UUID, list[dict]] = defaultdict(list)
    server_rows: list[dict] = []

    servers = db.scalars(select(InfrastructureServer).order_by(InfrastructureServer.name)).all()
    for server in servers:
        profile = db.scalar(
            select(InfrastructureCommercialProfile).where(InfrastructureCommercialProfile.server_id == server.id)
        )
        allocations = db.scalars(
            select(TenantInfrastructureAllocation).where(
                TenantInfrastructureAllocation.server_id == server.id,
                TenantInfrastructureAllocation.active.is_(True),
            )
        ).all()
        total_weight = sum(max(1, int(row.allocation_weight or 1)) for row in allocations)
        monthly_cost = _server_monthly_cost(profile)

        allocated_cpu = sum(max(0, int(row.cpu_millicores or 0)) for row in allocations)
        allocated_memory = sum(max(0, int(row.memory_mb or 0)) for row in allocations)
        allocated_storage = sum(max(0, int(row.storage_mb or 0)) for row in allocations)
        allocated_bandwidth = sum(max(0, int(row.bandwidth_gb or 0)) for row in allocations)

        capacity = {
            "cpu_millicores": int(profile.total_cpu_millicores or 0) if profile else 0,
            "memory_mb": int(profile.total_memory_mb or 0) if profile else 0,
            "storage_mb": int(profile.total_storage_mb or 0) if profile else 0,
            "bandwidth_gb": int(profile.included_bandwidth_gb or 0) if profile else 0,
        }
        allocated = {
            "cpu_millicores": allocated_cpu,
            "memory_mb": allocated_memory,
            "storage_mb": allocated_storage,
            "bandwidth_gb": allocated_bandwidth,
        }

        utilization: dict[str, float | None] = {}
        for key, total in capacity.items():
            utilization[key] = round((allocated[key] / total) * 100, 1) if total > 0 else None

        allocated_cost = 0
        remaining = monthly_cost
        ordered = sorted(allocations, key=lambda row: str(row.tenant_id))
        for index, allocation in enumerate(ordered):
            share = 0
            if total_weight > 0 and monthly_cost > 0:
                if index == len(ordered) - 1:
                    share = remaining
                else:
                    share = (monthly_cost * max(1, int(allocation.allocation_weight or 1))) // total_weight
                    remaining -= share
            allocated_cost += share
            tenant_costs[allocation.tenant_id] += share
            detail = {
                "server_id": str(server.id),
                "server_name": server.name,
                "hostname": server.hostname,
                "provider": server.provider,
                "allocation_weight": int(allocation.allocation_weight or 1),
                "allocated_cost_minor": share,
                "target_margin_bps": int(profile.target_margin_bps or 3000) if profile else 3000,
                "cost_profile_configured": profile is not None,
                "cpu_millicores": int(allocation.cpu_millicores or 0),
                "memory_mb": int(allocation.memory_mb or 0),
                "storage_mb": int(allocation.storage_mb or 0),
                "bandwidth_gb": int(allocation.bandwidth_gb or 0),
                "source": allocation.source,
            }
            tenant_server_details[allocation.tenant_id].append(detail)

        server_rows.append(
            {
                "server_id": str(server.id),
                "name": server.name,
                "hostname": server.hostname,
                "provider": server.provider,
                "region": server.region,
                "status": server.status,
                "currency": profile.currency if profile else "LSL",
                "monthly_cost_minor": monthly_cost,
                "allocated_cost_minor": allocated_cost,
                "unallocated_cost_minor": max(0, monthly_cost - allocated_cost),
                "allocation_count": len(allocations),
                "capacity": capacity,
                "allocated": allocated,
                "utilization": utilization,
                "target_margin_bps": int(profile.target_margin_bps or 3000) if profile else 3000,
                "cost_profile_configured": profile is not None,
            }
        )

    return dict(tenant_costs), dict(tenant_server_details), server_rows


def customer_profitability(
    db: Session,
    tenant_id: UUID,
    *,
    precomputed_costs: dict[UUID, int] | None = None,
    precomputed_servers: dict[UUID, list[dict]] | None = None,
) -> dict:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise ValueError("Tenant not found")

    subscription = db.scalar(select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id))
    usage = tenant_usage(db, tenant_id)
    recurring_minor = 0
    overage = None
    plan_name = None
    subscription_status = None

    if subscription is not None:
        subscription_status = subscription.status.value
        plan = db.get(BillingPlan, subscription.plan_id)
        if plan is not None:
            plan_name = plan.name
            contract = db.scalar(select(BillingContract).where(BillingContract.tenant_id == tenant_id))
            recurring_minor = _monthly_plan_revenue(plan, contract)
            overage = calculate_overage(plan, usage)

    estimated_overage_minor = int((overage or {}).get("estimated_minor") or 0)
    estimated_revenue_minor = recurring_minor + estimated_overage_minor

    if precomputed_costs is None or precomputed_servers is None:
        precomputed_costs, precomputed_servers, _ = _allocation_costs(db)
    allocated_cost_minor = int(precomputed_costs.get(tenant_id, 0))
    gross_profit_minor = estimated_revenue_minor - allocated_cost_minor
    margin_bps = (
        round((gross_profit_minor / estimated_revenue_minor) * 10000)
        if estimated_revenue_minor > 0
        else 0
    )

    domains = db.scalar(select(func.count(Domain.id)).where(Domain.tenant_id == tenant_id)) or 0
    mailboxes = db.scalar(select(func.count(Mailbox.id)).where(Mailbox.tenant_id == tenant_id)) or 0
    projects = db.scalar(select(func.count(HostingProject.id)).where(HostingProject.tenant_id == tenant_id)) or 0
    databases = db.scalar(select(func.count(HostingDatabase.id)).where(HostingDatabase.tenant_id == tenant_id)) or 0

    alerts: list[dict] = []
    if subscription is None:
        alerts.append({"severity": "high", "key": "subscription.missing", "message": "Customer has no subscription."})
    elif subscription.status == SubscriptionStatus.past_due:
        alerts.append({"severity": "high", "key": "billing.past_due", "message": "Subscription is past due."})
    elif subscription.status == SubscriptionStatus.canceled:
        alerts.append({"severity": "high", "key": "billing.canceled", "message": "Subscription is canceled."})

    if overage and overage.get("unpriced_metrics"):
        alerts.append(
            {
                "severity": "high",
                "key": "billing.unpriced_overage",
                "message": f"Unpriced excess usage: {', '.join(overage['unpriced_metrics'])}.",
            }
        )

    server_allocations = precomputed_servers.get(tenant_id, [])
    target_margin_bps = max(
        [int(item.get("target_margin_bps") or 3000) for item in server_allocations] or [3000]
    )
    if estimated_revenue_minor > 0 and margin_bps < target_margin_bps:
        alerts.append(
            {
                "severity": "high" if margin_bps < max(1000, target_margin_bps // 2) else "medium",
                "key": "margin.low",
                "message": f"Estimated gross margin is {margin_bps / 100:.1f}% against a {target_margin_bps / 100:.1f}% target.",
            }
        )
    if not server_allocations:
        alerts.append(
            {
                "severity": "medium",
                "key": "infrastructure.unallocated",
                "message": "No infrastructure cost allocation is assigned to this customer.",
            }
        )

    return {
        "tenant": {"id": str(tenant.id), "name": tenant.name, "slug": tenant.slug},
        "subscription": {
            "status": subscription_status,
            "plan_name": plan_name,
        },
        "resources": {
            "domains": int(domains),
            "mailboxes": int(mailboxes),
            "hosted_projects": int(projects),
            "databases": int(databases),
            "mailbox_storage_bytes": int(usage["allocated_storage_bytes"]),
            "hosting_storage_bytes": int(usage["hosting_storage_bytes"]),
            "database_storage_bytes": int(usage["hosting_database_storage_bytes"]),
            "source_storage_bytes": int(usage["hosting_source_storage_bytes"]),
        },
        "commercial": {
            "currency": "LSL",
            "recurring_revenue_minor": recurring_minor,
            "estimated_overage_minor": estimated_overage_minor,
            "estimated_monthly_revenue_minor": estimated_revenue_minor,
            "allocated_infrastructure_cost_minor": allocated_cost_minor,
            "gross_profit_minor": gross_profit_minor,
            "gross_margin_bps": margin_bps,
        },
        "overage": overage,
        "servers": precomputed_servers.get(tenant_id, []),
        "alerts": alerts,
    }


def profitability_portfolio(db: Session) -> dict:
    tenant_costs, tenant_servers, servers = _allocation_costs(db)
    tenants = db.scalars(select(Tenant).order_by(Tenant.name)).all()
    customers = [
        customer_profitability(
            db,
            tenant.id,
            precomputed_costs=tenant_costs,
            precomputed_servers=tenant_servers,
        )
        for tenant in tenants
    ]

    revenue = sum(item["commercial"]["estimated_monthly_revenue_minor"] for item in customers)
    cost = sum(item["commercial"]["allocated_infrastructure_cost_minor"] for item in customers)
    server_cost = sum(item["monthly_cost_minor"] for item in servers)
    gross_profit = revenue - cost
    margin_bps = round((gross_profit / revenue) * 10000) if revenue > 0 else 0

    alerts: list[dict] = []
    for server in servers:
        if server["monthly_cost_minor"] > 0 and server["allocation_count"] == 0:
            alerts.append(
                {
                    "severity": "medium",
                    "key": "server.unallocated_cost",
                    "server_id": server["server_id"],
                    "message": f"{server['name']} has monthly cost but no customer allocation.",
                }
            )
        for metric, percent in server["utilization"].items():
            if percent is not None and percent >= 80:
                alerts.append(
                    {
                        "severity": "high" if percent >= 90 else "medium",
                        "key": "server.capacity",
                        "server_id": server["server_id"],
                        "message": f"{server['name']} {metric.replace('_', ' ')} is {percent:.1f}% allocated.",
                    }
                )

    for customer in customers:
        for alert in customer["alerts"]:
            alerts.append({**alert, "tenant_id": customer["tenant"]["id"], "tenant_name": customer["tenant"]["name"]})

    customers.sort(
        key=lambda item: (
            item["commercial"]["gross_margin_bps"],
            item["commercial"]["estimated_monthly_revenue_minor"],
        )
    )

    return {
        "currency": "LSL",
        "summary": {
            "estimated_mrr_minor": revenue,
            "allocated_infrastructure_cost_minor": cost,
            "total_server_cost_minor": server_cost,
            "unallocated_server_cost_minor": max(0, server_cost - cost),
            "gross_profit_minor": gross_profit,
            "gross_margin_bps": margin_bps,
            "customers": len(customers),
            "servers": len(servers),
            "alerts": len(alerts),
        },
        "customers": customers,
        "servers": servers,
        "alerts": alerts,
    }
