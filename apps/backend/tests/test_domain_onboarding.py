import dns.resolver

from app.services.domain_discovery import (
    infer_nameserver_provider,
    inspect_existing_records,
    inspect_nameservers,
    platform_nameservers_ready,
)

PASSWORD = "Phase1-Test-Password!"


def login(client, email):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_nameserver_discovery_normalizes_and_identifies_provider():
    result = inspect_nameservers(
        "example.co.ls",
        ["ns1.mailbox.co.ls", "ns2.mailbox.co.ls"],
        resolve_fn=lambda _: ["ADA.NS.CLOUDFLARE.COM.", "bob.ns.cloudflare.com."],
    )
    assert result["lookup_status"] == "found"
    assert result["current_nameservers"] == ["ada.ns.cloudflare.com", "bob.ns.cloudflare.com"]
    assert result["current_provider"] == "Cloudflare"
    assert result["platform_nameservers_configured"] is True
    assert result["already_on_platform_nameservers"] is False


def test_existing_record_discovery_ignores_missing_types_and_finds_live_service_records():
    records = {
        "A": ["203.0.113.20"],
        "AAAA": [],
        "CNAME": [],
        "MX": ["10 mail.example.co.ls."],
        "TXT": [],
    }

    def resolve(name, record_type):
        values = records[record_type]
        if not values:
            raise dns.resolver.NoAnswer()
        return values

    result = inspect_existing_records("example.co.ls", resolve_fn=resolve)
    assert result["has_existing_dns_records"] is True
    assert result["existing_record_types"] == ["A", "MX"]
    assert result["record_lookup_status"] == "found"


def test_nameserver_discovery_recognizes_zeecom_and_nxdomain():
    assert infer_nameserver_provider(["ns1.zeecom.co.ls", "ns2.zeecom.co.ls"]) == "Zeecom Technologies"

    def missing(_):
        raise dns.resolver.NXDOMAIN()

    result = inspect_nameservers("missing.co.ls", ["ns1.mailbox.co.ls", "ns2.mailbox.co.ls"], resolve_fn=missing)
    assert result["lookup_status"] == "nxdomain"
    assert result["current_nameservers"] == []
    assert "registered" in result["lookup_detail"]


def test_placeholder_platform_nameservers_are_never_offered_for_delegation():
    placeholders = ["ns1.example.co.ls", "ns2.example.co.ls"]
    assert platform_nameservers_ready(placeholders) is False
    result = inspect_nameservers(
        "customer.co.ls",
        placeholders,
        resolve_fn=lambda _: ["ns1.zeecom.co.ls", "ns2.zeecom.co.ls"],
    )
    assert result["platform_nameservers_configured"] is False
    assert result["platform_nameservers"] == []
    assert result["already_on_platform_nameservers"] is False


