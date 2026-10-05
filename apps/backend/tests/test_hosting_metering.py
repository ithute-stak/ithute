import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from app.models import BillingPlan, HostingDatabase, HostingSource, SubscriptionStatus, TenantSubscription, UsageSnapshot
from app.services.billing import capture_usage
from app.services.hosting_metering import (
    database_allocation_allowed,
    hosting_resource_meter,
    source_allocation_allowed,
)


def _plan() -> BillingPlan:
    suffix = uuid.uuid4().hex[:10]
    return BillingPlan(
        code=f"meter-{suffix}",
        name="Meter Test",
        currency="LSL",
        monthly_price_minor=1000,
        included_mailboxes=1,
        included_domains=1,
        included_storage_mb=1024,
        max_api_keys=1,
        included_hosted_projects=2,
        hosting_storage_mb=2048,
        hosting_memory_mb_per_project=512,
        hosting_cpu_millicores_per_project=500,
        hosting_pids_per_project=128,
        hosting_database_limit=2,
        hosting_database_storage_mb=1536,
        hosting_source_storage_mb=1024,
    )


def test_hosting_resource_meter_counts_database_and_zip_reservations(db, tenant_admin):
    user, tenant, _ = tenant_admin
    plan = _plan()
    db.add(plan)
    db.flush()
    now = datetime.now(timezone.utc)
    db.add(TenantSubscription(
        tenant_id=tenant.id,
        plan_id=plan.id,
        status=SubscriptionStatus.active,
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
        provider="manual",
    ))
    db.add(HostingDatabase(
        tenant_id=tenant.id,
        engine="postgresql",
        database_name=f"meter_{uuid.uuid4().hex[:8]}",
        username=f"ith_meter_{uuid.uuid4().hex[:12]}",
        encrypted_password="encrypted-test-value",
        internal_port=5432,
        storage_mb=512,
        status="ready",
        operation="none",
        created_by_user_id=user.id,
    ))
    db.add(HostingSource(
        tenant_id=tenant.id,
        source_type="zip",
        original_filename="site.zip",
        upload_object_key=f"hosting/{tenant.id}/{uuid.uuid4()}.zip",
        size_bytes=256 * 1024 * 1024,
        status="ready",
        created_by_user_id=user.id,
    ))
    db.commit()

    try:
        meter = hosting_resource_meter(db, tenant.id)
        assert meter["usage"]["database_count"] == 1
        assert meter["usage"]["database_storage_bytes"] == 512 * 1024 * 1024
        assert meter["usage"]["source_storage_bytes"] == 256 * 1024 * 1024
        assert meter["limits"]["database_count"] == 2
        assert meter["limits"]["database_storage_bytes"] == 1536 * 1024 * 1024
        assert meter["limits"]["source_storage_bytes"] == 1024 * 1024 * 1024

        allowed, _, _ = database_allocation_allowed(db, tenant.id, 512)
        assert allowed is True
        allowed, reason, _ = database_allocation_allowed(db, tenant.id, 1200)
        assert allowed is False
        assert reason == "Hosted database storage limit reached"

        allowed, _, _ = source_allocation_allowed(db, tenant.id, 700 * 1024 * 1024)
        assert allowed is True
        allowed, reason, _ = source_allocation_allowed(db, tenant.id, 900 * 1024 * 1024)
        assert allowed is False
        assert reason == "Hosted source storage limit reached"

        # A plan must explicitly opt in and price each exceeded resource before
        # Ithute permits allocations above the included capacity.
        plan.allow_metered_overages = True
        plan.overage_database_minor = 2500
        plan.overage_database_storage_gb_minor = 1500
        plan.overage_source_storage_gb_minor = 1200
        db.commit()

        allowed, reason, _ = database_allocation_allowed(db, tenant.id, 1200)
        assert allowed is True
        assert reason == "metered overage"
        allowed, reason, _ = source_allocation_allowed(db, tenant.id, 900 * 1024 * 1024)
        assert allowed is True
        assert reason == "metered overage"

        snapshot = capture_usage(db, tenant.id, now, now + timedelta(days=30))
        assert snapshot.hosting_database_count == 1
        assert snapshot.hosting_database_storage_bytes == 512 * 1024 * 1024
        assert snapshot.hosting_source_storage_bytes == 256 * 1024 * 1024
        assert snapshot.api_keys == 0
        assert snapshot.hosted_projects == 0
        assert snapshot.hosting_storage_bytes == 0
    finally:
        db.rollback()
        db.execute(delete(UsageSnapshot).where(UsageSnapshot.tenant_id == tenant.id))
        db.execute(delete(HostingSource).where(HostingSource.tenant_id == tenant.id))
        db.execute(delete(HostingDatabase).where(HostingDatabase.tenant_id == tenant.id))
        db.execute(delete(TenantSubscription).where(TenantSubscription.tenant_id == tenant.id))
        db.execute(delete(BillingPlan).where(BillingPlan.id == plan.id))
        db.commit()
