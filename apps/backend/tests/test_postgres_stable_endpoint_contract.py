from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
API = ROOT / "apps/backend/app/api/v1/shared_hosting.py"
ROUTER = ROOT / "engines/go-worker/cmd/db-router/main.go"


def test_gateway_uses_scoped_credential_and_generation_ack():
    text = API.read_text()
    assert '"ith_dbgw_" + secrets.token_urlsafe(36)' in text
    assert "X-Ithute-Database-Gateway" not in text  # FastAPI header name is generated from the parameter.
    assert "x_ithute_database_gateway" in text
    assert "Stale PostgreSQL endpoint route generation" in (
        ROOT / "apps/backend/app/services/postgres_endpoints.py"
    ).read_text()


def test_group_failover_switches_endpoint_before_commit_and_waits_for_route_ack():
    text = API.read_text()
    completion = text.index("endpoint = switch_postgres_endpoint_to_primary")
    pending = text.index("attempt.service_restored_at = None", completion)
    commit = text.index("db.commit()", completion)
    assert completion < pending < commit
    ack = text.index("def database_gateway_route_ack")
    restored = text.index("attempt.service_restored_at = restored_at", ack)
    assert restored > ack


def test_database_output_prefers_stable_endpoint_when_grouped():
    text = API.read_text()
    assert '"stable_endpoint": endpoint_payload' in text
    assert "host = endpoint.hostname" in text
    assert "port = endpoint.listen_port" in text


def test_go_router_requires_https_by_default_and_probes_target_before_ack():
    text = ROUTER.read_text()
    assert 'database gateway control-plane URL must use HTTPS' in text
    assert 'strings.HasPrefix(cfg.Token, "ith_dbgw_")' in text
    assert "manager.probe(r)" in text
    assert "api.ack(callCtx, r.EndpointID, r.Generation)" in text
    assert text.index("manager.probe(r)") < text.index("api.ack(callCtx, r.EndpointID, r.Generation)")
    assert "shell" not in text.lower()
