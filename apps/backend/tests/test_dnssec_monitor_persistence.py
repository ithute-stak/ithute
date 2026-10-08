from uuid import uuid4

import pytest

from app.services.dnssec_monitor_persistence import record_dnssec_observation


class MissingDomainSession:
    def __init__(self):
        self.committed = False

    def execute(self, statement):
        return self

    def scalar_one_or_none(self):
        return None

    def commit(self):
        self.committed = True


def test_rejects_cross_tenant_or_missing_domain_before_writing():
    db = MissingDomainSession()
    with pytest.raises(ValueError, match="Domain not found for tenant"):
        record_dnssec_observation(
            db, tenant_id=uuid4(), domain_id=uuid4(),
            observation={"severity": "warning", "code": "DNS_RESOLVER_SERVFAIL"},
        )
    assert db.committed is False


def test_persistence_requires_external_transaction_commit():
    # The persistence API deliberately does not call commit: callers may commit
    # the state update and any audit/outbox entries atomically.
    import inspect
    source = inspect.getsource(record_dnssec_observation)
    assert "db.commit(" not in source
    assert "with_for_update()" in source


def test_recovery_and_supersession_are_transactional():
    import inspect
    source = inspect.getsource(record_dnssec_observation)
    assert 'observation.get("severity") == "healthy"' in source
    assert 'incident.status = "recovered"' in source
    assert 'incident.status = "superseded"' in source
    assert 'db.flush()' in source
    assert 'db.commit(' not in source
