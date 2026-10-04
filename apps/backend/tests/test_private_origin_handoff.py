import os
from pathlib import Path

import pytest

from app.services.hosting_edge_handoff import HostingOriginError, validate_trusted_origin


def test_trusted_hosting_origin_accepts_private_ipv4(monkeypatch):
    monkeypatch.setenv("ITHUTE_HOSTING_ORIGIN_CIDRS", "10.20.0.0/24")
    assert validate_trusted_origin("http://10.20.0.15:22001") == "http://10.20.0.15:22001"


def test_trusted_hosting_origin_rejects_public_or_untrusted(monkeypatch):
    monkeypatch.setenv("ITHUTE_HOSTING_ORIGIN_CIDRS", "10.20.0.0/24")
    with pytest.raises(HostingOriginError):
        validate_trusted_origin("http://8.8.8.8:22001")
    with pytest.raises(HostingOriginError):
        validate_trusted_origin("http://10.21.0.10:22001")
    with pytest.raises(HostingOriginError):
        validate_trusted_origin("https://10.20.0.10:22001")


def test_private_origin_handoff_contract_exists():
    root = Path(__file__).parents[2]
    operations = (root / "app" / "api" / "v1" / "hosting_operations.py").read_text(encoding="utf-8")
    provisioning = (root / "app" / "api" / "v1" / "hosting_provisioning.py").read_text(encoding="utf-8")
    edge = (root / "app" / "api" / "v1" / "edge_routes.py").read_text(encoding="utf-8")
    agent = (root.parents[1] / "infrastructure" / "hosting-agent" / "agent.py").read_text(encoding="utf-8")
    firewall = (root.parents[1] / "infrastructure" / "hosting-node" / "apply-egress-firewall.sh").read_text(encoding="utf-8")
    reconciler = (root / "app" / "services" / "hosting_provisioning_reconcile.py").read_text(encoding="utf-8")

    assert "origin_url" in operations
    assert "validate_trusted_origin(payload.origin_url)" in operations
    assert "reconcile_project_edge" in provisioning
    assert 'origin.name == "ithute-hosting"' in edge
    assert "ITHUTE_HOSTING_ORIGIN_BIND_IP" in agent
    assert "--publish" in agent
    assert "ITHUTE-HOSTING-INGRESS" in firewall
    assert "--ctorigdst" in firewall
    assert "run_hosting_provisioning_reconcile" in reconciler
