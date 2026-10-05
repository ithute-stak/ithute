import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from app.models import (
    BillingPlan,
    InfrastructureCommercialProfile,
    InfrastructureServer,
    SubscriptionStatus,
    TenantInfrastructureAllocation,
    TenantSubscription,
)
from app.services.billing import assign_subscription
from app.services.commercial_profitability import customer_profitability, profitability_portfolio


def _plan(code: str) -> BillingPlan:
    return BillingPlan(
        code=code,
        name="Profitability Test",
        currency="LSL",
        monthly_price_minor=10_000,
        annual_price_minor=120_000,
        setup_fee_minor=0,
        included_mailboxes=10,
        included_domains=2,
        included_storage_mb=1024,
        max_api_keys=3,
        included_hosted_projects=1,
        hosting_storage_mb=1024,
        hosting_memory_mb_per_project=512,
        hosting_cpu_millicores_per_project=500,
        hosting_pids_per_project=128,
        hosting_database_limit=2,
        hosting_database_storage_mb=1024,
        hosting_source_storage_mb=1024,
        lifecycle_state="sellable",
        customer_visible=True,
        is_active=True,
    )


def test_customer_profitability_allocates_real_server_cost(db, tenant_admin):
    user, tenant, _membership = tenant_admin
    plan = _plan(f"profit-{tenant.id.hex[:8]}")
    db.add(plan)
    db.commit()
    subscription = assign_subscription(db, tenant.id, plan, SubscriptionStatus.active, period_days=30)

    server = InfrastructureServer(
        name=f"Profit VPS {tenant.id.hex[:6]}",
        hostname=f"profit-{tenant.id.hex[:8]}.example.test",
        region="lesotho",
        provider="test-provider",
        roles_json='["application"]',
        status="active",
        created_by_user_id=user.id,
    )
    db.add(server)
    db.flush()

    profile = InfrastructureCommercialProfile(
        server_id=server.id,
        currency="LSL",
        provider_cost_minor=5_000,
        backup_cost_minor=1_000,
        bandwidth_cost_minor=0,
        other_cost_minor=0,
        total_cpu_millicores=4_000,
        total_memory_mb=8_192,
        total_storage_mb=100_000,
        included_bandwidth_gb=1_000,
        target_margin_bps=3000,
        created_by_user_id=user.id,
        updated_by_user_id=user.id,
    )
    allocation = TenantInfrastructureAllocation(
        tenant_id=tenant.id,
        server_id=server.id,
        allocation_weight=1,
        cpu_millicores=1_000,
        memory_mb=2_048,
        storage_mb=20_000,
        bandwidth_gb=100,
        source="manual",
        active=True,
        created_by_user_id=user.id,
        updated_by_user_id=user.id,
    )
    db.add_all([profile, allocation])
    db.commit()

    try:
        result = customer_profitability(db, tenant.id)
        assert result["commercial"]["estimated_monthly_revenue_minor"] == 10_000
        assert result["commercial"]["allocated_infrastructure_cost_minor"] == 6_000
        assert result["commercial"]["gross_profit_minor"] == 4_000
        assert result["commercial"]["gross_margin_bps"] == 4_000
        assert result["servers"][0]["allocated_cost_minor"] == 6_000
        assert not any(alert["key"] == "infrastructure.unallocated" for alert in result["alerts"])
    finally:
        db.rollback()
        db.execute(delete(TenantInfrastructureAllocation).where(TenantInfrastructureAllocation.tenant_id == tenant.id))
        db.execute(delete(InfrastructureCommercialProfile).where(InfrastructureCommercialProfile.server_id == server.id))
        db.execute(delete(InfrastructureServer).where(InfrastructureServer.id == server.id))
        db.execute(delete(TenantSubscription).where(TenantSubscription.id == subscription.id))
        db.execute(delete(BillingPlan).where(BillingPlan.id == plan.id))
        db.commit()


def test_portfolio_flags_capacity_and_unallocated_cost(db, tenant_admin):
    user, tenant, _membership = tenant_admin
    plan = _plan(f"capacity-{tenant.id.hex[:8]}")
    db.add(plan)
    db.commit()
    subscription = assign_subscription(db, tenant.id, plan, SubscriptionStatus.active, period_days=30)

    server = InfrastructureServer(
        name=f"Capacity VPS {tenant.id.hex[:6]}",
        hostname=f"capacity-{tenant.id.hex[:8]}.example.test",
        region="lesotho",
        provider="test-provider",
        roles_json='["application"]',
        status="active",
        created_by_user_id=user.id,
    )
    idle = InfrastructureServer(
        name=f"Idle VPS {tenant.id.hex[:6]}",
        hostname=f"idle-{tenant.id.hex[:8]}.example.test",
        region="lesotho",
        provider="test-provider",
        roles_json='["application"]',
        status="active",
        created_by_user_id=user.id,
    )
    db.add_all([server, idle])
    db.flush()
    db.add_all([
        InfrastructureCommercialProfile(
            server_id=server.id, currency="LSL", provider_cost_minor=4_000,
            total_cpu_millicores=1_000, total_memory_mb=1_000, total_storage_mb=1_000,
            included_bandwidth_gb=100, target_margin_bps=3000,
            created_by_user_id=user.id, updated_by_user_id=user.id,
        ),
        InfrastructureCommercialProfile(
            server_id=idle.id, currency="LSL", provider_cost_minor=2_000,
            total_cpu_millicores=1_000, total_memory_mb=1_000, total_storage_mb=1_000,
            included_bandwidth_gb=100, target_margin_bps=3000,
            created_by_user_id=user.id, updated_by_user_id=user.id,
        ),
        TenantInfrastructureAllocation(
            tenant_id=tenant.id, server_id=server.id, allocation_weight=1,
            cpu_millicores=900, memory_mb=900, storage_mb=900, bandwidth_gb=90,
            source="manual", active=True, created_by_user_id=user.id, updated_by_user_id=user.id,
        ),
    ])
    db.commit()

    try:
        result = profitability_portfolio(db)
        messages = [row["message"] for row in result["alerts"]]
        assert any("90.0% allocated" in message for message in messages)
        assert any("monthly cost but no customer allocation" in message for message in messages)
        assert result["summary"]["total_server_cost_minor"] >= 6_000
        assert result["summary"]["unallocated_server_cost_minor"] >= 2_000
    finally:
        db.rollback()
        db.execute(delete(TenantInfrastructureAllocation).where(TenantInfrastructureAllocation.tenant_id == tenant.id))
        db.execute(delete(InfrastructureCommercialProfile).where(InfrastructureCommercialProfile.server_id.in_([server.id, idle.id])))
        db.execute(delete(InfrastructureServer).where(InfrastructureServer.id.in_([server.id, idle.id])))
        db.execute(delete(TenantSubscription).where(TenantSubscription.id == subscription.id))
        db.execute(delete(BillingPlan).where(BillingPlan.id == plan.id))
        db.commit()


def test_profitability_routes_are_registered(client):
    routes = set(client.app.openapi().get("paths", {}))
    required = {
        "/api/v1/platform/commercial/profitability",
        "/api/v1/platform/commercial/customers/{tenant_id}",
        "/api/v1/platform/commercial/server-costs",
        "/api/v1/platform/commercial/servers/{server_id}/cost-profile",
        "/api/v1/platform/commercial/allocations",
        "/api/v1/platform/commercial/customers/{tenant_id}/servers/{server_id}/allocation",
    }
    assert not (required - routes)
