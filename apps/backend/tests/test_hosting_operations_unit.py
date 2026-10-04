import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.v1.hosting_operations import _validate_image_ref, _validate_source_commit
from app.models import HostingNode, HostingNodeAgent, HostingNodeHealthState, InfrastructureServer, InfrastructureServerAgent, InfrastructureWireGuardPeer
from app.services import hosting_node_health


def test_deployment_requires_immutable_sha256_image_reference():
    image, digest = _validate_image_ref(
        "ghcr.io/ithute-stak/hosted-customer-app@sha256:" + "a" * 64
    )
    assert image.endswith("@" + digest)
    assert digest == "sha256:" + "a" * 64

    with pytest.raises(HTTPException) as exc:
        _validate_image_ref("ghcr.io/ithute-stak/hosted-customer-app:latest")
    assert exc.value.status_code == 422

    with pytest.raises(HTTPException) as exc:
        _validate_image_ref("ghcr.io/example/customer-app@sha256:" + "b" * 64)
    assert exc.value.status_code == 422


def test_source_commit_accepts_git_hex_and_rejects_untrusted_text():
    assert _validate_source_commit("ABCDEF0123456789") == "abcdef0123456789"
    assert _validate_source_commit(None) is None

    with pytest.raises(HTTPException) as exc:
        _validate_source_commit("main; rm -rf /")
    assert exc.value.status_code == 422



def test_edge_private_network_bootstrap_contract_and_shell_syntax():
    repo = Path(__file__).resolve().parents[3]
    scripts = [
        repo / "infrastructure" / "wireguard-edge" / "bootstrap.sh",
        repo / "infrastructure" / "wireguard-edge" / "reconcile.sh",
        repo / "infrastructure" / "wireguard-edge" / "firewall.sh",
        repo / "scripts" / "bootstrap-vps.sh",
        repo / "scripts" / "deploy-production.sh",
        repo / "scripts" / "deploy-production-manual.sh",
        repo / "scripts" / "verify-production-readiness.sh",
    ]
    for script in scripts:
        subprocess.run(["bash", "-n", str(script)], check=True)

    bootstrap = scripts[0].read_text(encoding="utf-8")
    deploy = (repo / "scripts" / "deploy-production.sh").read_text(encoding="utf-8")
    manual = (repo / "scripts" / "deploy-production-manual.sh").read_text(encoding="utf-8")
    fresh = (repo / "scripts" / "bootstrap-vps.sh").read_text(encoding="utf-8")
    firewall_service = (repo / "infrastructure" / "wireguard-edge" / "ithute-wireguard-edge-firewall.service").read_text(encoding="utf-8")

    assert "wg genkey" in bootstrap
    assert "ITHUTE_WIREGUARD_RECONCILER_TOKEN" in bootstrap
    assert "systemctl enable --now wg-quick@ithute0" in bootstrap
    assert "systemctl enable --now ithute-wireguard-edge-reconciler.timer" in bootstrap
    assert "ithute-wireguard-edge-firewall.service" in bootstrap
    assert "configure_edge_private_network" in deploy
    assert "verify_edge_private_network" in deploy
    assert "infrastructure/wireguard-edge/bootstrap.sh" in manual
    assert "raw.githubusercontent.com/ithute-stak/ithute/$IMAGE_TAG" in fresh
    assert "CapabilityBoundingSet=CAP_NET_ADMIN" in firewall_service



