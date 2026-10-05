from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
API = ROOT / "apps/backend/app/api/v1/shared_hosting.py"
AGENT = ROOT / "infrastructure/hosting-agent/agent_v4.py"


def test_failover_api_requires_source_fence_before_target_claim():
    text = API.read_text()
    assert 'status == "source_fenced"' in text
    assert "source_fenced_at.is_not(None)" in text
    assert '"source_fencing_confirmed": True' in text
    assert "Stale database source-fencing token" in text
    assert "Stale database promotion token" in text


def test_agent_physically_stops_source_before_reporting_fence_success():
    text = AGENT.read_text()
    assert 'action == "fence_source"' in text
    assert '["systemctl", "stop", POSTGRES_SERVICE]' in text
    assert '["systemctl", "is-active", POSTGRES_SERVICE]' in text
    assert "remained active after fencing request" in text


def test_agent_refuses_target_promotion_without_control_plane_fencing_confirmation():
    text = AGENT.read_text()
    assert 'action == "promote_target"' in text
    assert 'work.get("source_fencing_confirmed") is not True' in text
    assert "Control plane did not confirm source fencing" in text
    assert "postgres_promote_physical_replica(source_fencing_confirmed=True)" in text


def test_unreachable_source_has_no_automatic_promotion_shortcut():
    api = API.read_text()
    agent = AGENT.read_text()
    assert "source_unreachable" not in api
    assert "source_unreachable" not in agent
    assert "force_promote" not in api
    assert "force_promote" not in agent