def test_domain_inspection_existing_dns_requires_txt_and_returns_capacity(client, tenant_admin, platform_owner, monkeypatch):
    _, tenant, _ = tenant_admin
    owner_headers = login(client, platform_owner.email)

    assigned = client.put(
        f"/api/v1/tenants/{tenant.id}/billing/subscription",
        headers=owner_headers,
        json={"plan_code": "starter", "status": "active", "period_days": 30},
    )
    assert assigned.status_code == 200, assigned.text

    monkeypatch.setattr(
        "app.api.v1.domain_onboarding.inspect_nameservers",
        lambda name, platform: {
            "lookup_status": "found",
            "lookup_detail": None,
            "current_nameservers": ["ns1.zeecom.co.ls", "ns2.zeecom.co.ls"],
            "current_provider": "Zeecom Technologies",
            "platform_nameservers": ["ns1.mailbox.co.ls", "ns2.mailbox.co.ls"],
            "platform_nameservers_configured": True,
            "already_on_platform_nameservers": False,
        },
    )
    monkeypatch.setattr(
        "app.api.v1.domain_onboarding.inspect_existing_records",
        lambda name: {
            "has_existing_dns_records": True,
            "existing_record_types": ["A", "MX"],
            "record_lookup_status": "found",
            "record_lookup_errors": [],
        },
    )

    response = client.post(
        f"/api/v1/tenants/{tenant.id}/domain-onboarding/inspect",
        headers=owner_headers,
        json={"name": "Example.CO.LS", "dns_mode": "platform"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ascii_name"] == "example.co.ls"
    assert body["current_provider"] == "Zeecom Technologies"
    assert body["current_nameservers"] == ["ns1.zeecom.co.ls", "ns2.zeecom.co.ls"]
    assert body["nameserver_change_required"] is True
    assert body["platform_nameservers_configured"] is True
    assert body["has_existing_dns_records"] is True
    assert body["has_existing_external_dns"] is True
    assert body["verification_method"] == "txt"
    assert body["txt_required"] is True
    assert body["package"]["plan_code"] == "starter"
    assert body["domain_capacity"]["limit"] == 2
    assert body["domain_capacity"]["remaining"] == 2
    assert body["domain_capacity"]["allowed"] is True
    assert body["package_usage"]["domains"] == 0


def test_new_reseller_domain_without_existing_records_uses_nameserver_verification(client, tenant_admin, platform_owner, monkeypatch):
    _, tenant, _ = tenant_admin
    owner_headers = login(client, platform_owner.email)
    assert client.put(
        f"/api/v1/tenants/{tenant.id}/billing/subscription",
        headers=owner_headers,
        json={"plan_code": "starter", "status": "active", "period_days": 30},
    ).status_code == 200

    monkeypatch.setattr(
        "app.api.v1.domain_onboarding.inspect_nameservers",
        lambda name, platform: {
            "lookup_status": "no_nameservers",
            "lookup_detail": "No authoritative nameservers were returned for this domain.",
            "current_nameservers": [],
            "current_provider": None,
            "platform_nameservers": ["ns1.ithute.co.ls", "ns2.ithute.co.ls"],
            "platform_nameservers_configured": True,
            "already_on_platform_nameservers": False,
        },
    )
    monkeypatch.setattr(
        "app.api.v1.domain_onboarding.inspect_existing_records",
        lambda name: {
            "has_existing_dns_records": False,
            "existing_record_types": [],
            "record_lookup_status": "none",
            "record_lookup_errors": [],
        },
    )

    response = client.post(
        f"/api/v1/tenants/{tenant.id}/domain-onboarding/inspect",
        headers=owner_headers,
        json={"name": "new-domain.co.ls", "dns_mode": "platform"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["has_existing_dns_records"] is False
    assert body["verification_method"] == "nameserver"
    assert body["txt_required"] is False
    assert "No TXT record is required" in body["next_step"]


def test_platform_onboarding_with_placeholder_targets_never_requests_nameserver_change(client, tenant_admin, platform_owner, monkeypatch):
    _, tenant, _ = tenant_admin
    owner_headers = login(client, platform_owner.email)
    assert client.put(
        f"/api/v1/tenants/{tenant.id}/billing/subscription",
        headers=owner_headers,
        json={"plan_code": "starter", "status": "active", "period_days": 30},
    ).status_code == 200

    monkeypatch.setattr(
        "app.api.v1.domain_onboarding.inspect_nameservers",
        lambda name, platform: {
            "lookup_status": "found",
            "lookup_detail": None,
            "current_nameservers": ["ns1.zeecom.co.ls", "ns2.zeecom.co.ls"],
            "current_provider": "Zeecom Technologies",
            "platform_nameservers": [],
            "platform_nameservers_configured": False,
            "already_on_platform_nameservers": False,
        },
    )
    monkeypatch.setattr(
        "app.api.v1.domain_onboarding.inspect_existing_records",
        lambda name: {
            "has_existing_dns_records": False,
            "existing_record_types": [],
            "record_lookup_status": "none",
            "record_lookup_errors": [],
        },
    )
    response = client.post(
        f"/api/v1/tenants/{tenant.id}/domain-onboarding/inspect",
        headers=owner_headers,
        json={"name": "safe-bootstrap.co.ls", "dns_mode": "platform"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["nameserver_change_required"] is False
    assert body["platform_nameservers"] == []
    assert body["verification_method"] == "txt"
    assert body["txt_required"] is True
    assert "not configured yet" in body["next_step"]
    assert "unchanged" in body["next_step"]


def test_external_dns_inspection_never_requires_registrar_nameserver_change(client, tenant_admin, platform_owner, monkeypatch):
    _, tenant, _ = tenant_admin
    owner_headers = login(client, platform_owner.email)
    assert client.put(
        f"/api/v1/tenants/{tenant.id}/billing/subscription",
        headers=owner_headers,
        json={"plan_code": "business", "status": "active", "period_days": 30},
    ).status_code == 200

    monkeypatch.setattr(
        "app.api.v1.domain_onboarding.inspect_nameservers",
        lambda name, platform: {
            "lookup_status": "found",
            "lookup_detail": None,
            "current_nameservers": ["ns1.external.test", "ns2.external.test"],
            "current_provider": "External DNS provider",
            "platform_nameservers": ["ns1.mailbox.co.ls", "ns2.mailbox.co.ls"],
            "platform_nameservers_configured": True,
            "already_on_platform_nameservers": False,
        },
    )
    monkeypatch.setattr(
        "app.api.v1.domain_onboarding.inspect_existing_records",
        lambda name: {
            "has_existing_dns_records": True,
            "existing_record_types": ["MX"],
            "record_lookup_status": "found",
            "record_lookup_errors": [],
        },
    )
    response = client.post(
        f"/api/v1/tenants/{tenant.id}/domain-onboarding/inspect",
        headers=owner_headers,
        json={"name": "external.example.com", "dns_mode": "external"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["nameserver_change_required"] is False
    assert body["verification_method"] == "txt"
    assert body["txt_required"] is True
    assert "Keep the current external nameservers" in body["next_step"]
