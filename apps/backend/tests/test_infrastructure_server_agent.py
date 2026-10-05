from pathlib import Path

from app.api.v1.infrastructure_servers import _json_roles, _roles, _security_findings, _validated_agent_command


def test_server_agent_roles_remain_scoped():
    assert _roles(["mail", "database", "storage"]) == ["database", "mail", "storage"]
    assert _json_roles('["application","database"]') == ["application", "database"]


def test_server_agent_contract_and_packaging_exist():
    root = Path(__file__).parents[2]
    api = (root / "app" / "api" / "v1" / "infrastructure_servers.py").read_text(encoding="utf-8")
    model = (root / "app" / "models" / "infrastructure.py").read_text(encoding="utf-8")
    frontend = (root.parent / "frontend" / "app" / "infrastructure" / "servers" / "page.tsx").read_text(encoding="utf-8")
    repo = root.parents[1]
    agent = (repo / "infrastructure" / "server-agent" / "agent.py").read_text(encoding="utf-8")
    service = (repo / "infrastructure" / "server-agent" / "ithute-server-agent.service").read_text(encoding="utf-8")

    assert "class InfrastructureServerAgent" in model
    assert '@router.post("/servers/{server_id}/agent-token")' in api
    assert '@router.post("/agent/heartbeat")' in api
    assert "X-Ithute-Server-Agent" in agent
    assert "cpu_percent" in agent
    assert "docker_info" in agent
    assert '"postgresql"' in agent
    assert '"mysql"' in agent
    assert '"mongodb"' in agent
    assert '"redis"' in agent
    assert "Create token" in frontend
    assert "Physical server agent" in frontend
    assert "NoNewPrivileges=true" in service
    assert "ProtectSystem=strict" in service


def test_structured_agent_commands_are_allowlisted_and_guarded():
    assert _validated_agent_command("agent.ping", {"ignored": True}) == ("agent.ping", {})
    assert _validated_agent_command("service.restart", {"unit": "postgresql"}) == (
        "service.restart",
        {"unit": "postgresql.service"},
    )
    assert _validated_agent_command("container.restart", {"container": "ithute-web"}) == (
        "container.restart",
        {"container": "ithute-web"},
    )

    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        _validated_agent_command("shell.exec", {"command": "rm -rf /"})
    with pytest.raises(HTTPException):
        _validated_agent_command("service.restart", {"unit": "sshd"})


def test_agent_operations_and_container_drift_contract_exist():
    root = Path(__file__).parents[2]
    api = (root / "app" / "api" / "v1" / "infrastructure_servers.py").read_text(encoding="utf-8")
    model = (root / "app" / "models" / "infrastructure.py").read_text(encoding="utf-8")
    migration = (root / "alembic" / "versions" / "0072_infrastructure_agent_ops.py").read_text(encoding="utf-8")
    frontend = (root.parent / "frontend" / "app" / "infrastructure" / "servers" / "[serverId]" / "page.tsx").read_text(encoding="utf-8")
    repo = root.parents[1]
    agent = (repo / "infrastructure" / "server-agent" / "agent.py").read_text(encoding="utf-8")

    assert "class InfrastructureAgentCommand" in model
    assert "class InfrastructureContainerSnapshot" in model
    assert "infrastructure_agent_commands" in migration
    assert "infrastructure_container_snapshots" in migration
    assert '@router.post("/servers/{server_id}/commands"' in api
    assert '@router.post("/agent/commands/next")' in api
    assert '@router.post("/agent/commands/{command_id}/result")' in api
    assert '@router.get("/servers/{server_id}/container-inventory")' in api
    assert '"ithute.project_id"' in agent
    assert "poll_command" in agent
    assert "execute_structured_command" in agent
    assert "Agent operations & container drift" in frontend


def test_host_security_findings_score_risky_configuration():
    result = _security_findings({
        "security": {
            "sshd": {"permit_root_login": "yes", "password_authentication": "yes"},
            "firewall": {"provider": "ufw", "active": False},
            "fail2ban_active": False,
            "unattended_upgrades_active": False,
            "docker": {"socket_mode": "0o666", "socket_world_writable": True, "privileged_running_containers": 1},
            "risky_public_listeners": [{"port": 5432, "bind": "0.0.0.0"}],
        }
    })
    assert result["posture"] == "critical"
    assert result["score"] < 50
    assert len(result["fingerprint_sha256"]) == 64
    keys = {item["key"] for item in result["findings"]}
    assert "docker.socket_world_writable" in keys
    assert "network.risky_public_ports" in keys


def test_missing_v3_security_telemetry_fails_closed():
    result = _security_findings({})
    assert result["posture"] == "critical"
    assert result["score"] == 50
    assert result["findings"][0]["key"] == "agent.security_unavailable"


def test_security_readiness_donor_contract_exists():
    root = Path(__file__).parents[2]
    api = (root / "app" / "api" / "v1" / "infrastructure_servers.py").read_text(encoding="utf-8")
    model = (root / "app" / "models" / "infrastructure.py").read_text(encoding="utf-8")
    migration = (root / "alembic" / "versions" / "0073_infrastructure_security.py").read_text(encoding="utf-8")
    frontend = (root.parent / "frontend" / "app" / "infrastructure" / "servers" / "[serverId]" / "page.tsx").read_text(encoding="utf-8")
    repo = root.parents[1]
    agent = (repo / "infrastructure" / "server-agent" / "agent.py").read_text(encoding="utf-8")

    assert "class InfrastructureSecuritySnapshot" in model
    assert "infrastructure_security_snapshots" in migration
    assert '@router.get("/servers/{server_id}/security")' in api
    assert '@router.get("/servers/{server_id}/readiness")' in api
    assert 'execute_binary("crypto.sha256"' in api
    assert "execute_network(targets" in api
    assert "security_posture" in agent
    assert "backup_tools" in agent
    assert "Production readiness & host security" in frontend
    assert "Java remains the enterprise/XML engine" in frontend
    assert "C++ remains the native blob/fingerprint accelerator" in frontend


def test_cluster_awareness_contract_exists_and_remains_read_only():
    root = Path(__file__).parents[2]
    api = (root / "app" / "api" / "v1" / "infrastructure_servers.py").read_text(encoding="utf-8")
    repo = root.parents[1]
    agent = (repo / "infrastructure" / "server-agent" / "agent.py").read_text(encoding="utf-8")
    service = (repo / "infrastructure" / "server-agent" / "ithute-server-agent.service").read_text(encoding="utf-8")
    readme = (repo / "infrastructure" / "server-agent" / "README.md").read_text(encoding="utf-8")

    assert '@router.get("/agent/cluster-state")' in api
    assert '"fingerprint_sha256"' in api
    assert '"private_network"' in api
    assert '"workloads"' in api
    assert '"resource_usage"' in api
    assert '"docker"' in api
    assert "token_hint" not in api[api.index("def _cluster_node_out"):api.index('@router.post("/servers/{server_id}/agent-token")')]

    assert "sync_cluster_state" in agent
    assert "/platform/infrastructure/agent/cluster-state" in agent
    assert "/var/lib/ithute/server-agent/cluster-state.json" in agent
    assert "os.replace(temporary, CLUSTER_STATE_PATH)" in agent
    assert "shell.exec" not in agent
    assert "ReadWritePaths=/var/log/ithute /var/lib/ithute/server-agent" in service
    assert "read-only discovery" in readme
