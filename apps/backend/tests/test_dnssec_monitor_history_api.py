"""Guard tenant scoping and read-only DNSSEC incident history wiring."""
from pathlib import Path


API = Path(__file__).resolve().parents[1] / "app/api/v1/dns_phase5.py"
UI = Path(__file__).resolve().parents[2] / "frontend/app/dns-security/page.tsx"


def test_history_api_requires_permission_and_tenant_scoping():
    src = API.read_text()
    handler = src.split('def dnssec_monitor_history(', 1)[1].split('@router.get("/dnssec")', 1)[0]
    assert 'require_tenant_permission(tenant_id, "dns.read", db, current)' in handler
    assert '_managed_domain(db, tenant_id, domain_id)' in handler
    assert "DnssecIncidentHistory.tenant_id == tenant_id" in handler
    assert "DnssecIncidentHistory.domain_id == domain.id" in handler
    assert "DnssecMonitorState.tenant_id == tenant_id" in handler
    assert "limit(50)" in handler
    assert '"read_only": True' in handler


def test_history_ui_shows_absence_of_monitoring_without_fake_health():
    src = UI.read_text()
    assert "/dnssec/monitor-history" in src
    assert '"Not yet monitored"' in src
    assert "No DNSSEC incidents recorded." in src
    assert "refreshing this page does not start it" in src.lower()
