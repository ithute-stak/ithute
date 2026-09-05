import uuid
from sqlalchemy import delete, select
from app.models import AuditLog, Tenant

PASSWORD = "Phase1-Test-Password!"


def login(client, email):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_platform_owner_can_create_and_list_tenant(client, db, platform_owner):
    token = login(client, platform_owner.email)
    slug = f"phase1-{uuid.uuid4().hex[:12]}"
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/api/v1/tenants",
        json={"name": "Phase 1 Verification Tenant", "slug": slug},
        headers=headers,
    )
    assert created.status_code == 201
    tenant_id = created.json()["id"]

    listed = client.get("/api/v1/tenants", headers=headers)
    assert listed.status_code == 200
    assert any(row["id"] == tenant_id and row["slug"] == slug for row in listed.json())

    audit = db.scalar(
        select(AuditLog).where(
            AuditLog.actor_user_id == platform_owner.id,
            AuditLog.action == "tenant.create",
            AuditLog.resource_id == tenant_id,
        )
    )
    assert audit is not None

    db.execute(delete(AuditLog).where(AuditLog.resource_id == tenant_id))
    db.execute(delete(Tenant).where(Tenant.id == tenant_id))
    db.commit()


def test_duplicate_tenant_slug_is_rejected(client, db, platform_owner):
    token = login(client, platform_owner.email)
    slug = f"duplicate-{uuid.uuid4().hex[:12]}"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"name": "Duplicate Tenant", "slug": slug}

    first = client.post("/api/v1/tenants", json=payload, headers=headers)
    second = client.post("/api/v1/tenants", json=payload, headers=headers)
    assert first.status_code == 201
    assert second.status_code == 409

    tenant_id = first.json()["id"]
    db.execute(delete(AuditLog).where(AuditLog.resource_id == tenant_id))
    db.execute(delete(Tenant).where(Tenant.id == tenant_id))
    db.commit()


def test_tenant_member_cannot_access_platform_tenants(client, tenant_member):
    token = login(client, tenant_member.email)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/tenants", headers=headers).status_code == 403
    assert client.post(
        "/api/v1/tenants",
        json={"name": "Forbidden Tenant", "slug": f"forbidden-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    ).status_code == 403
