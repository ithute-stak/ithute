from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
API = ROOT / "apps/backend/app/api/v1/shared_hosting.py"
AGENT = ROOT / "infrastructure/hosting-agent/agent_v4.py"
SERVICE = ROOT / "apps/backend/app/services/postgres_topology_repair.py"
ENV = ROOT / "infrastructure/hosting-node/agent.env.example"


def test_repair_planner_prefers_rewind_only_with_checksum_evidence():
    text = SERVICE.read_text()
    assert 'postgres.get("pg_rewind_available") is True' in text
    assert 'postgres.get("data_checksums") is True' in text
    assert 'return "basebackup"' in text


def test_failed_rewind_enqueues_basebackup_fallback():
    text = API.read_text()
    assert 'if row.method == "rewind":' in text
    assert 'method="basebackup"' in text
    assert '"fallback_repair_id": fallback_id' in text


def test_successful_repair_requires_verified_wal_positions():
    text = API.read_text()
    assert "Successful topology repair requires verified WAL positions" in text
    assert "standby.receive_lsn = payload.receive_lsn" in text
    assert "standby.replay_lsn = payload.replay_lsn" in text
    assert "standby.replay_backlog_bytes = payload.replay_backlog_bytes" in text


def test_agent_checks_offline_checksum_state_before_pg_rewind():
    text = AGENT.read_text()
    assert "def _postgres_checksums_enabled_offline()" in text
    assert "PG_CONTROLDATA" in text
    assert "Data page checksum version:" in text
    assert "pg_rewind requires locally verified PostgreSQL page checksums" in text


def test_repair_credentials_remain_node_local():
    api = API.read_text()
    agent = AGENT.read_text()
    env = ENV.read_text()
    assert "POSTGRES_REPLICATION_PASSWORD" not in api
    assert "ITHUTE_HOSTING_POSTGRES_REPLICATION_PASSWORD" in agent
    assert "ITHUTE_HOSTING_POSTGRES_REPLICATION_PASSWORD" in env
    assert '"source": source' in api


def test_agent_verifies_streaming_after_repair():
    text = AGENT.read_text()
    assert "Repaired PostgreSQL node did not enter standby recovery mode" in text
    assert "Repaired PostgreSQL node is not streaming WAL from the new primary" in text
    assert "process_postgres_topology_repair" in text
