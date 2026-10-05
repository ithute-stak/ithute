import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import delete

from app.api.v1.commercial_ops_v2 import MonitorCreate
from app.models import BillingAddon, BillingInvoice, BillingPlan, HostingDatabase, SubscriptionStatus, TenantAddon, TenantSubscription, UsageSnapshot
from app.models.commercial_ops_v2 import BillingContract
from app.services.billing import assign_subscription
from app.services.catalog_entitlements import rebuild_effective_plan
from app.services.commercial_ops_v2 import generate_contract_invoice, request_plan_change, run_billing_cycle


def make_plan(code: str, *, annual: int = 100_000, storage: int = 2048, projects: int = 1) -> BillingPlan:
    return BillingPlan(
        code=code,
        name=code,
        currency="LSL",
        monthly_price_minor=10_000,
        annual_price_minor=annual,
        setup_fee_minor=7_000,
        included_mailboxes=18,
        included_domains=1,
        included_storage_mb=36_864,
        max_api_keys=3,
        included_hosted_projects=projects,
        hosting_storage_mb=storage,
        hosting_memory_mb_per_project=512,
        hosting_cpu_millicores_per_project=500,
        hosting_pids_per_project=128,
        hosting_database_limit=2,
        hosting_database_storage_mb=2048,
        hosting_source_storage_mb=2048,
        lifecycle_state="sellable",
        customer_visible=True,
        is_active=True,
    )


def test_annual_cycle_applies_plan_and_addon_setup_fee_once_and_renews(db, tenant_admin):
    _user, tenant, _membership = tenant_admin
    plan = make_plan(f"v2-{tenant.id.hex[:10]}")
    db.add(plan); db.commit(); db.refresh(plan)
    subscription = assign_subscription(db, tenant.id, plan, SubscriptionStatus.active, period_days=30)

    addon = BillingAddon(
        code=f"addon-{tenant.id.hex[:10]}", name="Extra capacity", description="", currency="LSL",
        monthly_price_minor=1_000, annual_price_minor=10_000, setup_fee_minor=2_000,
        resource_key="hosting_storage_mb", amount_per_quantity=1024, unit_label="GB",
        max_quantity=10, customer_visible=True, is_active=True, sort_order=10,
    )
    db.add(addon); db.flush()
    assignment = TenantAddon(tenant_id=tenant.id, addon_id=addon.id, quantity=1, status="active", activated_at=datetime.now(timezone.utc))
    db.add(assignment); db.flush()
    rebuild_effective_plan(db, tenant.id)

    now = datetime.now(timezone.utc)
    subscription.current_period_start = now - timedelta(days=360)
    subscription.current_period_end = now + timedelta(days=5)
    contract = BillingContract(tenant_id=tenant.id, billing_interval="annual", invoice_lead_days=14, grace_days=7)
    db.add(contract); db.commit()

    result = run_billing_cycle(db, now=now)
    assert result["invoices_created"] >= 1
    invoice = db.query(BillingInvoice).filter(BillingInvoice.subscription_id == subscription.id).one()
    assert invoice.subtotal_minor == 119_000  # 100k plan + 10k add-on + 7k plan setup + 2k add-on setup
    assert contract.setup_fee_applied is True
    db.refresh(assignment)
    assert assignment.setup_fee_applied is True

    run_billing_cycle(db, now=now + timedelta(days=1))
    assert db.query(BillingInvoice).filter(BillingInvoice.subscription_id == subscription.id).count() == 1

    invoice.status = "paid"
    invoice.paid_at = now
    subscription.current_period_end = now - timedelta(minutes=1)
    invoice.period_end = subscription.current_period_end
    db.commit()
    run_billing_cycle(db, now=now)
    db.refresh(subscription)
    db.refresh(assignment)
    assert subscription.status == SubscriptionStatus.active
    assert subscription.current_period_end > now + timedelta(days=360)
    assert assignment.current_period_end == subscription.current_period_end

    db.execute(delete(BillingContract).where(BillingContract.tenant_id == tenant.id))
    db.execute(delete(BillingInvoice).where(BillingInvoice.subscription_id == subscription.id))
    db.execute(delete(TenantAddon).where(TenantAddon.tenant_id == tenant.id))
    db.execute(delete(TenantSubscription).where(TenantSubscription.id == subscription.id))
    db.execute(delete(BillingAddon).where(BillingAddon.id == addon.id))
    db.execute(delete(BillingPlan).where(BillingPlan.code.like(f"effective-{tenant.id.hex[:32]}")))
    db.execute(delete(BillingPlan).where(BillingPlan.id == plan.id))
    db.commit()


