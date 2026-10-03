from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.services import mail_operations_noc as noc


class ScalarRows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeDb:
    def __init__(self, node):
        self.node = node
        self.scalars_calls = 0
        self.scalar_calls = 0

    def scalars(self, _statement):
        self.scalars_calls += 1
        if self.scalars_calls == 1:
            return ScalarRows([self.node])
        return ScalarRows([])

    def scalar(self, _statement):
        self.scalar_calls += 1
        if self.scalar_calls == 1:
            return None  # latest snapshot
        if self.scalar_calls == 2:
            return 12  # mailboxes total
        if self.scalar_calls == 3:
            return 4  # external mailboxes
        if self.scalar_calls == 4:
            return 3  # mail domains
        return 0


def _node(**overrides):
    values = {
        "id": uuid4(),
        "name": "mail-ls-01",
        "hostname": "mail-ls-01.example.net",
        "region": "lesotho",
        "status": "active",
        "last_heartbeat_at": datetime.now(timezone.utc),
        "smtp_ready": True,
        "imap_ready": True,
        "tls_ready": True,
        "backup_ready": True,
        "readiness_error": None,
        "backup_error": None,
        "total_storage_bytes": 1000,
        "used_storage_bytes": 250,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_noc_reports_ready_node_and_capacity(monkeypatch):
    monkeypatch.setattr(noc, "_safe_runtime", lambda: {"status": "ok", "services": {}, "mail_queue_total": 0})
    monkeypatch.setattr(noc, "_safe_queue", lambda: {"total": 0})
    monkeypatch.setattr(noc, "_safe_tls", lambda: {"ready": True})

    result = noc.mail_operations_noc(FakeDb(_node()))

    assert result["overall_status"] == "healthy"
    assert result["summary"]["nodes_ready"] == 1
    assert result["summary"]["mailboxes_total"] == 12
    assert result["summary"]["mailboxes_external"] == 4
    assert result["summary"]["mail_domains"] == 3
    assert result["nodes"][0]["storage_percent"] == 25.0


def test_noc_marks_fleet_attention_when_active_node_is_unready(monkeypatch):
    monkeypatch.setattr(noc, "_safe_runtime", lambda: {"status": "ok", "services": {}, "mail_queue_total": 0})
    monkeypatch.setattr(noc, "_safe_queue", lambda: {})
    monkeypatch.setattr(noc, "_safe_tls", lambda: {})

    result = noc.mail_operations_noc(FakeDb(_node(smtp_ready=False)))

    assert result["overall_status"] == "critical"
    assert result["summary"]["nodes_ready"] == 0
    assert result["nodes"][0]["ready"] is False
