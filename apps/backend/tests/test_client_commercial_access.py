from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import delete

from app.api.deps import require_tenant_permission
from app.models import BillingPlan, SubscriptionStatus, TenantSubscription


def _plan(code: str) -> BillingPlan:
    return BillingPlan(
        code=code,
        name="Client access test",
        currency="LSL",
        monthly_price_minor=10_000,
        annual_price_minor=100_000,
        setup_fee_minor=0,
        included_mailboxes=18,
        included_domains=1,
        included_storage_mb=36_864,
        max_api_keys=3,
        included_hosted_projects=1,
        hosting_storage_mb=2048,
        hosting_memory_mb_per_project=512,
        hosting_cpu_millicores_per_project=500,
        hosting_pids_per_project=128,
        hosting_database_limit=2,
        hosting_database_storage_mb=2048,
        hosting_source_storage_mb=2048,
        customer_visible=False,
        lifecycle_state="hidden",
        is_active=True,
    )


def test_service_mutations_follow_subscription_state_but_billing_remains_available(db, tenant_admin):
    user, tenant, _membership = tenant_admin
    plan = _plan(f"access-{tenant.id.hex[:10]}")
    db.add(plan)
    db.flush()
    now = datetime.now(timezone.utc)
    subscription = TenantSubscription(
        tenant_id=tenant.id,
        plan_id=plan.id,
        base_plan_id=plan.id,
        status=SubscriptionStatus.active,
        current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=29),
    )
    tenant.requested_plan_code = plan.code
    db.add(subscription)
    db.commit()

    try:
        # Active customers may manage their provisioned services.
        assert require_tenant_permission(tenant.id, "hosting.manage", db, user) is not None

        # Read access remains available even if the subscription is later inactive.
        subscription.status = SubscriptionStatus.canceled
        db.commit()
        assert require_tenant_permission(tenant.id, "hosting.read", db, user) is not None

        # Billing remains usable for recovery, but service mutations are blocked.
        assert require_tenant_permission(tenant.id, "billing.manage", db, user) is not None
        with pytest.raises(HTTPException) as canceled:
            require_tenant_permission(tenant.id, "hosting.manage", db, user)
        assert canceled.value.status_code == 402
        assert canceled.value.detail["code"] == "SUBSCRIPTION_INACTIVE"

        # Past-due customers keep mutation access during the contractual grace window.
        subscription.status = SubscriptionStatus.past_due
        subscription.grace_ends_at = now + timedelta(days=2)
        db.commit()
        assert require_tenant_permission(tenant.id, "dns.manage", db, user) is not None

        # Once grace expires, DNS/mail/hosting changes are centrally blocked.
        subscription.grace_ends_at = now - timedelta(minutes=1)
        db.commit()
        with pytest.raises(HTTPException) as expired:
            require_tenant_permission(tenant.id, "dns.manage", db, user)
        assert expired.value.status_code == 402
        assert expired.value.detail["code"] == "SUBSCRIPTION_GRACE_EXPIRED"
    finally:
        db.execute(delete(TenantSubscription).where(TenantSubscription.id == subscription.id))
        db.execute(delete(BillingPlan).where(BillingPlan.id == plan.id))
        tenant.requested_plan_code = None
        db.commit()
