import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, text

from app.models import BillingAddon, BillingPlan, Tenant, TenantAddon, TenantSubscription
from app.services.catalog_entitlements import rebuild_effective_plan


def test_seeded_start_package_is_customer_visible(client):
    response = client.get("/api/v1/public/pricing")
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    start = next(item for item in items if item["code"] == "start")
    assert start["hosting_storage_mb"] == 2048
    assert start["included_mailboxes"] == 18
    assert start["included_hosted_projects"] == 1
    assert start["hosting_database_limit"] == 2
    assert start["annual_price_minor"] is not None
    assert all(not item["code"].startswith("effective-") for item in items)


def test_pending_addon_does_not_change_entitlements_but_active_addon_does(db):
    base = db.scalar(select(BillingPlan).where(BillingPlan.code == "start"))
    addon = db.scalar(select(BillingAddon).where(BillingAddon.code == "extra-mail-10"))
    assert base is not None and addon is not None

    tenant = Tenant(name="Addon Test", slug=f"addon-{uuid.uuid4().hex[:12]}")
    db.add(tenant)
    db.flush()
    now = datetime.now(timezone.utc)
    subscription = TenantSubscription(
        tenant_id=tenant.id,
        plan_id=base.id,
        status="active",
        current_period_start=now,
        current_period_end=now + timedelta(days=365),
    )
    db.add(subscription)
    db.flush()
    db.execute(text("UPDATE tenant_subscriptions SET base_plan_id = :plan WHERE id = :id"), {"plan": str(base.id), "id": str(subscription.id)})

    assignment = TenantAddon(tenant_id=tenant.id, addon_id=addon.id, quantity=2, status="pending")
    db.add(assignment)
    db.commit()

    pending = rebuild_effective_plan(db, tenant.id)
    db.commit()
    assert pending is not None
    assert pending.id == base.id
    db.refresh(subscription)
    assert subscription.plan_id == base.id

    assignment.status = "active"
    assignment.activated_at = now
    db.commit()
    effective = rebuild_effective_plan(db, tenant.id)
    db.commit()
    assert effective is not None
    assert effective.code.startswith("effective-")
    assert effective.customer_visible is False
    assert effective.included_mailboxes == base.included_mailboxes + 20
    db.refresh(subscription)
    assert subscription.plan_id == effective.id

    assignment.status = "canceled"
    db.commit()
    restored = rebuild_effective_plan(db, tenant.id)
    db.commit()
    assert restored is not None and restored.id == base.id
    db.refresh(subscription)
    assert subscription.plan_id == base.id

    db.execute(delete(TenantAddon).where(TenantAddon.tenant_id == tenant.id))
    db.execute(delete(TenantSubscription).where(TenantSubscription.tenant_id == tenant.id))
    db.execute(delete(BillingPlan).where(BillingPlan.code == f"effective-{tenant.id.hex[:32]}"))
    db.execute(delete(Tenant).where(Tenant.id == tenant.id))
    db.commit()
