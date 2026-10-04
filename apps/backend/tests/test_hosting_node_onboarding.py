from pathlib import Path

from app.services.hosting_node_bootstrap import render_hosting_node_bootstrap


def test_rendered_bootstrap_installs_both_agents_without_public_origin():
    script = render_hosting_node_bootstrap(
        api_base_url="https://ithute.co.ls",
        hosting_token="ith_host_example",
        server_token="ith_srv_example",
        origin_bind_ip="10.20.0.15",
        edge_origin_cidrs="10.20.0.10/32",
        backup_remote=None,
    )

    assert "ITHUTE_HOSTING_AGENT_TOKEN=ith_host_example" in script
    assert "ITHUTE_SERVER_AGENT_TOKEN=ith_srv_example" in script
    assert "/api/v1/hosting/agent/network/enroll" in script
    assert "wg genkey" in script
    assert "systemctl enable --now wg-quick@ithute0" in script
    assert "ITHUTE_HOSTING_ORIGIN_BIND_IP=$ORIGIN_BIND_IP" in script
    assert "systemctl enable --now ithute-hosting-agent.service" in script
    assert "systemctl enable --now ithute-server-agent.service" in script
    assert "/opt/ithute-hosting-node/validate-host.sh" in script
    assert "0.0.0.0" not in script


def test_secure_onboarding_contract_exists():
    root = Path(__file__).parents[2]
    api = (root / "app" / "api" / "v1" / "hosting_operations.py").read_text(encoding="utf-8")
    model = (root / "app" / "models" / "hosting_operations.py").read_text(encoding="utf-8")
    agent = (root.parents[1] / "infrastructure" / "hosting-agent" / "agent.py").read_text(encoding="utf-8")
    frontend = (root.parent / "frontend" / "app" / "hosting-nodes" / "page.tsx").read_text(encoding="utf-8")

    assert "class HostingNodeBootstrap" in model
    assert '@router.post("/platform/hosting/nodes/{node_id}/bootstrap")' in api
    assert '@router.get("/hosting/bootstrap/{node_id}/script"' in api
    assert "Bootstrap credential has already been used" in api
    assert "timedelta(minutes=15)" in api
    assert 'node.status = "draining"' in api
    assert "node.accepts_new_projects = False" in api
    assert '@router.post("/platform/hosting/nodes/{node_id}/activate")' in api
    assert "origin_bind_ip" in agent
    assert "managed_private_network" in api
    assert "managed_network_connected" in api
    assert "Generate secure installer" in frontend
    assert "Copy safe install command" in frontend
    assert "Activate node" in frontend
    assert "does not enter shell history" in frontend