def _healthy_node_graph(db, owner):
    now = datetime.now(timezone.utc)
    node = HostingNode(
        name=f"health-node-{owner.id}",
        hostname=f"health-{owner.id}.test",
        public_ip="192.0.2.10",
        allocatable_storage_mb=4096,
        allocatable_memory_mb=4096,
        allocatable_cpu_millicores=4000,
        status="draining",
        accepts_new_projects=False,
        created_by_user_id=owner.id,
    )
    db.add(node)
    db.flush()
    server = InfrastructureServer(
        name=node.name,
        hostname=node.hostname,
        public_ip=node.public_ip,
        region="lesotho",
        roles_json='["application","database","storage"]',
        status="active",
        hosting_node_id=node.id,
        created_by_user_id=owner.id,
    )
    db.add(server)
    db.flush()
    peer = InfrastructureWireGuardPeer(
        server_id=server.id,
        public_key="A" * 43 + "=",
        assigned_ipv4="10.70.0.2",
        status="active",
        last_handshake_at=now,
    )
    hosting_agent = HostingNodeAgent(
        node_id=node.id,
        token_hash=f"host-{owner.id}",
        token_hint="health-host-token",
        agent_version="test",
        last_seen_at=now,
        origin_bind_ip="10.70.0.2",
        rotated_at=now,
        rotated_by_user_id=owner.id,
    )
    telemetry = {
        "wireguard": {"connected": True, "address": "10.70.0.2"},
        "docker": {"installed": True, "reachable": True},
        "disks": [{"used_percent": 20.0}],
    }
    server_agent = InfrastructureServerAgent(
        server_id=server.id,
        token_hash=f"server-{owner.id}",
        token_hint="health-server-token",
        agent_version="test",
        last_seen_at=now,
        telemetry_json=json.dumps(telemetry),
        capabilities_json="{}",
        rotated_at=now,
        rotated_by_user_id=owner.id,
    )
    state = HostingNodeHealthState(
        node_id=node.id,
        automation_enabled=True,
        health_status="healthy",
        healthy_since=now - timedelta(seconds=hosting_node_health.AUTO_ACTIVATE_SECONDS + 5),
        last_transition="bootstrap_exchanged",
    )
    db.add_all([peer, hosting_agent, server_agent, state])
    db.flush()
    return now, node, server, peer, hosting_agent, server_agent, state


def test_node_self_healing_activates_drains_and_recovers(db, platform_owner):
    now, node, server, peer, hosting_agent, server_agent, state = _healthy_node_graph(db, platform_owner)

    result = hosting_node_health.reconcile_node_health(db, node, now=now)
    assert result["healthy"] is True
    assert node.status == "active"
    assert node.accepts_new_projects is True
    assert state.last_transition == "auto_activated"

    telemetry = json.loads(server_agent.telemetry_json)
    telemetry["wireguard"]["connected"] = False
    server_agent.telemetry_json = json.dumps(telemetry)
    state.unhealthy_since = now - timedelta(seconds=hosting_node_health.AUTO_DRAIN_SECONDS + 5)
    state.healthy_since = None
    result = hosting_node_health.reconcile_node_health(db, node, now=now)
    assert result["healthy"] is False
    assert node.status == "draining"
    assert node.accepts_new_projects is False
    assert state.last_transition == "auto_drained"

    telemetry["wireguard"]["connected"] = True
    server_agent.telemetry_json = json.dumps(telemetry)
    state.healthy_since = now - timedelta(seconds=hosting_node_health.AUTO_RECOVER_SECONDS + 5)
    state.unhealthy_since = None
    result = hosting_node_health.reconcile_node_health(db, node, now=now)
    assert result["healthy"] is True
    assert node.status == "active"
    assert node.accepts_new_projects is True
    assert state.last_transition == "auto_recovered"

    db.rollback()


def test_manual_hold_prevents_self_healing_transition(db, platform_owner):
    now, node, server, peer, hosting_agent, server_agent, state = _healthy_node_graph(db, platform_owner)
    state.automation_enabled = False
    state.healthy_since = now - timedelta(hours=1)
    node.status = "draining"
    node.accepts_new_projects = False

    result = hosting_node_health.reconcile_node_health(db, node, now=now)
    assert result["healthy"] is True
    assert node.status == "draining"
    assert node.accepts_new_projects is False
    db.rollback()


def test_self_healing_runtime_contract_exists():
    repo = Path(__file__).resolve().parents[3]
    compose = (repo / "compose.production.yml").read_text(encoding="utf-8")
    frontend = (repo / "apps" / "frontend" / "app" / "hosting-nodes" / "page.tsx").read_text(encoding="utf-8")
    api = (repo / "apps" / "backend" / "app" / "api" / "v1" / "hosting_operations.py").read_text(encoding="utf-8")

    assert "ithute-hosting-health-controller:" in compose
    assert "app.services.hosting_node_health_daemon" in compose
    assert '@router.post("/platform/hosting/nodes/{node_id}/automation")' in api
    assert "Automatic self-healing enabled" in frontend
    assert "Pause automation" in frontend
