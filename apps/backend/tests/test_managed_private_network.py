from pathlib import Path

from app.services.managed_network import edge_address
from app.services.hosting_node_bootstrap import render_hosting_node_bootstrap


def test_managed_network_uses_private_configured_subnet(monkeypatch):
    monkeypatch.setenv("ITHUTE_WIREGUARD_SUBNET", "10.77.0.0/24")
    monkeypatch.setenv("ITHUTE_WIREGUARD_EDGE_ADDRESS", "10.77.0.1")
    assert edge_address() == "10.77.0.1"


def test_bootstrap_generates_node_private_key_locally():
    script = render_hosting_node_bootstrap(
        api_base_url="https://ithute.co.ls",
        hosting_token="ith_host_example",
        server_token="ith_srv_example",
        origin_bind_ip=None,
        edge_origin_cidrs="",
        backup_remote=None,
        managed_private_network=True,
    )

    assert "wg genkey > /etc/wireguard/ithute0.key" in script
    assert 'WG_PUBLIC_KEY="$(printf' in script
    assert "/api/v1/hosting/agent/network/enroll" in script
    assert "systemctl enable --now wg-quick@ithute0" in script
    assert "PrivateKey = $WG_PRIVATE_KEY" in script
    assert "private.key" not in script.split("NETWORK_JSON=", 1)[-1].split("cat > /etc/wireguard/ithute0.conf", 1)[0]


def test_managed_network_contract_exists():
    root = Path(__file__).parents[2]
    api = (root / "app" / "api" / "v1" / "managed_network.py").read_text(encoding="utf-8")
    onboarding = (root / "app" / "api" / "v1" / "hosting_operations.py").read_text(encoding="utf-8")
    server_agent = (root.parents[1] / "infrastructure" / "server-agent" / "agent.py").read_text(encoding="utf-8")
    edge_reconcile = (root.parents[1] / "infrastructure" / "wireguard-edge" / "reconcile.sh").read_text(encoding="utf-8")
    frontend = (root.parent / "frontend" / "app" / "infrastructure" / "network" / "page.tsx").read_text(encoding="utf-8")

    assert '@router.post("/hosting/agent/network/enroll")' in api
    assert '@router.get("/infrastructure/private-network/edge-peers")' in api
    assert "hmac.compare_digest" in api
    assert "managed_network_connected" in onboarding
    assert '"wireguard": wireguard_info()' in server_agent
    assert "wg syncconf ithute0" in edge_reconcile
    assert "PrivateKey" in edge_reconcile
    assert "Managed private network" in frontend
    assert "last handshake" in frontend.lower()
