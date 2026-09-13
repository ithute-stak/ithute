import uuid

from sqlalchemy import delete

from app.models import AuditLog, BillingPlan

PASSWORD = "Phase1-Test-Password!"


def login(client, email: str):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text


def test_default_monthly_commercial_catalog(client):
    response = client.get("/api/v1/public/hosting-pricing")
    assert response.status_code == 200, response.text
    plans = {item["code"]: item for item in response.json()["items"]}

    assert [plans[code]["monthly_price_minor"] for code in ("starter", "grow", "business", "professional", "enterprise")] == [
        18_500,
        29_500,
        49_500,
        79_500,
        150_000,
    ]
    assert plans["starter"]["name"] == "Ithute Start"
    assert plans["starter"]["minimum_term_months"] == 12
    assert plans["starter"]["includes_website_design"] is True
    assert plans["starter"]["includes_logo_design"] is True
    assert plans["starter"]["includes_page_headers_footers"] is True
    assert plans["business"]["includes_company_profile"] is True
    assert plans["business"]["includes_business_templates"] is True
    assert plans["professional"]["support_level"] == "priority"
    assert plans["enterprise"]["price_from"] is True
    assert plans["enterprise"]["support_level"] == "dedicated"

    # Repricing must not shrink the original three packages' hosting capacity.
    assert plans["starter"]["included_mailboxes"] == 10
    assert plans["starter"]["hosting_storage_mb"] == 1024
    assert plans["business"]["included_hosted_projects"] == 3
    assert plans["business"]["hosting_storage_mb"] == 5120
    assert plans["enterprise"]["included_hosted_projects"] == 10
    assert plans["enterprise"]["hosting_storage_mb"] == 10240


def test_platform_owner_can_create_publish_and_update_package(client, db, platform_owner):
    login(client, platform_owner.email)
    code = f"custom-{uuid.uuid4().hex[:10]}"
    created = client.post(
        "/api/v1/platform/billing/plans",
        json={
            "code": code,
            "name": "Custom Growth",
            "currency": "LSL",
            "monthly_price_minor": 225000,
            "included_mailboxes": 75,
            "included_domains": 15,
            "included_storage_mb": 375000,
            "max_api_keys": 12,
            "product_category": "Branding & Corporate Identity",
            "description": "Custom digital and branding package",
            "website_pages": 6,
            "includes_website_design": True,
            "includes_logo_design": True,
            "includes_brand_guide": True,
            "includes_letterhead": True,
            "includes_page_headers_footers": True,
            "included_revisions": 3,
            "content_updates_per_month": 2,
            "support_level": "priority",
            "minimum_term_months": 12,
            "is_active": True,
        },
    )
    assert created.status_code == 201, created.text
    plan = created.json()
    plan_id = plan["id"]
    assert plan["code"] == code
    assert plan["included_mailboxes"] == 75
    assert plan["includes_logo_design"] is True
    assert plan["minimum_term_months"] == 12

    public = client.get("/api/v1/public/hosting-pricing")
    assert public.status_code == 200, public.text
    published = {item["code"]: item for item in public.json()["items"]}
    assert code in published
    assert published[code]["included_storage_mb"] == 375000
    assert published[code]["product_category"] == "Branding & Corporate Identity"

    updated = client.patch(
        f"/api/v1/platform/billing/plans/{plan_id}",
        json={
            "monthly_price_minor": 239000,
            "included_mailboxes": 80,
            "max_api_keys": 15,
            "includes_company_profile": True,
            "support_level": "dedicated",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["monthly_price_minor"] == 239000
    assert updated.json()["included_mailboxes"] == 80
    assert updated.json()["max_api_keys"] == 15
    assert updated.json()["includes_company_profile"] is True
    assert updated.json()["support_level"] == "dedicated"

    db.execute(delete(AuditLog).where(AuditLog.resource_type == "billing_plan", AuditLog.resource_id == plan_id))
    db.execute(delete(BillingPlan).where(BillingPlan.id == uuid.UUID(plan_id)))
    db.commit()


def test_non_owner_cannot_manage_package_catalog(client, tenant_admin):
    user, _, _ = tenant_admin
    login(client, user.email)
    response = client.get("/api/v1/platform/billing/plans")
    assert response.status_code == 403, response.text
