from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.services.hosting_placement import _fresh


def test_placement_heartbeat_freshness():
    now = datetime.now(timezone.utc)
    assert _fresh(now - timedelta(seconds=30)) is True
    assert _fresh(now - timedelta(minutes=10)) is False
    assert _fresh(None) is False


def test_automatic_placement_contract_exists():
    root = Path(__file__).parents[2]
    placement = (root / "app" / "services" / "hosting_placement.py").read_text(encoding="utf-8")
    applications = (root / "app" / "api" / "v1" / "application_hosting.py").read_text(encoding="utf-8")
    databases = (root / "app" / "api" / "v1" / "shared_hosting.py").read_text(encoding="utf-8")
    frontend = (root.parent / "frontend" / "app" / "hosting" / "page.tsx").read_text(encoding="utf-8")

    assert "def score_node(" in placement
    assert "def rank_nodes(" in placement
    assert "def select_node(" in placement
    assert "CPU pressure" in placement
    assert "memory pressure" in placement
    assert "disk pressure" in placement
    assert "Docker is unavailable" in placement
    assert "postgresql" in placement
    assert "mysql" in placement
    assert "preferred_region" in placement
    assert "region_penalty" in placement
    assert '"region_match": region_match' in placement
    assert '"infrastructure": {' in placement

    assert '@router.get("/platform/hosting/placement-preview")' in applications
    assert 'placement_mode": "manual_override" if preferred_node_id else "automatic"' in applications
    assert "Only the platform owner can override automatic workload placement" in applications

    assert "project_colocation" in databases
    assert "Only the platform owner can override automatic database placement" in databases
    assert "A project database must remain on the same hosting node as its application" in databases

    assert "Automatic · healthiest available node" in frontend
    assert "Automatic placement considers live CPU, RAM, disk pressure" in frontend
    assert "Preferred region" in frontend
    assert "region preference" in frontend


def test_infrastructure_control_centre_exposes_placement_planner():
    root = Path(__file__).parents[2]
    infrastructure_page = (root.parent / "frontend" / "app" / "infrastructure" / "servers" / "page.tsx").read_text(encoding="utf-8")
    applications = (root / "app" / "api" / "v1" / "application_hosting.py").read_text(encoding="utf-8")

    assert "Smart workload placement" in infrastructure_page
    assert "Placement score" in infrastructure_page
    assert "preferred_region" in infrastructure_page
    assert "placement-preview" in infrastructure_page
    assert "preferred_region: str | None" in applications
    assert "placement_region_match" in applications
