import uuid

from sqlalchemy import delete

from app.models import AuditLog
from app.models.domains import Domain, DomainEvent, DomainVerificationAttempt

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


def test_new_registrar_domain_is_created_without_txt_challenge(client, db, tenant_admin, monkeypatch):
    user, tenant, _ = tenant_admin
    headers = login(client, user.email)
    monkeypatch.setattr("app.api.v1.domains.settings.nameserver_1", "ns1.ithute.co.ls")
    monkeypatch.setattr("app.api.v1.domains.settings.nameserver_2", "ns2.ithute.co.ls")

    name = f"new-registration-{uuid.uuid4().hex[:10]}.co.ls"
    response = client.post(
        f"/api/v1/tenants/{tenant.id}/domains",
        headers=headers,
        json={"name": name, "dns_mode": "platform"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["verification_method"] == "nameserver"
    assert body["verification_value"] is None
    assert body["verification_token_hint"] == "not-needed"

    challenge = client.post(
        f"/api/v1/tenants/{tenant.id}/domains/{body['id']}/challenge",
        headers=headers,
    )
    assert challenge.status_code == 409
    assert "TXT verification is not required" in challenge.json()["detail"]
    cleanup_domain(db, uuid.UUID(body["id"]))


def test_existing_dns_migration_is_created_without_txt_challenge(client, db, tenant_admin, monkeypatch):
    user, tenant, _ = tenant_admin
    headers = login(client, user.email)
    monkeypatch.setattr("app.api.v1.domains.settings.nameserver_1", "ns1.ithute.co.ls")
    monkeypatch.setattr("app.api.v1.domains.settings.nameserver_2", "ns2.ithute.co.ls")

    # Creation intentionally does not depend on the old provider being reachable.
    # Existing DNS records must be staged/copied before cutover, while registrar
    # nameserver delegation is the ownership proof for managed authoritative DNS.
    name = f"existing-migration-{uuid.uuid4().hex[:10]}.co.ls"
    response = client.post(
        f"/api/v1/tenants/{tenant.id}/domains",
        headers=headers,
        json={"name": name, "dns_mode": "platform"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["verification_method"] == "nameserver"
    assert body["verification_value"] is None
    assert body["verification_token_hint"] == "not-needed"
    cleanup_domain(db, uuid.UUID(body["id"]))


def test_external_dns_still_uses_txt_challenge(client, db, tenant_admin):
    user, tenant, _ = tenant_admin
    headers = login(client, user.email)

    name = f"external-dns-{uuid.uuid4().hex[:10]}.co.ls"
    response = client.post(
        f"/api/v1/tenants/{tenant.id}/domains",
        headers=headers,
        json={"name": name, "dns_mode": "external"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["verification_method"] == "txt"
    assert body["verification_value"].startswith("mailbox-dns-verification=")
    assert body["verification_token_hint"] != "not-needed"
    cleanup_domain(db, uuid.UUID(body["id"]))


def test_managed_dns_creation_fails_closed_if_public_platform_nameservers_are_not_configured(client, tenant_admin, monkeypatch):
    user, tenant, _ = tenant_admin
    headers = login(client, user.email)
    monkeypatch.setattr("app.api.v1.domains.settings.nameserver_1", "ns1.example.co.ls")
    monkeypatch.setattr("app.api.v1.domains.settings.nameserver_2", "ns2.example.co.ls")

    response = client.post(
        f"/api/v1/tenants/{tenant.id}/domains",
        headers=headers,
        json={"name": f"blocked-{uuid.uuid4().hex[:10]}.co.ls", "dns_mode": "platform"},
    )
    assert response.status_code == 503
    assert "No TXT fallback" in response.json()["detail"]
