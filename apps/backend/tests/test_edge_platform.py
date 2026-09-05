import uuid
from datetime import datetime, timezone

from sqlalchemy import delete

from app.models import AuditLog, DnsZoneAnalyticsSnapshot, EdgeApplication, EdgeInspection, EdgeOrigin, EdgeRule
from app.models.domains import Domain, DomainEvent, DomainStatus, DomainVerificationAttempt
from app.services.domains import token_hash
from app.services.edge_inspection import EdgeInspectionError, inspect_public_origin, summarize_powerdns_zone

PASSWORD = "Phase1-Test-Password!"


def login(client, email):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def verified_domain(db, user, tenant):
    name = f"edge-{uuid.uuid4().hex[:10]}.example.com"
    domain = Domain(
        tenant_id=tenant.id,
        ascii_name=name,
        unicode_name=name,
        status=DomainStatus.verified,
        verification_token_hash=token_hash("edge-platform-test-token"),
        verification_token_hint="verified",
        verification_record_name=f"_mailbox-dns-verification.{name}",
        ownership_verified_at=datetime.now(timezone.utc),
        created_by_user_id=user.id,
    )
    db.add(domain)
    db.commit()
    db.refresh(domain)
    return domain


def cleanup(db, tenant_id, domain_id):
    app_ids = db.scalars(EdgeApplication.__table__.select().with_only_columns(EdgeApplication.id).where(EdgeApplication.tenant_id == tenant_id)).all()
    if app_ids:
        db.execute(delete(EdgeInspection).where(EdgeInspection.application_id.in_(app_ids)))
        db.execute(delete(EdgeRule).where(EdgeRule.application_id.in_(app_ids)))
        db.execute(delete(EdgeOrigin).where(EdgeOrigin.application_id.in_(app_ids)))
        db.execute(delete(EdgeApplication).where(EdgeApplication.id.in_(app_ids)))
    db.execute(delete(DnsZoneAnalyticsSnapshot).where(DnsZoneAnalyticsSnapshot.domain_id == domain_id))
    db.execute(delete(AuditLog).where(AuditLog.resource_id == str(domain_id)))
    db.execute(delete(DomainVerificationAttempt).where(DomainVerificationAttempt.domain_id == domain_id))
    db.execute(delete(DomainEvent).where(DomainEvent.domain_id == domain_id))
    db.execute(delete(Domain).where(Domain.id == domain_id))
    db.commit()


def test_zone_summary_counts_records_by_type():
    summary = summarize_powerdns_zone({
        "kind": "Master",
        "serial": 2026090201,
        "dnssec": True,
        "rrsets": [
            {"type": "A", "records": [{"content": "203.0.113.10"}, {"content": "203.0.113.11"}]},
            {"type": "MX", "records": [{"content": "10 mail.example.com."}]},
        ],
    })
    assert summary == {
        "zone_kind": "Master",
        "serial": 2026090201,
        "dnssec_enabled": True,
        "rrset_count": 2,
        "record_count": 3,
        "type_counts": {"A": 2, "MX": 1},
    }


def test_health_probe_rejects_private_resolution(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 443))])
    try:
        inspect_public_origin("https://private.example", "/health", 200, 2)
    except EdgeInspectionError as exc:
        assert "non-public IP" in str(exc)
    else:
        raise AssertionError("Private health target should be rejected")


