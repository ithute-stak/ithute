import uuid

from sqlalchemy import delete

from app.models import AuditLog, BillingPlan

PASSWORD = "Phase1-Test-Password!"


def login(client, email: str):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text


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
            "is_active": True,
        },
    )
    assert created.status_code == 201, created.text
    plan = created.json()
    plan_id = plan["id"]
    assert plan["code"] == code
    assert plan["included_mailboxes"] == 75

    public = client.get("/api/v1/public/pricing")
    assert public.status_code == 200, public.text
    published = {item["code"]: item for item in public.json()["items"]}
    assert code in published
    assert published[code]["included_storage_mb"] == 375000

    updated = client.patch(
        f"/api/v1/platform/billing/plans/{plan_id}",
        json={"monthly_price_minor": 239000, "included_mailboxes": 80, "max_api_keys": 15},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["monthly_price_minor"] == 239000
    assert updated.json()["included_mailboxes"] == 80
    assert updated.json()["max_api_keys"] == 15

    db.execute(delete(AuditLog).where(AuditLog.resource_type == "billing_plan", AuditLog.resource_id == plan_id))
    db.execute(delete(BillingPlan).where(BillingPlan.id == uuid.UUID(plan_id)))
    db.commit()


def test_non_owner_cannot_manage_package_catalog(client, tenant_admin):
    user, _, _ = tenant_admin
    login(client, user.email)
    response = client.get("/api/v1/platform/billing/plans")
    assert response.status_code == 403, response.text
