from datetime import datetime, timezone
import uuid

from app.models import HostingDatabase, HostingNode, HostingProject
from app.services import maintenance_drain_planner


def _node(db, owner, suffix: str) -> HostingNode:
    node = HostingNode(
        name=f"drain-{suffix}-{uuid.uuid4().hex[:6]}",
        hostname=f"drain-{suffix}-{uuid.uuid4().hex[:6]}.example.test",
        allocatable_storage_mb=10000,
        allocatable_memory_mb=8000,
        allocatable_cpu_millicores=4000,
        status="active",
        accepts_new_projects=True,
        created_by_user_id=owner.id,
    )
    db.add(node)
    db.flush()
    return node


def _project(db, tenant, owner, node, *, policy: str) -> HostingProject:
    now = datetime.now(timezone.utc)
    project = HostingProject(
        tenant_id=tenant.id,
        node_id=node.id,
        name=f"Drain project {uuid.uuid4().hex[:6]}",
        slug=f"drain-{uuid.uuid4().hex[:8]}",
        runtime="docker",
        source_branch="main",
        container_port=8080,
        health_path="/",
        storage_mb=512,
        memory_mb=256,
        cpu_millicores=250,
        pid_limit=128,
        status="running",
        failover_policy=policy,
        rules_version="2026-09-13",
        rules_accepted_at=now,
        rules_accepted_by_user_id=owner.id,
        created_by_user_id=owner.id,
    )
    db.add(project)
    db.flush()
    return project


def test_drain_plan_blocks_stateful_and_database_dependent_workload(db, tenant_admin, platform_owner, monkeypatch):
    user, tenant, _ = tenant_admin
    source = _node(db, platform_owner, "source")
    project = _project(db, tenant, user, source, policy="manual")
    database = HostingDatabase(
        tenant_id=tenant.id,
        project_id=project.id,
        node_id=source.id,
        engine="postgresql",
        database_name=f"db_{uuid.uuid4().hex[:8]}",
        username=f"u_{uuid.uuid4().hex[:8]}",
        encrypted_password="encrypted",
        internal_port=5432,
        storage_mb=1024,
        status="ready",
        operation="idle",
        created_by_user_id=user.id,
    )
    db.add(database)
    db.flush()
    monkeypatch.setattr(maintenance_drain_planner, "rank_nodes", lambda *args, **kwargs: [])

    plan = maintenance_drain_planner.build_maintenance_drain_plan(db, node_id=source.id)

    assert plan["execution_mode"] == "plan_only"
    assert plan["summary"]["maintenance_ready"] is False
    assert plan["summary"]["blocked_workloads"] >= 1
    app = next(item for item in plan["migration_order"] if item["kind"] == "application")
    assert app["movable"] is False
    assert any("stateless_auto" in reason for reason in app["blockers"])
    assert any("safe replica promotion target" in reason for reason in app["blockers"])
    db.rollback()


def test_drain_plan_recommends_target_for_stateless_application(db, tenant_admin, platform_owner, monkeypatch):
    user, tenant, _ = tenant_admin
    source = _node(db, platform_owner, "source-safe")
    target = _node(db, platform_owner, "target-safe")
    project = _project(db, tenant, user, source, policy="stateless_auto")

    monkeypatch.setattr(
        maintenance_drain_planner,
        "rank_nodes",
        lambda *args, **kwargs: [
            {"node": target, "eligible": True, "score": 10.0, "name": target.name},
            {"node": source, "eligible": True, "score": 1.0, "name": source.name},
        ],
    )
    monkeypatch.setattr(
        maintenance_drain_planner,
        "_server_for_node",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        maintenance_drain_planner,
        "rank_failover_candidates",
        lambda *args, **kwargs: [
            {
                "placement": {"node": target, "eligible": True, "score": 10.0, "name": target.name},
                "target_server": None,
                "failure_domain": {"highest_risk": None},
                "route": {"reachable": False, "total_weight": None},
            }
        ],
    )

    plan = maintenance_drain_planner.build_maintenance_drain_plan(db, node_id=source.id)

    assert plan["summary"]["maintenance_ready"] is True
    assert plan["summary"]["movable_workloads"] == 1
    assert plan["summary"]["required_destination_capacity"] == {
        "cpu_millicores": 250,
        "memory_mb": 256,
        "storage_mb": 512,
    }
    app = plan["migration_order"][0]
    assert app["recommended_target_node_id"] == str(target.id)
    assert app["recommended_target_name"] == target.name
    db.rollback()


def test_application_hosting_exposes_drain_plan_contract():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "app/api/v1/application_hosting.py").read_text()
    assert '@router.get("/platform/hosting/nodes/{node_id}/drain-plan")' in source
    assert "build_maintenance_drain_plan" in source
