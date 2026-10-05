import uuid

from sqlalchemy import delete

from app.models import AuditLog, BillingPlan

PASSWORD = "Phase1-Test-Password!"


def login(client, email: str):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text


def test_default_public_catalog_is_one_canonical_hosting_family(client):
    response = client.get("/api/v1/public/hosting-pricing")
    assert response.status_code == 200, response.text
    plans = {item["code"]: item for item in response.json()["items"]}

    canonical = (
        "ithute-start",
        "ithute-grow",
        "ithute-business",
        "ithute-professional",
        "ithute-enterprise",
        "ithute-ultimate",
    )
    assert [plans[code]["monthly_price_minor"] for code in canonical] == [
        7_000,
        14_000,
        24_000,
        42_000,
        75_000,
        125_000,
    ]
    assert [plans[code]["annual_price_minor"] for code in canonical] == [
        84_000,
        168_000,
        288_000,
        504_000,
        900_000,
        1_500_000,
    ]

    for legacy in ("starter", "grow", "business", "professional", "enterprise"):
        assert legacy not in plans

    start = plans["ithute-start"]
    assert start["name"] == "Ithute Start"
    assert start["included_mailboxes"] == 18
    assert start["included_hosted_projects"] == 1
    assert start["hosting_storage_mb"] == 2048
    assert start["hosting_database_limit"] == 2
    assert start["setup_fee_minor"] == 10_000

    business = plans["ithute-business"]
    assert business["featured"] is True
    assert business["support_level"] == "priority"

    enterprise = plans["ithute-enterprise"]
    assert enterprise["included_mailboxes"] == 500
    assert enterprise["included_hosted_projects"] == 30
    assert enterprise["support_level"] == "dedicated"


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
            "allow_metered_overages": True,
            "overage_mailbox_minor": 500,
            "overage_domain_minor": 1000,
            "overage_storage_gb_minor": 250,
            "overage_api_key_minor": 300,
            "overage_hosted_project_minor": 2500,
            "overage_hosting_storage_gb_minor": 400,
            "overage_database_minor": 1500,
            "overage_database_storage_gb_minor": 350,
            "overage_source_storage_gb_minor": 200,
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
    assert plan["allow_metered_overages"] is True
    assert plan["overage_mailbox_minor"] == 500
    assert plan["overage_database_minor"] == 1500
    assert plan["includes_logo_design"] is True
    assert plan["minimum_term_months"] == 12

    public = client.get("/api/v1/public/hosting-pricing")
    assert public.status_code == 200, public.text
    published = {item["code"]: item for item in public.json()["items"]}
    assert code in published
    assert published[code]["included_storage_mb"] == 375000
    assert published[code]["allow_metered_overages"] is True
    assert published[code]["overage_storage_gb_minor"] == 250
    assert published[code]["product_category"] == "Branding & Corporate Identity"

    updated = client.patch(
        f"/api/v1/platform/billing/plans/{plan_id}",
        json={
            "monthly_price_minor": 239000,
            "included_mailboxes": 80,
            "max_api_keys": 15,
            "overage_mailbox_minor": 650,
            "overage_database_minor": 1800,
            "includes_company_profile": True,
            "support_level": "dedicated",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["monthly_price_minor"] == 239000
    assert updated.json()["included_mailboxes"] == 80
    assert updated.json()["max_api_keys"] == 15
    assert updated.json()["overage_mailbox_minor"] == 650
    assert updated.json()["overage_database_minor"] == 1800
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
