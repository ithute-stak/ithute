import uuid

from sqlalchemy import delete

from app.models import BillingPlan


def _plan(code: str, *, visible: bool, lifecycle_state: str = "sellable") -> BillingPlan:
    return BillingPlan(
        code=code,
        name=f"Catalog test {code}",
        currency="LSL",
        monthly_price_minor=10000,
        annual_price_minor=120000,
        setup_fee_minor=0,
        included_mailboxes=18,
        included_domains=1,
        included_storage_mb=36864,
        max_api_keys=3,
        included_hosted_projects=1,
        hosting_storage_mb=2048,
        hosting_memory_mb_per_project=512,
        hosting_cpu_millicores_per_project=500,
        hosting_pids_per_project=128,
        hosting_database_limit=2,
        hosting_database_storage_mb=2048,
        hosting_source_storage_mb=2048,
        customer_visible=visible,
        featured=False,
        sort_order=9990,
        is_active=True,
        lifecycle_state=lifecycle_state,
    )


def test_public_hosting_pricing_requires_sellable_lifecycle(client, db):
    suffix = uuid.uuid4().hex[:10]
    hidden = _plan(f"hidden-{suffix}", visible=False)
    legacy_but_visible = _plan(f"legacy-visible-{suffix}", visible=True, lifecycle_state="legacy")
    visible = _plan(f"owner-visible-{suffix}", visible=True, lifecycle_state="sellable")
    db.add_all([hidden, legacy_but_visible, visible])
    db.commit()

    try:
        for endpoint in ("/api/v1/public/hosting-pricing", "/api/v1/public/pricing"):
            response = client.get(endpoint)
            assert response.status_code == 200
            items = response.json()["items"]
            codes = {item["code"] for item in items}
            assert hidden.code not in codes
            assert legacy_but_visible.code not in codes
            assert visible.code in codes
            returned = next(item for item in items if item["code"] == visible.code)
            assert returned["annual_price_minor"] == 120000
            assert returned["included_mailboxes"] == 18
            assert returned["hosting_storage_mb"] == 2048
            assert returned["hosting_database_limit"] == 2
    finally:
        db.execute(delete(BillingPlan).where(BillingPlan.id.in_([hidden.id, legacy_but_visible.id, visible.id])))
        db.commit()
