from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete

from app.models import HostingNode, HostingProject, InfrastructureCommercialProfile, InfrastructureServer, TenantInfrastructureAllocation
from app.services.hosting_placement import _estimated_incremental_cost, _fresh, score_node, sync_tenant_infrastructure_allocation
from app.services.resource_manager import reserve_capacity


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



def test_incremental_cost_uses_weighted_reserved_capacity():
    profile = InfrastructureCommercialProfile(
        server_id=None,
        currency="LSL",
        provider_cost_minor=10_000,
        backup_cost_minor=0,
        bandwidth_cost_minor=0,
        other_cost_minor=0,
        total_cpu_millicores=4_000,
        total_memory_mb=8_000,
        total_storage_mb=100_000,
        included_bandwidth_gb=0,
        target_margin_bps=3000,
        created_by_user_id=None,
        updated_by_user_id=None,
    )
    # 25% CPU * 40% + 25% RAM * 30% + 20% storage * 30% = 23.5% of cost.
    assert _estimated_incremental_cost(
        profile,
        storage_mb=20_000,
        memory_mb=2_000,
        cpu_millicores=1_000,
    ) == 2_350


def test_placement_sync_creates_commercial_allocation_from_actual_project(db, tenant_admin):
    user, tenant, _membership = tenant_admin
    node = HostingNode(
        name=f"placement-{tenant.id.hex[:8]}",
        hostname=f"placement-{tenant.id.hex[:8]}.example.test",
        allocatable_storage_mb=100_000,
        allocatable_memory_mb=8_192,
        allocatable_cpu_millicores=4_000,
        status="active",
        accepts_new_projects=True,
        created_by_user_id=user.id,
    )
    db.add(node)
    db.flush()
    server = InfrastructureServer(
        name=f"Placement server {tenant.id.hex[:6]}",
        hostname=f"placement-server-{tenant.id.hex[:8]}.example.test",
        region="lesotho",
        provider="test",
        roles_json='["application","database"]',
        status="active",
        hosting_node_id=node.id,
        created_by_user_id=user.id,
    )
    db.add(server)
    db.flush()
    db.add(InfrastructureCommercialProfile(
        server_id=server.id,
        currency="LSL",
        provider_cost_minor=10_000,
        backup_cost_minor=0,
        bandwidth_cost_minor=0,
        other_cost_minor=0,
        total_cpu_millicores=4_000,
        total_memory_mb=8_000,
        total_storage_mb=100_000,
        included_bandwidth_gb=1_000,
        target_margin_bps=3000,
        created_by_user_id=user.id,
        updated_by_user_id=user.id,
    ))
    project = HostingProject(
        tenant_id=tenant.id,
        node_id=node.id,
        name="Placed app",
        slug=f"placed-{tenant.id.hex[:8]}",
        runtime="python",
        source_branch="main",
        container_port=8080,
        health_path="/",
        storage_mb=20_000,
        memory_mb=2_000,
        cpu_millicores=1_000,
        pid_limit=128,
        status="configured",
        rules_accepted_at=datetime.now(timezone.utc),
        rules_accepted_by_user_id=user.id,
        created_by_user_id=user.id,
    )
    db.add(project)
    db.flush()

    try:
        row = sync_tenant_infrastructure_allocation(
            db,
            tenant_id=tenant.id,
            server_id=server.id,
            actor_user_id=user.id,
        )
        assert row is not None
        assert row.source == "placement"
        assert row.cpu_millicores == 1_000
        assert row.memory_mb == 2_000
        assert row.storage_mb == 20_000
        assert row.allocation_weight == 2350
        assert row.active is True
    finally:
        db.rollback()
        db.execute(delete(TenantInfrastructureAllocation).where(TenantInfrastructureAllocation.tenant_id == tenant.id))
        db.execute(delete(HostingProject).where(HostingProject.tenant_id == tenant.id))
        db.execute(delete(InfrastructureCommercialProfile).where(InfrastructureCommercialProfile.server_id == server.id))
        db.execute(delete(InfrastructureServer).where(InfrastructureServer.id == server.id))
        db.execute(delete(HostingNode).where(HostingNode.id == node.id))
        db.commit()


def test_placement_contract_includes_security_and_commercial_scoring():
    root = Path(__file__).parents[2]
    placement = (root / "app" / "services" / "hosting_placement.py").read_text(encoding="utf-8")
    provisioning = (root / "app" / "api" / "v1" / "hosting_provisioning.py").read_text(encoding="utf-8")
    planner = (root.parent / "frontend" / "app" / "infrastructure" / "servers" / "page.tsx").read_text(encoding="utf-8")

    assert "InfrastructureSecuritySnapshot" in placement
    assert "estimated_incremental_cost_minor" in placement
    assert "target_margin_bps" in placement
    assert "security posture is" in placement
    assert "sync_tenant_infrastructure_allocation" in placement
    assert "tenant_id=tenant_id" in placement
    assert "application_placement = None" in provisioning
    assert "Project has not been assigned to a hosting node" not in provisioning
    assert "security posture, infrastructure economics" in planner
    assert "Cost est." in planner



def test_placement_respects_active_resource_reservations(db, platform_owner):
    node = HostingNode(
        name=f"reserved-placement-{platform_owner.id}",
        hostname=f"reserved-placement-{platform_owner.id}.test",
        allocatable_storage_mb=10_000,
        allocatable_memory_mb=8_000,
        allocatable_cpu_millicores=4_000,
        status="active",
        accepts_new_projects=True,
        created_by_user_id=platform_owner.id,
    )
    db.add(node)
    db.flush()

    reserve_capacity(
        db,
        node_id=node.id,
        cpu_millicores=3_500,
        memory_mb=7_500,
        storage_mb=9_500,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        created_by_user_id=platform_owner.id,
        purpose="placement-race-test",
    )

    scored = score_node(
        db,
        node,
        workload="application",
        storage_mb=600,
        memory_mb=600,
        cpu_millicores=600,
    )

    assert scored["eligible"] is False
    assert "insufficient storage" in scored["reasons"]
    assert "insufficient memory" in scored["reasons"]
    assert "insufficient CPU" in scored["reasons"]
    assert scored["allocated"]["reserved"] == {
        "cpu_millicores": 3_500,
        "memory_mb": 7_500,
        "storage_mb": 9_500,
    }
    db.rollback()
