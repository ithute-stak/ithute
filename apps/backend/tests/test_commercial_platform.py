import uuid

from sqlalchemy import delete

from app.models import EmailVerificationToken, MailNode, MailNodeAgent, ResellerAccount, WhiteLabelBrand

PASSWORD = "Phase1-Test-Password!"


def login(client, email: str, password: str = PASSWORD):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text


def test_email_verification_round_trip_in_non_production(client, db, tenant_admin):
    user, _, _ = tenant_admin
    response = client.post("/api/v1/public/email-verification/request", json={"email": user.email})
    assert response.status_code == 200, response.text
    token = response.json().get("verification_token")
    assert token
    verified = client.post("/api/v1/public/email-verification/verify", json={"token": token})
    assert verified.status_code == 200, verified.text
    db.refresh(user)
    assert user.email_verified_at is not None
    db.execute(delete(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id))
    db.commit()


def test_commercial_provider_status_is_safe_without_credentials(client):
    payment = client.get("/api/v1/public/payment-provider")
    assert payment.status_code == 200
    assert payment.json()["provider"] == "dpo"
    assert isinstance(payment.json()["configured"], bool)


def test_platform_owner_can_enable_reseller_and_tenant_can_brand(client, db, platform_owner, tenant_admin):
    admin, tenant, _ = tenant_admin
    login(client, platform_owner.email)
    enabled = client.post(f"/api/v1/platform/resellers/{tenant.id}", json={"max_customers": 25, "discount_bps": 500})
    assert enabled.status_code == 201, enabled.text
    client.post("/api/v1/auth/logout")
    login(client, admin.email)
    saved = client.put(
        f"/api/v1/tenants/{tenant.id}/reseller/brand",
        json={"brand_name": "Example Hosting", "support_email": admin.email, "primary_color": "#123a38"},
    )
    assert saved.status_code == 200, saved.text
    brand = client.get(f"/api/v1/tenants/{tenant.id}/reseller/brand")
    assert brand.status_code == 200
    assert brand.json()["brand_name"] == "Example Hosting"
    reseller = db.query(ResellerAccount).filter(ResellerAccount.tenant_id == tenant.id).first()
    if reseller:
        db.execute(delete(WhiteLabelBrand).where(WhiteLabelBrand.reseller_id == reseller.id))
        db.delete(reseller)
        db.commit()


def test_platform_owner_can_manage_mail_nodes(client, db, platform_owner):
    login(client, platform_owner.email)
    name = f"phase2-mail-{uuid.uuid4().hex[:8]}"
    created = client.post(
        "/api/v1/platform/mail-nodes",
        json={
            "name": name,
            "role": "combined",
            "region": "lesotho",
            "hostname": f"{name}.example.com",
            "public_ip": "192.0.2.15",
            "ssh_port": 22,
            "ssh_user": "root",
            "storage_path": "/srv/ithute-mail",
            "capabilities": ["mail", "storage"],
            "weight": 100,
        },
    )
    assert created.status_code == 201, created.text
    node = created.json()
    assert node["storage_path"] == "/srv/ithute-mail"
    assert node["ssh_port"] == 22
    assert set(node["capabilities"]) == {"mail", "storage"}

    listed = client.get("/api/v1/platform/mail-nodes")
    assert listed.status_code == 200
    assert any(item["id"] == node["id"] for item in listed.json()["items"])

    maintenance = client.patch(
        f"/api/v1/platform/mail-nodes/{node['id']}/status",
        json={"status": "maintenance"},
    )
    assert maintenance.status_code == 200
    assert maintenance.json()["status"] == "maintenance"

    db.execute(delete(MailNode).where(MailNode.id == uuid.UUID(node["id"])))
    db.commit()


def test_mail_node_agent_reports_service_readiness(client, db, platform_owner):
    login(client, platform_owner.email)
    name = f"ready-mail-{uuid.uuid4().hex[:8]}"
    created = client.post(
        "/api/v1/platform/mail-nodes",
        json={
            "name": name,
            "role": "combined",
            "region": "lesotho",
            "hostname": f"{name}.example.com",
            "storage_path": "/srv/ithute-mail",
            "capabilities": ["mail", "storage"],
        },
    )
    assert created.status_code == 201, created.text
    node_id = created.json()["id"]

    credential = client.post(f"/api/v1/platform/mail-nodes/{node_id}/agent-token")
    assert credential.status_code == 200, credential.text
    token = credential.json()["token"]

    heartbeat = client.post(
        "/api/v1/mail-node-agent/heartbeat",
        headers={"X-Ithute-Mail-Agent": token},
        json={
            "version": "ithute-mail-agent/test",
            "total_storage_bytes": 500 * 1024**3,
            "used_storage_bytes": 100 * 1024**3,
            "capabilities": ["mail", "storage"],
            "smtp_ready": True,
            "imap_ready": True,
            "tls_ready": True,
            "tls_not_after": "2027-10-03T00:00:00+00:00",
        },
    )
    assert heartbeat.status_code == 200, heartbeat.text

    listed = client.get("/api/v1/platform/mail-nodes")
    row = next(item for item in listed.json()["items"] if item["id"] == node_id)
    assert row["smtp_ready"] is True
    assert row["imap_ready"] is True
    assert row["tls_ready"] is True
    assert row["free_storage_bytes"] == 400 * 1024**3

    db.execute(delete(MailNodeAgent).where(MailNodeAgent.node_id == uuid.UUID(node_id)))
    db.execute(delete(MailNode).where(MailNode.id == uuid.UUID(node_id)))
    db.commit()


def test_professional_and_hosting_routes_are_registered(client):
    routes = set(client.app.openapi().get("paths", {}))
    required = {
        "/api/v1/tenants/{tenant_id}/professional-email/migrations/run",
        "/api/v1/tenants/{tenant_id}/professional-email/mailboxes/{mailbox_id}/policy",
        "/api/v1/tenants/{tenant_id}/smtp-credentials",
        "/api/v1/transactional/v1/send",
        "/api/v1/tenants/{tenant_id}/registrar/register",
        "/api/v1/tenants/{tenant_id}/groupware/credentials",
        "/api/v1/platform/mail-nodes",
        "/api/v1/platform/mail-nodes/{node_id}/status",
        "/api/v1/mail-nodes/{node_id}/heartbeat",
        "/api/v1/platform/mail-nodes/{node_id}/agent-token",
        "/api/v1/platform/mail-nodes/{node_id}/agent",
        "/api/v1/mail-node-agent/heartbeat",
        "/api/v1/mail-node-agent/commands/claim",
        "/api/v1/platform/mail-routing",
        "/api/v1/platform/mail-routing/reconcile",
    }
    assert not (required - routes)
