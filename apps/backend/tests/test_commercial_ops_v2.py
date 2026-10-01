from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import delete

from app.api.v1.commercial_ops_v2 import MonitorCreate
from app.models import BillingInvoice, BillingPlan, SubscriptionStatus, TenantSubscription
from app.models.commercial_ops_v2 import BillingContract
from app.services.billing import assign_subscription
from app.services.commercial_ops_v2 import run_billing_cycle


def test_annual_cycle_applies_setup_fee_once_and_renews_paid_subscription(db, tenant_admin):
    _user, tenant, _membership = tenant_admin
    plan = BillingPlan(
        code=f"v2-{tenant.id.hex[:10]}",
        name="V2 Annual",
        currency="LSL",
        monthly_price_minor=10_000,
        annual_price_minor=100_000,
        setup_fee_minor=7_000,
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
        is_active=True,
    )
    db.add(plan); db.commit(); db.refresh(plan)
    subscription = assign_subscription(db, tenant.id, plan, SubscriptionStatus.active, period_days=30)
    now = datetime.now(timezone.utc)
    subscription.current_period_start = now - timedelta(days=360)
    subscription.current_period_end = now + timedelta(days=5)
    contract = BillingContract(tenant_id=tenant.id, billing_interval="annual", invoice_lead_days=14, grace_days=7)
    db.add(contract); db.commit()

    result = run_billing_cycle(db, now=now)
    assert result["invoices_created"] >= 1
    invoice = db.query(BillingInvoice).filter(BillingInvoice.subscription_id == subscription.id).one()
    assert invoice.subtotal_minor == 107_000
    assert invoice.total_minor == 107_000
    assert contract.setup_fee_applied is True

    # Idempotent: the same period cannot generate a second invoice.
    run_billing_cycle(db, now=now + timedelta(days=1))
    assert db.query(BillingInvoice).filter(BillingInvoice.subscription_id == subscription.id).count() == 1

    invoice.status = "paid"
    invoice.paid_at = now
    subscription.current_period_end = now - timedelta(minutes=1)
    db.commit()
    run_billing_cycle(db, now=now)
    db.refresh(subscription)
    assert subscription.status == SubscriptionStatus.active
    assert subscription.current_period_end > now + timedelta(days=360)

    db.execute(delete(BillingContract).where(BillingContract.tenant_id == tenant.id))
    db.execute(delete(BillingInvoice).where(BillingInvoice.subscription_id == subscription.id))
    db.execute(delete(TenantSubscription).where(TenantSubscription.id == subscription.id))
    db.execute(delete(BillingPlan).where(BillingPlan.id == plan.id))
    db.commit()


def test_monitor_rejects_local_and_private_targets():
    with pytest.raises(ValidationError):
        MonitorCreate(name="Localhost", url="https://127.0.0.1/health")
    with pytest.raises(ValidationError):
        MonitorCreate(name="Docker private", url="https://10.0.0.1/health")
