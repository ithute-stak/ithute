PASSWORD = "Phase1-Test-Password!"


def login(client, email):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200


def test_tenant_admin_can_read_tenant_audit(client, tenant_admin):
    admin, tenant, _ = tenant_admin
    login(client, admin.email)
    invited = client.post(
        f"/api/v1/tenants/{tenant.id}/invitations",
        json={"email": "audit-user@example.com", "role": "auditor"},
    )
    assert invited.status_code == 201
    audit = client.get(f"/api/v1/tenants/{tenant.id}/audit")
    assert audit.status_code == 200
    assert any(row["action"] == "invitation.create" for row in audit.json())


def test_platform_owner_can_read_platform_audit(client, platform_owner):
    login(client, platform_owner.email)
    response = client.get("/api/v1/audit/platform")
    assert response.status_code == 200
    assert any(row["action"] == "auth.login" for row in response.json())
