from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.models import (
    HostingDeployment,
    HostingFailoverAttempt,
    HostingNode,
    HostingNodeAgent,
    HostingNodeHealthState,
    HostingProject,
    HostingProjectOperation,
)
from app.services import hosting_failover


def _node(db, owner, suffix: str, *, active: bool) -> HostingNode:
    node = HostingNode(
        name=f"failover-{suffix}-{uuid.uuid4().hex[:6]}",
        hostname=f"{suffix}-{uuid.uuid4().hex[:8]}.example.test",
        public_ip=None,
        allocatable_storage_mb=8192,
        allocatable_memory_mb=8192,
        allocatable_cpu_millicores=8000,
        status="active" if active else "draining",
        accepts_new_projects=active,
        created_by_user_id=owner.id,
    )
    db.add(node)
    db.flush()
    return node


def _project(db, tenant, user, source: HostingNode, *, policy: str) -> HostingProject:
    now = datetime.now(timezone.utc)
    project = HostingProject(
        tenant_id=tenant.id,
        node_id=source.id,
        name=f"Failover app {uuid.uuid4().hex[:6]}",
        slug=f"failover-{uuid.uuid4().hex[:10]}",
        runtime="python",
        source_branch="main",
        container_port=8080,
        health_path="/health",
        storage_mb=512,
        memory_mb=256,
        cpu_millicores=250,
        pid_limit=128,
        status="running",
        failover_policy=policy,
        rules_version="2026-09-13",
        rules_accepted_at=now,
        rules_accepted_by_user_id=user.id,
        created_by_user_id=user.id,
    )
    db.add(project)
    db.flush()
    deployment = HostingDeployment(
        tenant_id=tenant.id,
        project_id=project.id,
        node_id=source.id,
        release_number=1,
        image_ref="ghcr.io/ithute-stak/hosted-test@sha256:" + "a" * 64,
        image_digest="sha256:" + "a" * 64,
        source_commit="abcdef1",
        status="healthy",
        requested_by_user_id=user.id,
        completed_at=now,
        last_health_at=now,
        origin_url="http://10.70.0.9:22000",
    )
    db.add(deployment)
    db.flush()
    return project


def _drained_state(db, source: HostingNode) -> HostingNodeHealthState:
    state = HostingNodeHealthState(
        node_id=source.id,
        automation_enabled=True,
        health_status="unhealthy",
        unhealthy_since=datetime.now(timezone.utc) - timedelta(seconds=hosting_failover.FAILOVER_AFTER_SECONDS + 30),
        last_transition="auto_drained",
        last_transition_at=datetime.now(timezone.utc) - timedelta(seconds=hosting_failover.FAILOVER_AFTER_SECONDS + 30),
        last_reason="managed_network_connected",
    )
    db.add(state)
    db.flush()
    return state


