"""Guard the DNSSEC monitoring runner's execution boundaries."""
import pytest
from app.services.dnssec_monitor_runner import run_dnssec_monitor


def test_rejects_unbounded_scan_before_database_use():
    with pytest.raises(ValueError, match="limit"):
        run_dnssec_monitor(None, limit=0)
    with pytest.raises(ValueError, match="limit"):
        run_dnssec_monitor(None, limit=1001)


def test_runner_does_not_modify_dns_or_registrar_records():
    import inspect
    source = inspect.getsource(run_dnssec_monitor)
    assert "publish(" not in source
    assert "set_dnssec(" not in source
    assert "remove_managed(" not in source
    assert "pg_try_advisory_xact_lock" in source
    assert "db.begin_nested()" in source
