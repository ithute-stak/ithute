"""PostgreSQL-backed DNSSEC incident lifecycle regression tests."""
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.models.domains import Domain
from app.models.dnssec_incident_history import DnssecIncidentHistory, DnssecMonitorState
from app.services.dnssec_monitor_persistence import record_dnssec_observation


@pytest.fixture
def managed_domain(db, tenant_admin):
    user, tenant, _ = tenant_admin
    domain = Domain(
        tenant_id=tenant.id,
        ascii_name=f"dnssec-{uuid4().hex[:12]}.example.com",
        unicode_name=f"dnssec-{uuid4().hex[:12]}.example.com",
        verification_token_hash="0" * 64,
        verification_token_hint="test",
        verification_record_name="_ithute-validation.example.com",
        created_by_user_id=user.id,
    )
    db.add(domain)
    db.commit()
    try:
        yield tenant, domain
    finally:
        db.rollback()
        db.execute(delete(DnssecIncidentHistory).where(DnssecIncidentHistory.domain_id == domain.id))
        db.execute(delete(DnssecMonitorState).where(DnssecMonitorState.domain_id == domain.id))
        db.execute(delete(Domain).where(Domain.id == domain.id))
        db.commit()


def test_open_once_recover_and_preserve_history(db, managed_domain):
    tenant, domain = managed_domain
    failure = {"severity": "warning", "code": "DNS_RESOLVER_SERVFAIL", "summary": "Resolver failed"}
    events = []
    for _ in range(5):
        result = record_dnssec_observation(db, tenant_id=tenant.id, domain_id=domain.id, observation=failure)
        events += result["events"]
        db.commit()
    assert events == ["opened"]
    incidents = db.scalars(select(DnssecIncidentHistory).where(DnssecIncidentHistory.domain_id == domain.id)).all()
    assert len(incidents) == 1
    assert incidents[0].status == "open"

    record_dnssec_observation(db, tenant_id=tenant.id, domain_id=domain.id,
                              observation={"severity": "unknown", "code": "RESOLVER_UNAVAILABLE"})
    db.commit()
    db.refresh(incidents[0])
    assert incidents[0].status == "open"

    result = record_dnssec_observation(db, tenant_id=tenant.id, domain_id=domain.id,
                                       observation={"severity": "healthy", "code": "DNSSEC_VALIDATED"})
    db.commit()
    db.refresh(incidents[0])
    assert result["events"] == ["recovered"]
    assert incidents[0].status == "recovered"
    assert incidents[0].recovered_at is not None


def test_changed_failure_supersedes_old_incident_after_confirmation(db, managed_domain):
    tenant, domain = managed_domain
    first = {"severity": "warning", "code": "DNS_RESOLVER_SERVFAIL"}
    second = {"severity": "warning", "code": "DNSSEC_PARENT_DS_UNVERIFIED"}
    for _ in range(3):
        record_dnssec_observation(db, tenant_id=tenant.id, domain_id=domain.id, observation=first)
        db.commit()
    for _ in range(2):
        record_dnssec_observation(db, tenant_id=tenant.id, domain_id=domain.id, observation=second)
        db.commit()
    old = db.scalar(select(DnssecIncidentHistory).where(DnssecIncidentHistory.domain_id == domain.id,
                                                        DnssecIncidentHistory.code == first["code"]))
    assert old.status == "open"
    record_dnssec_observation(db, tenant_id=tenant.id, domain_id=domain.id, observation=second)
    db.commit()
    db.refresh(old)
    assert old.status == "superseded"
    latest = db.scalar(select(DnssecIncidentHistory).where(DnssecIncidentHistory.domain_id == domain.id,
                                                           DnssecIncidentHistory.code == second["code"]))
    assert latest.status == "open"


def test_wrong_tenant_cannot_write_monitor_state(db, managed_domain):
    tenant, domain = managed_domain
    with pytest.raises(ValueError, match="Domain not found"):
        record_dnssec_observation(db, tenant_id=uuid4(), domain_id=domain.id,
                                  observation={"severity": "warning", "code": "DNS_RESOLVER_SERVFAIL"})
    db.rollback()
    assert db.get(DnssecMonitorState, domain.id) is None
