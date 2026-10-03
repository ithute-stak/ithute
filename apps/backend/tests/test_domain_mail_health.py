from types import SimpleNamespace
from uuid import uuid4

from app.models.domains import DomainDnsMode, DomainStatus
from app.services import domain_mail_health as health_service


def _domain():
    return SimpleNamespace(
        id=uuid4(),
        ascii_name="example.co.ls",
        status=DomainStatus.verified,
        ownership_verified_at=object(),
        dns_mode=DomainDnsMode.platform,
        mail_enabled=True,
    )


def test_domain_mail_health_healthy(monkeypatch):
    key = SimpleNamespace(selector="s1", public_key_b64="PUBLIC")
    monkeypatch.setattr(health_service, "_active_dkim", lambda db, domain_id: key)
    monkeypatch.setattr(
        health_service,
        "delegation_diagnostics",
        lambda domain: {
            "ready": True,
            "observed_nameservers": ["ns1.ithute.co.ls", "ns2.ithute.co.ls"],
            "expected_nameservers": ["ns1.ithute.co.ls", "ns2.ithute.co.ls"],
        },
    )
    monkeypatch.setattr(
        health_service,
        "dns_readiness",
        lambda *args: {
            "checks": {"mx": True, "spf": True, "dkim": True, "dmarc": True},
            "recommended_records": [{"name": "example.co.ls", "type": "MX", "value": "10 mail.ithute.co.ls.", "purpose": "mail-routing"}],
        },
    )
    monkeypatch.setattr(
        health_service,
        "infrastructure_readiness",
        lambda *args: {
            "checks": {"forward_dns": True, "fcrdns": True},
            "addresses": ["203.0.113.25"],
            "ptr_hosts": ["mail.ithute.co.ls"],
            "public_ip": "203.0.113.25",
            "mail_hostname": "mail.ithute.co.ls",
        },
    )
    monkeypatch.setattr(
        health_service,
        "_discovery_check",
        lambda domain, label: {
            "id": label,
            "label": label.title(),
            "status": "healthy",
            "required": False,
            "detail": "ok",
            "observed": [],
            "expected": "mail.ithute.co.ls",
        },
    )

    result = health_service.domain_mail_health(None, _domain())

    assert result["overall_status"] == "healthy"
    assert result["score"] == 100
    assert result["summary"]["attention"] == 0
    assert result["dkim_selector"] == "s1"


def test_domain_mail_health_surfaces_required_failure(monkeypatch):
    key = SimpleNamespace(selector="s1", public_key_b64="PUBLIC")
    monkeypatch.setattr(health_service, "_active_dkim", lambda db, domain_id: key)
    monkeypatch.setattr(
        health_service,
        "delegation_diagnostics",
        lambda domain: {"ready": True, "observed_nameservers": [], "expected_nameservers": []},
    )
    monkeypatch.setattr(
        health_service,
        "dns_readiness",
        lambda *args: {
            "checks": {"mx": True, "spf": True, "dkim": True, "dmarc": False},
            "recommended_records": [],
        },
    )
    monkeypatch.setattr(
        health_service,
        "infrastructure_readiness",
        lambda *args: {
            "checks": {"forward_dns": True, "fcrdns": True},
            "addresses": [],
            "ptr_hosts": [],
            "public_ip": None,
            "mail_hostname": "mail.ithute.co.ls",
        },
    )
    monkeypatch.setattr(
        health_service,
        "_discovery_check",
        lambda domain, label: {
            "id": label,
            "label": label.title(),
            "status": "attention",
            "required": False,
            "detail": "optional",
            "observed": [],
            "expected": "mail.ithute.co.ls",
        },
    )

    result = health_service.domain_mail_health(None, _domain())

    assert result["overall_status"] == "attention"
    assert result["score"] < 100
    assert result["summary"]["attention"] == 1
    assert any(item["id"] == "dmarc" and item["status"] == "attention" for item in result["checks"])
