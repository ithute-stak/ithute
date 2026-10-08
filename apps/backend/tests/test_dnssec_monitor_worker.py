"""DNSSEC monitoring worker remains opt-in and fails safely."""
from app.workers import dnssec_monitor


def test_worker_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ITHUTE_DNSSEC_MONITOR_ENABLED", raising=False)
    monkeypatch.setattr(dnssec_monitor, "SessionLocal", lambda: (_ for _ in ()).throw(AssertionError("worker should not open DB")))
    assert dnssec_monitor.main() == 0


def test_worker_invokes_runner_when_enabled(monkeypatch):
    class Session:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False

    calls = []
    monkeypatch.setenv("ITHUTE_DNSSEC_MONITOR_ENABLED", "true")
    monkeypatch.setenv("ITHUTE_DNSSEC_MONITOR_BATCH_SIZE", "25")
    monkeypatch.setattr(dnssec_monitor, "SessionLocal", Session)
    monkeypatch.setattr(dnssec_monitor, "run_dnssec_monitor", lambda db, limit: calls.append(limit) or {"checked": 1, "failed": 0})
    assert dnssec_monitor.main() == 0
    assert calls == [25]


def test_worker_returns_failure_when_runner_fails(monkeypatch):
    monkeypatch.setenv("ITHUTE_DNSSEC_MONITOR_ENABLED", "true")
    monkeypatch.setenv("ITHUTE_DNSSEC_MONITOR_BATCH_SIZE", "not-an-integer")
    assert dnssec_monitor.main() == 1
