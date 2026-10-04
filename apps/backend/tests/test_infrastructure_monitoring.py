from pathlib import Path

from app.api.v1.infrastructure_servers import _telemetry_values


def test_telemetry_values_extracts_peak_disk_and_resource_usage():
    values = _telemetry_values({
        "cpu": {"used_percent": 71.5, "load_1m": 2.2},
        "memory": {"used_percent": 64.0},
        "disks": [{"used_percent": 55.0}, {"used_percent": 88.0}],
        "docker": {"containers_running": 4, "containers_total": 6},
    })

    assert values["cpu_percent"] == 71.5
    assert values["memory_percent"] == 64.0
    assert values["disk_percent"] == 88.0
    assert values["load_1m"] == 2.2
    assert values["docker_running"] == 4
    assert values["docker_total"] == 6


def test_monitoring_contract_and_detail_page_exist():
    root = Path(__file__).parents[1]
    api = (root / "app" / "api" / "v1" / "infrastructure_servers.py").read_text(encoding="utf-8")
    model = (root / "app" / "models" / "infrastructure.py").read_text(encoding="utf-8")
    page = (root.parent / "frontend" / "app" / "infrastructure" / "servers" / "[serverId]" / "page.tsx").read_text(encoding="utf-8")

    assert "class InfrastructureTelemetrySnapshot" in model
    assert '@router.get("/servers/network-health")' in api
    assert "execute_network(targets, concurrency=24)" in api
    assert '"advisory_only": True' in api
    assert '@router.get("/servers/{server_id}/history")' in api
    assert "disk_pressure" in api
    assert "agent_offline" in api
    assert "cpu_high" in api
    assert "memory_high" in api
    assert "Telemetry history" in page
    assert "Alert thresholds" in page
    assert "Service & capability health" in page
    assert "Five-minute samples are retained for seven days." in page