def test_capacity_upgrade_is_immediate_but_downgrade_waits_for_period_end(db, tenant_admin):
    _user, tenant, _membership = tenant_admin
    base = make_plan(f"base-{tenant.id.hex[:8]}", storage=2048, projects=1)
    upgrade = make_plan(f"up-{tenant.id.hex[:8]}", annual=150_000, storage=8192, projects=3)
    downgrade = make_plan(f"down-{tenant.id.hex[:8]}", annual=80_000, storage=1024, projects=1)
    db.add_all([base, upgrade, downgrade]); db.commit()
    subscription = assign_subscription(db, tenant.id, base, SubscriptionStatus.active, period_days=30)
    subscription.base_plan_id = base.id
    db.commit()

    result = request_plan_change(db, subscription, upgrade)
    assert result["mode"] == "immediate"
    assert subscription.base_plan_id == upgrade.id
    assert subscription.pending_plan_id is None

    result = request_plan_change(db, subscription, downgrade)
    assert result["mode"] == "period_end"
    assert subscription.base_plan_id == upgrade.id
    assert subscription.pending_plan_id == downgrade.id
    assert subscription.pending_plan_effective_at == subscription.current_period_end

    db.execute(delete(TenantSubscription).where(TenantSubscription.id == subscription.id))
    db.execute(delete(BillingPlan).where(BillingPlan.code.like(f"effective-{tenant.id.hex[:32]}")))
    db.execute(delete(BillingPlan).where(BillingPlan.id.in_([base.id, upgrade.id, downgrade.id])))
    db.commit()


def test_monitor_rejects_local_and_private_targets():
    with pytest.raises(ValidationError):
        MonitorCreate(name="Localhost", url="https://127.0.0.1/health")
    with pytest.raises(ValidationError):
        MonitorCreate(name="Docker private", url="https://10.0.0.1/health")


def test_recurring_invoice_includes_priced_metered_overage(db, tenant_admin):
    user, tenant, _membership = tenant_admin
    plan = make_plan(f"overage-{tenant.id.hex[:8]}", annual=100_000, storage=2048, projects=1)
    plan.setup_fee_minor = 0
    plan.hosting_database_limit = 0
    plan.hosting_database_storage_mb = 0
    plan.allow_metered_overages = True
    plan.overage_database_minor = 2_500
    db.add(plan)
    db.commit()
    db.refresh(plan)

    subscription = assign_subscription(db, tenant.id, plan, SubscriptionStatus.active, period_days=30)
    database = HostingDatabase(
        tenant_id=tenant.id,
        engine="postgresql",
        database_name=f"overage_{tenant.id.hex[:8]}",
        username=f"ith_overage_{tenant.id.hex[:10]}",
        encrypted_password="encrypted-test-value",
        internal_port=5432,
        storage_mb=0,
        status="ready",
        operation="none",
        created_by_user_id=user.id,
    )
    db.add(database)
    contract = BillingContract(
        tenant_id=tenant.id,
        billing_interval="monthly",
        auto_renew=True,
        invoice_lead_days=14,
        grace_days=7,
        setup_fee_applied=True,
    )
    db.add(contract)
    db.commit()

    try:
        invoice = generate_contract_invoice(db, subscription, contract)
        assert invoice.base_amount_minor == 10_000
        assert invoice.overage_amount_minor == 2_500
        assert invoice.subtotal_minor == 12_500
        assert invoice.total_minor == 12_500
        breakdown = json.loads(invoice.usage_breakdown_json)
        assert breakdown["fully_priced"] is True
        database_line = next(item for item in breakdown["items"] if item["metric"] == "hosting_database_count")
        assert database_line == {
            "metric": "hosting_database_count",
            "units": 1,
            "rate_minor": 2_500,
            "amount_minor": 2_500,
        }
    finally:
        db.rollback()
        db.execute(delete(BillingInvoice).where(BillingInvoice.subscription_id == subscription.id))
        db.execute(delete(UsageSnapshot).where(UsageSnapshot.tenant_id == tenant.id))
        db.execute(delete(HostingDatabase).where(HostingDatabase.tenant_id == tenant.id))
        db.execute(delete(BillingContract).where(BillingContract.tenant_id == tenant.id))
        db.execute(delete(TenantSubscription).where(TenantSubscription.id == subscription.id))
        db.execute(delete(BillingPlan).where(BillingPlan.id == plan.id))
        db.commit()
