import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select

from app.models import AuditLog, MembershipRole, Tenant, TenantMembership, User
from app.models.domains import Domain, DomainEvent, DomainStatus, DomainVerificationAttempt
from app.core.security import hash_password

PASSWORD = "Phase1-Test-Password!"


def login(client, email):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def cleanup_domain(db, domain_id):
    db.execute(delete(AuditLog).where(AuditLog.resource_id == str(domain_id)))
    db.execute(delete(DomainVerificationAttempt).where(DomainVerificationAttempt.domain_id == domain_id))
    db.execute(delete(DomainEvent).where(DomainEvent.domain_id == domain_id))
    db.execute(delete(Domain).where(Domain.id == domain_id))
    db.commit()


def test_cross_tenant_domain_lookup_is_isolated(client, db, tenant_admin, platform_owner):
    admin, tenant, _ = tenant_admin
    admin_headers = login(client, admin.email)
    created = client.post(
        f"/api/v1/tenants/{tenant.id}/domains",
        headers=admin_headers,
        json={"name": f"isolated-{uuid.uuid4().hex[:10]}.example.com"},
    )
    assert created.status_code == 201
    domain_id = created.json()["id"]

    owner_headers = login(client, platform_owner.email)
    other = client.post(
        "/api/v1/tenants",
        headers=owner_headers,
        json={"name": "Isolation Other Tenant", "slug": f"isolation-other-{uuid.uuid4().hex[:8]}"},
    )
    assert other.status_code == 201
    other_id = other.json()["id"]
    lookup = client.get(f"/api/v1/tenants/{other_id}/domains/{domain_id}", headers=owner_headers)
    assert lookup.status_code == 404

    cleanup_domain(db, uuid.UUID(domain_id))
    db.execute(delete(AuditLog).where(AuditLog.resource_id == other_id))
    db.execute(delete(Tenant).where(Tenant.id == uuid.UUID(other_id)))
    db.commit()


def test_dns_admin_can_manage_domains(client, db, tenant_admin):
    _, tenant, _ = tenant_admin
    user = User(
        email=f"dns-admin-{uuid.uuid4().hex}@example.com",
        full_name="DNS Administrator",
        password_hash=hash_password(PASSWORD),
        is_active=True,
    )
    db.add(user); db.flush()
    membership = TenantMembership(tenant_id=tenant.id, user_id=user.id, role=MembershipRole.dns_admin)
    db.add(membership); db.commit()
    headers = login(client, user.email)
    created = client.post(
        f"/api/v1/tenants/{tenant.id}/domains",
        headers=headers,
        json={"name": f"dns-admin-{uuid.uuid4().hex[:10]}.example.com"},
    )
    assert created.status_code == 201
    cleanup_domain(db, uuid.UUID(created.json()["id"]))
    db.execute(delete(TenantMembership).where(TenantMembership.id == membership.id))
    db.execute(delete(User).where(User.id == user.id)); db.commit()


def test_external_dns_domain_is_not_powerdns_ready(client, db, tenant_admin):
    user, tenant, _ = tenant_admin
    headers = login(client, user.email)
    created = client.post(
        f"/api/v1/tenants/{tenant.id}/domains",
        headers=headers,
        json={"name": f"external-{uuid.uuid4().hex[:10]}.example.com", "dns_mode": "external"},
    )
    domain_id = uuid.UUID(created.json()["id"])
    domain = db.get(Domain, domain_id)
    domain.status = DomainStatus.verified
    domain.ownership_verified_at = datetime.now(timezone.utc)
    db.commit()
    readiness = client.get(f"/api/v1/tenants/{tenant.id}/domains/{domain_id}/readiness", headers=headers)
    assert readiness.status_code == 200
    assert readiness.json()["ownership_verified"] is True
    assert readiness.json()["ready_for_powerdns"] is False
    cleanup_domain(db, domain_id)


def test_challenge_regeneration_invalidates_old_hash(client, db, tenant_admin):
    user, tenant, _ = tenant_admin
    headers = login(client, user.email)
    created = client.post(
        f"/api/v1/tenants/{tenant.id}/domains",
        headers=headers,
        json={"name": f"regen-{uuid.uuid4().hex[:10]}.example.com"},
    )
    domain_id = uuid.UUID(created.json()["id"])
    old_hash = db.get(Domain, domain_id).verification_token_hash
    regenerated = client.post(f"/api/v1/tenants/{tenant.id}/domains/{domain_id}/challenge", headers=headers)
    assert regenerated.status_code == 200
    db.expire_all()
    domain = db.get(Domain, domain_id)
    assert domain.verification_token_hash != old_hash
    assert domain.status == DomainStatus.pending_verification
    assert domain.ownership_verified_at is None
    cleanup_domain(db, domain_id)


def test_verification_is_throttled_after_recent_attempt(client, db, tenant_admin):
    user, tenant, _ = tenant_admin
    headers = login(client, user.email)
    created = client.post(
        f"/api/v1/tenants/{tenant.id}/domains",
        headers=headers,
        json={"name": f"throttle-{uuid.uuid4().hex[:10]}.example.com"},
    )
    domain_id = uuid.UUID(created.json()["id"])
    db.add(DomainVerificationAttempt(
        domain_id=domain_id,
        actor_user_id=user.id,
        success=False,
        observed_values_json="[]",
        created_at=datetime.now(timezone.utc),
    ))
    db.commit()
    response = client.post(
        f"/api/v1/tenants/{tenant.id}/domains/{domain_id}/verify",
        headers=headers,
        json={"token": "x" * 40},
    )
    assert response.status_code == 429
    cleanup_domain(db, domain_id)


def test_status_filter_and_pagination(client, db, tenant_admin):
    user, tenant, _ = tenant_admin
    headers = login(client, user.email)
    ids = []
    for prefix in ("alpha", "beta", "gamma"):
        response = client.post(
            f"/api/v1/tenants/{tenant.id}/domains",
            headers=headers,
            json={"name": f"{prefix}-{uuid.uuid4().hex[:8]}.example.com"},
        )
        assert response.status_code == 201
        ids.append(uuid.UUID(response.json()["id"]))
    db.get(Domain, ids[0]).status = DomainStatus.suspended
    db.commit()

    filtered = client.get(f"/api/v1/tenants/{tenant.id}/domains", headers=headers, params={"status": "suspended"})
    assert filtered.status_code == 200
    assert all(row["status"] == "suspended" for row in filtered.json()["items"])

    paged = client.get(f"/api/v1/tenants/{tenant.id}/domains", headers=headers, params={"limit": 2, "offset": 0})
    assert paged.status_code == 200
    assert len(paged.json()["items"]) == 2
    assert paged.json()["total"] >= 3
    for domain_id in ids:
        cleanup_domain(db, domain_id)
