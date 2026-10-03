from types import SimpleNamespace
from uuid import uuid4

from app.models.domain_health import DomainHealthMonitorState
from app.models.business import Notification
from app.services import domain_health_monitor as monitor


class ScalarRows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeDb:
    def __init__(self, domain, state=None):
        self.domain = domain
        self.state = state
        self.added = []
        self.commits = 0

    def scalars(self, statement):
        return ScalarRows([self.domain])

    def get(self, model, key):
        if model is DomainHealthMonitorState and self.state and self.state.domain_id == key:
            return self.state
        return None

    def add(self, value):
        self.added.append(value)
        if isinstance(value, DomainHealthMonitorState):
            self.state = value

    def commit(self):
        self.commits += 1


def _domain():
    return SimpleNamespace(
        id=uuid4(),
        tenant_id=uuid4(),
        ascii_name="client.co.ls",
        mail_enabled=True,
    )


def test_monitor_warns_once_on_first_degradation(monkeypatch):
    domain = _domain()
    db = FakeDb(domain)
    monkeypatch.setattr(
        monitor,
        "domain_mail_health",
        lambda *_args: {
            "overall_status": "attention",
            "score": 75,
            "checks": [
                {"id": "spf", "required": True, "status": "attention"},
                {"id": "autoconfig", "required": False, "status": "attention"},
            ],
        },
    )

    first = monitor.run_domain_health_monitor(db)
    warning_count = sum(isinstance(item, Notification) for item in db.added)
    assert first["notifications_created"] == 1
    assert warning_count == 1
    assert db.state.last_status == "attention"

    db.added.clear()
    second = monitor.run_domain_health_monitor(db)
    assert second["notifications_created"] == 0
    assert not any(isinstance(item, Notification) for item in db.added)


def test_monitor_notifies_recovery(monkeypatch):
    domain = _domain()
    state = DomainHealthMonitorState(
        domain_id=domain.id,
        tenant_id=domain.tenant_id,
        last_status="attention",
        last_score=60,
        failing_checks_json='["dkim"]',
    )
    db = FakeDb(domain, state)
    monkeypatch.setattr(
        monitor,
        "domain_mail_health",
        lambda *_args: {
            "overall_status": "healthy",
            "score": 100,
            "checks": [{"id": "dkim", "required": True, "status": "healthy"}],
        },
    )

    result = monitor.run_domain_health_monitor(db)

    notifications = [item for item in db.added if isinstance(item, Notification)]
    assert result["recovered"] == 1
    assert result["notifications_created"] == 1
    assert len(notifications) == 1
    assert notifications[0].severity == "success"
    assert db.state.last_status == "healthy"
    assert db.state.first_unhealthy_at is None
