import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select

from app.models import AuditLog, Tenant
from app.models.domains import Domain, DomainEvent, DomainStatus, DomainVerificationAttempt
from app.services.domains import normalize_domain, token_hash, verification_value, verify_domain

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


def test_domain_normalization_and_idn():
    assert normalize_domain(" Example.COM. ") == ("example.com", "example.com")
    ascii_name, unicode_name = normalize_domain("münchen.de")
    assert ascii_name == "xn--mnchen-3ya.de"
    assert unicode_name == "münchen.de"


def test_domain_normalization_rejects_unsafe_inputs():
    for value in ["https://example.com", "*.example.com", "user@example.com", "localhost", "example.1"]:
        try:
            normalize_domain(value)
        except ValueError:
            continue
        raise AssertionError(f"Expected invalid domain: {value}")


def test_tenant_admin_can_create_list_search_and_archive_domain(client, db, tenant_admin):
    user, tenant, _ = tenant_admin
    headers = login(client, user.email)
    name = f"phase3-{uuid.uuid4().hex[:10]}.example.com"
    created = client.post(f"/api/v1/tenants/{tenant.id}/domains", headers=headers, json={"name": name})
    assert created.status_code == 201, created.text
    body = created.json()
    domain_id = body["id"]
    assert body["ascii_name"] == name
    assert body["status"] == "pending_verification"
    assert body["verification_value"].startswith("mailbox-dns-verification=")

    listed = client.get(f"/api/v1/tenants/{tenant.id}/domains", headers=headers)
    assert listed.status_code == 200
    assert any(item["id"] == domain_id for item in listed.json()["items"])
    searched = client.get(f"/api/v1/tenants/{tenant.id}/domains", headers=headers, params={"q": name[:12]})
    assert searched.status_code == 200
    assert searched.json()["total"] >= 1

    archived = client.delete(f"/api/v1/tenants/{tenant.id}/domains/{domain_id}", headers=headers)
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    blocked = client.patch(f"/api/v1/tenants/{tenant.id}/domains/{domain_id}", headers=headers, json={"notes": "nope"})
    assert blocked.status_code == 409
    cleanup_domain(db, uuid.UUID(domain_id))


def test_duplicate_domain_is_globally_blocked(client, db, platform_owner, tenant_admin):
    admin, tenant, _ = tenant_admin
    owner_headers = login(client, platform_owner.email)
    admin_headers = login(client, admin.email)
    name = f"claimed-{uuid.uuid4().hex[:10]}.example.com"
    first = client.post(f"/api/v1/tenants/{tenant.id}/domains", headers=admin_headers, json={"name": name})
    assert first.status_code == 201

    other = client.post("/api/v1/tenants", headers=owner_headers, json={"name": "Other Domain Tenant", "slug": f"other-{uuid.uuid4().hex[:10]}"})
    assert other.status_code == 201
    other_id = other.json()["id"]
    duplicate = client.post(f"/api/v1/tenants/{other_id}/domains", headers=owner_headers, json={"name": name.upper()})
    assert duplicate.status_code == 409

    cleanup_domain(db, uuid.UUID(first.json()["id"]))
    db.execute(delete(AuditLog).where(AuditLog.resource_id == other_id))
    db.execute(delete(Tenant).where(Tenant.id == uuid.UUID(other_id)))
    db.commit()


def test_member_without_dns_permission_is_forbidden(client, tenant_member):
    membership = tenant_member.memberships[0]
    headers = login(client, tenant_member.email)
    response = client.get(f"/api/v1/tenants/{membership.tenant_id}/domains", headers=headers)
    assert response.status_code == 403


def test_unverified_domain_cannot_be_manually_marked_verified(client, db, tenant_admin):
    user, tenant, _ = tenant_admin
    headers = login(client, user.email)
    created = client.post(
        f"/api/v1/tenants/{tenant.id}/domains",
        headers=headers,
        json={"name": f"status-{uuid.uuid4().hex[:10]}.example.com"},
    )
    domain_id = created.json()["id"]
    response = client.patch(
        f"/api/v1/tenants/{tenant.id}/domains/{domain_id}/status",
        headers=headers,
        json={"status": "verified"},
    )
    assert response.status_code == 409
    cleanup_domain(db, uuid.UUID(domain_id))


