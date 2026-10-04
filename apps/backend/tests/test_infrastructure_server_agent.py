from pathlib import Path

from app.api.v1.infrastructure_servers import _json_roles, _roles


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
