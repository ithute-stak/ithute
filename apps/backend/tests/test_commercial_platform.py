from sqlalchemy import delete

from app.models import EmailVerificationToken, ResellerAccount, WhiteLabelBrand

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
    }
    assert not (required - routes)
