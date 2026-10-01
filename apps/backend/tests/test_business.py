import uuid

from sqlalchemy import delete, select

from app.models import AuditLog, CustomerProfile, Notification, SupportTicket, SupportTicketMessage, Tenant, TenantMembership, TenantSubscription, User

PASSWORD = "Phase1-Test-Password!"
SIGNUP_PASSWORD = "Commercial-Test-Password!"


def login(client, email: str, password: str = PASSWORD) -> None:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text


def test_public_pricing_is_available_without_auth(client):
    response = client.get("/api/v1/public/pricing")
    assert response.status_code == 200
    payload = response.json()
    assert payload["currency"] == "LSL"
    assert {item["code"] for item in payload["items"]} >= {"starter", "business", "enterprise"}


def test_public_signup_waits_for_owner_approval_before_trial(client, db, platform_owner):
    email = f"signup-{uuid.uuid4().hex}@example.com"
    response = client.post(
        "/api/v1/public/signup",
        json={
            "company_name": f"Signup Company {uuid.uuid4().hex[:8]}",
            "full_name": "Commercial Signup User",
            "email": email,
            "password": SIGNUP_PASSWORD,
            "plan_code": "business",
            "terms_accepted": True,
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["approval_status"] == "pending"
    assert payload["requested_plan"] == "business"
    assert "subscription" not in payload

    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    tenant = db.get(Tenant, uuid.UUID(payload["tenant"]["id"]))
    assert tenant is not None
    db.refresh(tenant)
    assert tenant.requires_approval is True
    assert tenant.approved_at is None
    assert db.scalar(select(TenantSubscription).where(TenantSubscription.tenant_id == tenant.id)) is None

    # Authentication is allowed in test mode, but tenant-service mutations are
    # blocked centrally until Ithute approves the application.
    login(client, email, SIGNUP_PASSWORD)
    blocked = client.patch(
        f"/api/v1/tenants/{tenant.id}/customer-profile",
        json={"billing_email": email, "city": "Maseru", "country": "Lesotho"},
    )
    assert blocked.status_code == 403, blocked.text
    assert blocked.json()["detail"]["code"] == "CUSTOMER_APPROVAL_PENDING"

    login(client, platform_owner.email)
    approved = client.post(f"/api/v1/platform/customer-applications/{tenant.id}/approve")
    assert approved.status_code == 200, approved.text
    approved_payload = approved.json()
    assert approved_payload["status"] == "approved"
    assert approved_payload["subscription"]["status"] == "trialing"
    assert approved_payload["subscription"]["plan"] == "business"

    db.refresh(tenant)
    assert tenant.requires_approval is False
    assert tenant.approved_at is not None
    assert db.scalar(select(TenantSubscription).where(TenantSubscription.tenant_id == tenant.id)) is not None

    # The same customer can use the tenant immediately after approval.
    login(client, email, SIGNUP_PASSWORD)
    allowed = client.patch(
        f"/api/v1/tenants/{tenant.id}/customer-profile",
        json={"billing_email": email, "city": "Maseru", "country": "Lesotho"},
    )
    assert allowed.status_code == 200, allowed.text

    db.execute(delete(Notification).where(Notification.tenant_id == tenant.id))
    db.execute(delete(CustomerProfile).where(CustomerProfile.tenant_id == tenant.id))
    db.execute(delete(TenantSubscription).where(TenantSubscription.tenant_id == tenant.id))
    db.execute(delete(AuditLog).where(AuditLog.tenant_id == tenant.id))
    db.execute(delete(TenantMembership).where(TenantMembership.tenant_id == tenant.id))
    db.execute(delete(User).where(User.id == user.id))
    db.execute(delete(Tenant).where(Tenant.id == tenant.id))
    db.commit()


def test_tenant_support_ticket_and_profile(client, db, tenant_admin):
    user, tenant, _ = tenant_admin
    login(client, user.email)
    profile = client.patch(
        f"/api/v1/tenants/{tenant.id}/customer-profile",
        json={"billing_email": user.email, "phone": "+266 5000 0000", "city": "Maseru", "country": "Lesotho"},
    )
    assert profile.status_code == 200, profile.text
    assert profile.json()["city"] == "Maseru"
    ticket = client.post(
        f"/api/v1/tenants/{tenant.id}/support/tickets",
        json={
            "subject": "Mail delivery assistance",
            "category": "deliverability",
            "description": "A customer message is delayed and needs investigation.",
            "priority": "high",
        },
    )
    assert ticket.status_code == 201, ticket.text
    ticket_id = uuid.UUID(ticket.json()["id"])
    message = client.post(
        f"/api/v1/tenants/{tenant.id}/support/tickets/{ticket_id}/messages",
        json={"body": "Please check the queue and delivery logs."},
    )
    assert message.status_code == 201, message.text
    listing = client.get(f"/api/v1/tenants/{tenant.id}/support/tickets")
    assert listing.status_code == 200
    assert any(item["id"] == str(ticket_id) for item in listing.json()["items"])
    db.execute(delete(SupportTicketMessage).where(SupportTicketMessage.ticket_id == ticket_id))
    db.execute(delete(Notification).where(Notification.tenant_id == tenant.id))
    db.execute(delete(SupportTicket).where(SupportTicket.id == ticket_id))
    db.execute(delete(CustomerProfile).where(CustomerProfile.tenant_id == tenant.id))
    db.execute(delete(AuditLog).where(AuditLog.tenant_id == tenant.id))
    db.commit()
