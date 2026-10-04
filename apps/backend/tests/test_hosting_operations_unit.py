import subprocess
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.v1.hosting_operations import _validate_image_ref, _validate_source_commit


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
    root = Path(__file__).parents[2].parents[0]
    repo = root.parent.parent
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
