from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
INFRA_API = ROOT / "apps/backend/app/api/v1/infrastructure_servers.py"
FAILOVER_API = ROOT / "apps/backend/app/api/v1/shared_hosting.py"
FENCING = ROOT / "apps/backend/app/services/external_fencing.py"


def test_external_fence_controller_uses_scoped_credentials_and_per_attempt_claim_tokens():
    text = INFRA_API.read_text()
    assert '"ith_fence_" + secrets.token_urlsafe(36)' in text
    assert 'x_ithute_fence_controller' in text
    assert 'claim_token_hash = hash_token(raw_claim)' in text
    assert 'hash_token(payload.claim_token) != row.claim_token_hash' in text


def test_external_fence_success_requires_positive_power_or_isolation_state():
    text = INFRA_API.read_text()
    assert 'payload.observed_state not in {"powered_off", "isolated"}' in text
    assert "Successful external fence requires powered_off or isolated observation" in text


def test_external_fence_can_confirm_linked_database_source_only_for_matching_hosting_node():
    text = INFRA_API.read_text()
    assert "server.hosting_node_id == failover.source_node_id" in text
    assert 'failover.status in {"requested", "fence_claimed"}' in text
    assert 'failover.status = "source_fenced"' in text
    assert "failover.source_fenced_at = now" in text


def test_database_failover_queues_external_fence_but_has_no_unreachable_shortcut():
    api = FAILOVER_API.read_text()
    service = FENCING.read_text()
    assert "queue_external_fence_for_database_failover" in api
    assert 'InfrastructureFenceController.status == "active"' in service
    assert "source_unreachable" not in api
    assert "force_promote" not in api
    assert "heartbeat_missing" not in service
