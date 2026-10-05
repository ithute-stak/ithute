from pathlib import Path

from app.api.v1.infrastructure_servers import _json_roles, _roles, _validated_agent_command


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