def test_tenant_admin_can_manage_edge_application_and_run_inspection(client, db, tenant_admin, monkeypatch):
    user, tenant, _ = tenant_admin
    headers = login(client, user.email)
    domain = verified_domain(db, user, tenant)

    caps = client.get(f"/api/v1/tenants/{tenant.id}/edge/capabilities", headers=headers)
    assert caps.status_code == 200
    assert caps.json()["capabilities"]["origin_health"]["state"] == "active"
    assert caps.json()["capabilities"]["global_cdn"]["state"] == "planned"

    created = client.post(
        f"/api/v1/tenants/{tenant.id}/edge/applications",
        headers=headers,
        json={"domain_id": str(domain.id), "hostname": domain.ascii_name, "mode": "protected"},
    )
    assert created.status_code == 201, created.text
    app_id = created.json()["id"]

    updated = client.patch(
        f"/api/v1/tenants/{tenant.id}/edge/applications/{app_id}",
        headers=headers,
        json={"waf_enabled": True, "cache_enabled": True, "rate_limit_per_minute": 600},
    )
    assert updated.status_code == 200
    assert updated.json()["waf_enabled"] is True
    assert updated.json()["rate_limit_per_minute"] == 600

    origin = client.post(
        f"/api/v1/tenants/{tenant.id}/edge/applications/{app_id}/origins",
        headers=headers,
        json={"name": "primary", "url": "https://origin.example.com", "health_path": "/health", "expected_status": 200},
    )
    assert origin.status_code == 201, origin.text
    assert origin.json()["origins"][0]["name"] == "primary"

    rule = client.post(
        f"/api/v1/tenants/{tenant.id}/edge/applications/{app_id}/rules",
        headers=headers,
        json={"name": "Protect login", "rule_type": "rate_limit", "expression": "path starts_with /login", "action": "throttle", "config": {"requests_per_minute": 30}},
    )
    assert rule.status_code == 201, rule.text
    assert rule.json()["rules"][0]["action"] == "throttle"

    monkeypatch.setattr(
        "app.api.v1.edge.inspect_public_origin",
        lambda *args, **kwargs: {
            "healthy": True,
            "resolved_ip": "203.0.113.10",
            "status_code": 200,
            "latency_ms": 42,
            "tls_version": "TLSv1.3",
            "cipher": "TLS_AES_256_GCM_SHA384",
            "certificate_issuer": "commonName=Example CA",
            "certificate_not_after": datetime(2027, 1, 1, tzinfo=timezone.utc),
            "certificate_days_remaining": 120,
            "error": None,
        },
    )
    inspected = client.post(f"/api/v1/tenants/{tenant.id}/edge/applications/{app_id}/inspect", headers=headers)
    assert inspected.status_code == 200, inspected.text
    assert inspected.json()["results"][0]["healthy"] is True
    assert inspected.json()["results"][0]["tls_version"] == "TLSv1.3"

    history = client.get(f"/api/v1/tenants/{tenant.id}/edge/applications/{app_id}/inspections", headers=headers)
    assert history.status_code == 200
    assert history.json()["items"][0]["status_code"] == 200

    cleanup(db, tenant.id, domain.id)


def test_dns_analytics_live_and_snapshot(client, db, tenant_admin, monkeypatch):
    user, tenant, _ = tenant_admin
    headers = login(client, user.email)
    domain = verified_domain(db, user, tenant)
    zone = {
        "kind": "Master",
        "serial": 2026090202,
        "dnssec": False,
        "rrsets": [
            {"type": "SOA", "records": [{"content": "ns1.example. hostmaster.example. 1 1 1 1 1"}]},
            {"type": "A", "records": [{"content": "203.0.113.10"}]},
        ],
    }
    monkeypatch.setattr("app.api.v1.edge.PowerDNSClient.get_zone", lambda self, name: zone)

    live = client.get(f"/api/v1/tenants/{tenant.id}/edge/domains/{domain.id}/dns-analytics", headers=headers)
    assert live.status_code == 200, live.text
    assert live.json()["live"]["record_count"] == 2

    snapshot = client.post(f"/api/v1/tenants/{tenant.id}/edge/domains/{domain.id}/dns-analytics/snapshot", headers=headers)
    assert snapshot.status_code == 201, snapshot.text
    assert snapshot.json()["type_counts"] == {"A": 1, "SOA": 1}

    history = client.get(f"/api/v1/tenants/{tenant.id}/edge/domains/{domain.id}/dns-analytics", headers=headers)
    assert len(history.json()["history"]) == 1

    cleanup(db, tenant.id, domain.id)
