import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1 import dns as dns_api
from app.models.domains import DomainStatus


class FakeDB:
    def commit(self):
        return None


def pending_domain():
    return SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        ascii_name="staged-example.co.ls",
        dns_mode=SimpleNamespace(value="platform"),
        status=DomainStatus.pending_verification,
        ownership_verified_at=None,
        mail_enabled=True,
    )


def test_verified_helper_rejects_pending_platform_domain(monkeypatch):
    domain = pending_domain()
    monkeypatch.setattr(dns_api, "_platform_domain", lambda *args, **kwargs: domain)

    with pytest.raises(HTTPException) as exc:
        dns_api._verified_platform_domain(FakeDB(), domain.tenant_id, domain.id)

    assert exc.value.status_code == 409
    assert "verified" in str(exc.value.detail).lower()


def test_pending_domain_can_stage_zone_without_activating_mail(monkeypatch):
    domain = pending_domain()

    class FakePowerDNSClient:
        def get_zone(self, name):
            assert name == domain.ascii_name
            return {"name": name}

        def reconcile_authority(self, name):
            return {"name": name, "kind": "Master", "rrsets": []}

    monkeypatch.setattr(dns_api, "require_tenant_permission", lambda *args, **kwargs: None)
    monkeypatch.setattr(dns_api, "_platform_domain", lambda *args, **kwargs: domain)
    monkeypatch.setattr(dns_api, "PowerDNSClient", FakePowerDNSClient)
    monkeypatch.setattr(dns_api, "add_domain_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(dns_api, "_audit", lambda *args, **kwargs: None)

    def fail_mail_activation(*args, **kwargs):
        raise AssertionError("pending domain must not activate mail lifecycle")

    monkeypatch.setattr(dns_api, "_mail_dns_or_502", fail_mail_activation)

    result = dns_api.provision_zone(
        domain.tenant_id,
        domain.id,
        db=FakeDB(),
        current=SimpleNamespace(id=uuid.uuid4()),
    )

    assert result["staged"] is True
    assert result["ownership_verified"] is False
    assert result["activation_required"] is True
    assert result["mail_dns"] is None
    assert result["zone"]["name"] == domain.ascii_name


def test_verified_domain_reconcile_remains_live(monkeypatch):
    domain = pending_domain()
    domain.status = DomainStatus.verified
    domain.ownership_verified_at = object()

    class FakePowerDNSClient:
        def get_zone(self, name):
            return {"name": name}

        def reconcile_authority(self, name):
            return {"name": name, "kind": "Master", "rrsets": []}

    mail_result = SimpleNamespace(
        selector="s1",
        dkim_created=True,
        records=[{"type": "MX"}],
        rspamd_synced_domains=[domain.ascii_name],
    )
    monkeypatch.setattr(dns_api, "require_tenant_permission", lambda *args, **kwargs: None)
    monkeypatch.setattr(dns_api, "_platform_domain", lambda *args, **kwargs: domain)
    monkeypatch.setattr(dns_api, "PowerDNSClient", FakePowerDNSClient)
    monkeypatch.setattr(dns_api, "add_domain_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(dns_api, "_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(dns_api, "_mail_dns_or_502", lambda *args, **kwargs: mail_result)

    result = dns_api.provision_zone(
        domain.tenant_id,
        domain.id,
        db=FakeDB(),
        current=SimpleNamespace(id=uuid.uuid4()),
    )

    assert result["staged"] is False
    assert result["ownership_verified"] is True
    assert result["activation_required"] is False
    assert result["mail_dns"]["selector"] == "s1"
