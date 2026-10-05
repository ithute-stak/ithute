from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
API = ROOT / "apps/backend/app/api/v1/shared_hosting.py"
INFRA_API = ROOT / "apps/backend/app/api/v1/infrastructure_servers.py"
AGENT = ROOT / "infrastructure/hosting-agent/agent_v4.py"


def test_group_failover_requires_source_fence_before_promotion():
    text = API.read_text()
    assert '@router.post("/hosting/agent/postgres-group-failovers/claim")' in text
    assert 'HostingPostgresGroupFailoverAttempt.status == "source_fenced"' in text
    assert "source_fenced_at.is_not(None)" in text
    assert '"source_fencing_confirmed": True' in text


def test_group_cutover_updates_all_members_atomically_after_promotion():
    text = API.read_text()
    assert "for database in members:" in text
    assert "database.node_id = attempt.target_node_id" in text
    assert "group.primary_node_id = attempt.target_node_id" in text
    assert 'standby.status = "promoted"' in text
    assert 'row.telemetry_error = "Standby must be reconfigured to follow the newly promoted primary"' in text
    commit = text.index("db.commit()", text.index("for database in members:"))
    member_update = text.index("database.node_id = attempt.target_node_id")
    group_update = text.index("group.primary_node_id = attempt.target_node_id")
    assert member_update < commit
    assert group_update < commit


def test_grouped_database_cannot_use_legacy_per_database_failover():
    text = API.read_text()
    assert "Database belongs to a physical PostgreSQL replication group; use group failover" in text


def test_external_fence_can_advance_group_failover_only_for_exact_source_node():
    text = INFRA_API.read_text()
    assert "postgres_group_failover_attempt_id" in text
    assert "server.hosting_node_id == group_failover.source_node_id" in text
    assert 'group_failover.status = "source_fenced"' in text


def test_agent_prioritizes_group_failover_before_legacy_database_failover():
    text = AGENT.read_text()
    group_claim = text.index("group_failover = claim_postgres_group_failover()")
    database_claim = text.index("database_failover = claim_database_failover()")
    assert group_claim < database_claim
    assert "process_postgres_group_failover(group_failover)" in text
    assert "postgres_promote_physical_replica(source_fencing_confirmed=True)" in text