def test_stateless_project_stages_replacement_then_cuts_over(db, tenant_admin, platform_owner, monkeypatch):
    user, tenant, _ = tenant_admin
    source = _node(db, platform_owner, "source", active=False)
    target = _node(db, platform_owner, "target", active=True)
    project = _project(db, tenant, user, source, policy="stateless_auto")
    _drained_state(db, source)

    agent = HostingNodeAgent(
        node_id=target.id,
        token_hash=f"target-{uuid.uuid4().hex}",
        token_hint="target-agent",
        agent_version="test",
        last_seen_at=datetime.now(timezone.utc),
        origin_bind_ip="10.70.0.2",
        rotated_at=datetime.now(timezone.utc),
        rotated_by_user_id=platform_owner.id,
    )
    db.add(agent)
    db.flush()

    monkeypatch.setattr(
        hosting_failover,
        "rank_nodes",
        lambda *args, **kwargs: [
            {"node": target, "eligible": True, "score": 1.0, "name": target.name, "reasons": []},
            {"node": source, "eligible": False, "score": 99.0, "name": source.name, "reasons": ["draining"]},
        ],
    )

    result = hosting_failover.run_application_failover_reconcile(db)
    assert result["replacements_queued"] == 1
    attempt = db.scalar(select(HostingFailoverAttempt).where(HostingFailoverAttempt.project_id == project.id))
    assert attempt is not None
    assert attempt.status == "deploying"
    assert attempt.target_node_id == target.id

    replacement = db.get(HostingDeployment, attempt.deployment_id)
    assert replacement is not None
    assert replacement.node_id == target.id
    assert replacement.image_digest == "sha256:" + "a" * 64
    assert replacement.reset_data_volume is True

    replacement.status = "healthy"
    replacement.origin_url = "http://10.70.0.2:22001"
    replacement.completed_at = datetime.now(timezone.utc)
    monkeypatch.setattr(hosting_failover, "reconcile_project_edge", lambda *args, **kwargs: {"status": "active"})

    hosting_failover.run_application_failover_reconcile(db)
    db.refresh(project)
    db.refresh(attempt)
    assert project.node_id == target.id
    assert project.status == "running"
    assert attempt.status == "completed"
    retirement = db.scalar(
        select(HostingProjectOperation).where(
            HostingProjectOperation.project_id == project.id,
            HostingProjectOperation.node_id == source.id,
            HostingProjectOperation.operation == "retire",
        )
    )
    assert retirement is not None
    assert retirement.status == "queued"

    db.execute(delete(HostingFailoverAttempt).where(HostingFailoverAttempt.project_id == project.id))
    db.execute(delete(HostingDeployment).where(HostingDeployment.project_id == project.id))
    db.execute(delete(HostingNodeHealthState).where(HostingNodeHealthState.node_id == source.id))
    db.execute(delete(HostingNodeAgent).where(HostingNodeAgent.node_id == target.id))
    db.execute(delete(HostingProject).where(HostingProject.id == project.id))
    db.execute(delete(HostingNode).where(HostingNode.id.in_([source.id, target.id])))
    db.commit()


def test_stateful_default_never_auto_relocates(db, tenant_admin, platform_owner, monkeypatch):
    user, tenant, _ = tenant_admin
    source = _node(db, platform_owner, "manual-source", active=False)
    project = _project(db, tenant, user, source, policy="manual")
    _drained_state(db, source)

    monkeypatch.setattr(hosting_failover, "rank_nodes", lambda *args, **kwargs: [])
    result = hosting_failover.run_application_failover_reconcile(db)

    attempt = db.scalar(select(HostingFailoverAttempt).where(HostingFailoverAttempt.project_id == project.id))
    assert attempt is not None
    assert attempt.status == "recovery_required"
    assert attempt.deployment_id is None
    assert "local /data" in (attempt.reason or "")
    assert result["recovery_required"] >= 1

    db.execute(delete(HostingFailoverAttempt).where(HostingFailoverAttempt.project_id == project.id))
    db.execute(delete(HostingDeployment).where(HostingDeployment.project_id == project.id))
    db.execute(delete(HostingNodeHealthState).where(HostingNodeHealthState.node_id == source.id))
    db.execute(delete(HostingProject).where(HostingProject.id == project.id))
    db.execute(delete(HostingNode).where(HostingNode.id == source.id))
    db.commit()



def test_failover_runtime_cleanup_contract_exists():
    repo = __import__("pathlib").Path(__file__).resolve().parents[3]
    agent = (repo / "infrastructure" / "hosting-agent" / "agent.py").read_text(encoding="utf-8")
    agent_v3 = (repo / "infrastructure" / "hosting-agent" / "agent_v3.py").read_text(encoding="utf-8")
    operations = (repo / "apps" / "backend" / "app" / "api" / "v1" / "hosting_project_operations.py").read_text(encoding="utf-8")
    frontend = (repo / "apps" / "frontend" / "app" / "hosting" / "page.tsx").read_text(encoding="utf-8")

    assert "reset_data_volume" in agent
    assert 'operation not in {"restart", "logs", "retire"}' in agent_v3
    assert "label=ithute.project=" in agent_v3
    assert 'row.operation == "retire"' in operations
    assert "Enable stateless failover" in frontend
    assert "Move safely" in frontend
