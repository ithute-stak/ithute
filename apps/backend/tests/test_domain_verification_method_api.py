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

    monkeypatch.setattr(
        "app.api.v1.domains.inspect_nameservers",
        lambda name, platform: {
            "lookup_status": "no_nameservers",
            "lookup_detail": None,
            "current_nameservers": [],
            "current_provider": None,
            "platform_nameservers": ["ns1.ithute.co.ls", "ns2.ithute.co.ls"],
            "platform_nameservers_configured": True,
            "already_on_platform_nameservers": False,
        },
    )
    monkeypatch.setattr(
        "app.api.v1.domains.inspect_existing_records",
        lambda name: {
            "has_existing_dns_records": False,
            "existing_record_types": [],
            "record_lookup_status": "none",
            "record_lookup_errors": [],
        },
    )

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


def test_existing_dns_records_keep_txt_challenge(client, db, tenant_admin, monkeypatch):
    user, tenant, _ = tenant_admin
    headers = login(client, user.email)

    monkeypatch.setattr(
        "app.api.v1.domains.inspect_nameservers",
        lambda name, platform: {
            "lookup_status": "found",
            "lookup_detail": None,
            "current_nameservers": ["ns1.zeecom.co.ls", "ns2.zeecom.co.ls"],
            "current_provider": "Zeecom Technologies",
            "platform_nameservers": ["ns1.ithute.co.ls", "ns2.ithute.co.ls"],
            "platform_nameservers_configured": True,
            "already_on_platform_nameservers": False,
        },
    )
    monkeypatch.setattr(
        "app.api.v1.domains.inspect_existing_records",
        lambda name: {
            "has_existing_dns_records": True,
            "existing_record_types": ["A", "MX", "TXT"],
            "record_lookup_status": "found",
            "record_lookup_errors": [],
        },
    )

    name = f"existing-migration-{uuid.uuid4().hex[:10]}.co.ls"
    response = client.post(
        f"/api/v1/tenants/{tenant.id}/domains",
        headers=headers,
        json={"name": name, "dns_mode": "platform"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["verification_method"] == "txt"
    assert body["verification_value"].startswith("mailbox-dns-verification=")
    assert body["verification_token_hint"] != "not-needed"
    cleanup_domain(db, uuid.UUID(body["id"]))
