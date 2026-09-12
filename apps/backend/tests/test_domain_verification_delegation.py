import uuid
from types import SimpleNamespace

from app.models.domains import DomainStatus
from app.services.domains import token_hash, verify_domain


def fake_db():
    added = []
    return SimpleNamespace(add=added.append), added


def pending_platform_domain(method="nameserver"):
    token = "delegation-fallback-token-1234567890abcdef"
    return SimpleNamespace(
        id=uuid.uuid4(),
        ascii_name="example.co.ls",
        dns_mode="platform",
        verification_method=method,
        verification_record_name="_mailbox-dns-verification.example.co.ls",
        verification_token_hash=token_hash(token),
        verification_token_hint=token[-8:],
        status=DomainStatus.pending_verification,
        ownership_verified_at=None,
    )


def test_nameserver_method_accepts_both_configured_nameservers_without_txt(monkeypatch):
    domain = pending_platform_domain()
    db, attempts = fake_db()
    monkeypatch.setattr("app.services.domains.settings.nameserver_1", "ns1.ithute.co.ls")
    monkeypatch.setattr("app.services.domains.settings.nameserver_2", "ns2.ithute.co.ls")

    def txt_must_not_run(_):
        raise AssertionError("TXT resolver must not run for nameserver verification")

    success, observed, error = verify_domain(
        domain,
        None,
        uuid.uuid4(),
        db,
        resolver=txt_must_not_run,
        nameserver_resolver=lambda _: ["NS2.ITHUTE.CO.LS.", "ns1.ithute.co.ls."],
    )

    assert success is True
    assert error is None
    assert "NS:ns1.ithute.co.ls" in observed
    assert "NS:ns2.ithute.co.ls" in observed
    assert domain.status == DomainStatus.verified
    assert domain.ownership_verified_at is not None
    assert attempts[0].success is True


def test_nameserver_method_requires_both_nameservers(monkeypatch):
    domain = pending_platform_domain()
    db, attempts = fake_db()
    monkeypatch.setattr("app.services.domains.settings.nameserver_1", "ns1.ithute.co.ls")
    monkeypatch.setattr("app.services.domains.settings.nameserver_2", "ns2.ithute.co.ls")

    success, observed, error = verify_domain(
        domain,
        None,
        uuid.uuid4(),
        db,
        resolver=lambda _: [],
        nameserver_resolver=lambda _: ["ns1.ithute.co.ls"],
    )

    assert success is False
    assert error == "delegation_not_ready"
    assert observed == ["NS:ns1.ithute.co.ls"]
    assert domain.status == DomainStatus.pending_verification
    assert attempts[0].success is False


def test_txt_migration_does_not_accept_nameserver_delegation_as_bypass(monkeypatch):
    domain = pending_platform_domain(method="txt")
    db, attempts = fake_db()
    monkeypatch.setattr("app.services.domains.settings.nameserver_1", "ns1.ithute.co.ls")
    monkeypatch.setattr("app.services.domains.settings.nameserver_2", "ns2.ithute.co.ls")

    def nameserver_must_not_run(_):
        raise AssertionError("Nameserver resolver must not bypass required TXT verification")

    success, observed, _ = verify_domain(
        domain,
        None,
        uuid.uuid4(),
        db,
        resolver=lambda _: [],
        nameserver_resolver=nameserver_must_not_run,
    )

    assert success is False
    assert observed == []
    assert domain.status == DomainStatus.pending_verification
    assert attempts[0].success is False


def test_external_dns_cannot_use_nameserver_method(monkeypatch):
    domain = pending_platform_domain(method="nameserver")
    domain.dns_mode = "external"
    db, attempts = fake_db()
    monkeypatch.setattr("app.services.domains.settings.nameserver_1", "ns1.ithute.co.ls")
    monkeypatch.setattr("app.services.domains.settings.nameserver_2", "ns2.ithute.co.ls")

    success, observed, error = verify_domain(
        domain,
        None,
        uuid.uuid4(),
        db,
        resolver=lambda _: [],
        nameserver_resolver=lambda _: ["ns1.ithute.co.ls", "ns2.ithute.co.ls"],
    )

    assert success is False
    assert error == "nameserver_verification_requires_platform_dns"
    assert observed == []
    assert attempts[0].success is False