def test_verification_marks_domain_verified_and_exposes_history(client, db, tenant_admin, monkeypatch):
    user, tenant, _ = tenant_admin
    headers = login(client, user.email)
    name = f"verify-{uuid.uuid4().hex[:10]}.example.com"
    created = client.post(f"/api/v1/tenants/{tenant.id}/domains", headers=headers, json={"name": name})
    body = created.json()
    token = body["verification_value"].split("=", 1)[1]

    def fake_verify(domain, raw_token, actor_user_id, db_session):
        assert raw_token == token
        domain.status = DomainStatus.verified
        domain.ownership_verified_at = datetime.now(timezone.utc)
        domain.verification_token_hash = token_hash("invalidated-after-success")
        domain.verification_token_hint = "verified"
        db_session.add(DomainVerificationAttempt(
            domain_id=domain.id,
            actor_user_id=actor_user_id,
            success=True,
            observed_values_json='["%s"]' % verification_value(raw_token),
        ))
        return True, [verification_value(raw_token)], None

    monkeypatch.setattr("app.api.v1.domains.verify_domain", fake_verify)
    verified = client.post(
        f"/api/v1/tenants/{tenant.id}/domains/{body['id']}/verify",
        headers=headers,
        json={"token": token},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["verified"] is True
    assert verified.json()["status"] == "verified"

    readiness = client.get(f"/api/v1/tenants/{tenant.id}/domains/{body['id']}/readiness", headers=headers)
    assert readiness.status_code == 200
    assert readiness.json()["ready_for_powerdns"] is True
    assert len(readiness.json()["required_nameservers"]) == 2

    attempts = client.get(f"/api/v1/tenants/{tenant.id}/domains/{body['id']}/verification-attempts", headers=headers)
    assert attempts.status_code == 200
    assert attempts.json()[0]["success"] is True
    cleanup_domain(db, uuid.UUID(body["id"]))


def test_service_invalidates_successful_challenge(db, tenant_admin):
    user, tenant, _ = tenant_admin
    raw_token = "x" * 40
    name = f"service-{uuid.uuid4().hex[:10]}.example.com"
    domain = Domain(
        tenant_id=tenant.id,
        ascii_name=name,
        unicode_name=name,
        verification_token_hash=token_hash(raw_token),
        verification_token_hint=raw_token[-8:],
        verification_record_name="_mailbox-dns-verification.example.com",
        created_by_user_id=user.id,
    )
    db.add(domain)
    db.commit()
    db.refresh(domain)
    original_hash = domain.verification_token_hash
    success, _, _ = verify_domain(domain, raw_token, user.id, db, resolver=lambda _: [verification_value(raw_token)])
    assert success is True
    assert domain.status == DomainStatus.verified
    assert domain.verification_token_hash != original_hash
    assert domain.verification_token_hint == "verified"
    db.commit()
    cleanup_domain(db, domain.id)


def test_platform_owner_can_release_archived_global_claim(client, db, platform_owner, tenant_admin):
    _, tenant, _ = tenant_admin
    headers = login(client, platform_owner.email)
    name = f"release-{uuid.uuid4().hex[:10]}.example.com"
    created = client.post(f"/api/v1/tenants/{tenant.id}/domains", headers=headers, json={"name": name})
    assert created.status_code == 201
    domain_id = created.json()["id"]
    blocked = client.delete(f"/api/v1/tenants/{tenant.id}/domains/{domain_id}/release", headers=headers)
    assert blocked.status_code == 409
    assert client.delete(f"/api/v1/tenants/{tenant.id}/domains/{domain_id}", headers=headers).status_code == 200
    released = client.delete(f"/api/v1/tenants/{tenant.id}/domains/{domain_id}/release", headers=headers)
    assert released.status_code == 204
    assert db.scalar(select(Domain).where(Domain.id == uuid.UUID(domain_id))) is None
    db.execute(delete(AuditLog).where(AuditLog.resource_id == domain_id))
    db.commit()


def test_platform_owner_cannot_release_archived_domain_with_managed_dns_lifecycle(client, db, platform_owner, tenant_admin):
    _, tenant, _ = tenant_admin
    headers = login(client, platform_owner.email)
    name = f"managed-release-{uuid.uuid4().hex[:10]}.example.com"
    created = client.post(f"/api/v1/tenants/{tenant.id}/domains", headers=headers, json={"name": name})
    assert created.status_code == 201
    domain_id = uuid.UUID(created.json()["id"])
    assert client.delete(f"/api/v1/tenants/{tenant.id}/domains/{domain_id}", headers=headers).status_code == 200

    db.add(DomainEvent(
        domain_id=domain_id,
        tenant_id=tenant.id,
        actor_user_id=platform_owner.id,
        event_type="dns.zone_provisioned",
        metadata_json='{"created": true}',
    ))
    db.commit()

    blocked = client.delete(f"/api/v1/tenants/{tenant.id}/domains/{domain_id}/release", headers=headers)
    assert blocked.status_code == 409
    assert "authoritative DNS zone" in blocked.json()["detail"]
    assert db.scalar(select(Domain).where(Domain.id == domain_id)) is not None
    cleanup_domain(db, domain_id)


def test_domain_events_and_audit_are_written(client, db, tenant_admin):
    user, tenant, _ = tenant_admin
    headers = login(client, user.email)
    created = client.post(
        f"/api/v1/tenants/{tenant.id}/domains",
        headers=headers,
        json={"name": f"events-{uuid.uuid4().hex[:10]}.example.com"},
    )
    domain_id = uuid.UUID(created.json()["id"])
    events = client.get(f"/api/v1/tenants/{tenant.id}/domains/{domain_id}/events", headers=headers)
    assert events.status_code == 200
    assert any(event["event_type"] == "domain.created" for event in events.json())
    audit = db.scalar(select(AuditLog).where(AuditLog.resource_id == str(domain_id), AuditLog.action == "domain.create"))
    assert audit is not None
    cleanup_domain(db, domain_id)
