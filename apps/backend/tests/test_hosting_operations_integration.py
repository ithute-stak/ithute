import uuid
from datetime import datetime, timezone

from sqlalchemy import delete

from app.core.security import hash_token
from app.models import (
    BillingPlan,
    HostingDeployment,
    HostingEnvironmentVariable,
    HostingNode,
    HostingNodeAgent,
    HostingProject,
    SubscriptionStatus,
    TenantSubscription,
)
from app.services.billing import assign_subscription

PASSWORD = "Phase1-Test-Password!"


def login(client, email):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _plan(code: str) -> BillingPlan:
    return BillingPlan(
        code=code,
        name="Hosting Operations Integration",
        currency="LSL",
        monthly_price_minor=14900,
        included_mailboxes=0,
        included_domains=1,
        included_storage_mb=0,
        max_api_keys=1,
        included_hosted_projects=1,
        hosting_storage_mb=2048,
        hosting_memory_mb_per_project=1024,
        hosting_cpu_millicores_per_project=1000,
        hosting_pids_per_project=256,
        is_active=True,
    )


def test_release_environment_agent_and_safe_rollback(client, db, tenant_admin, platform_owner):
    user, tenant, _ = tenant_admin
    plan = _plan(f"hosting-ops-{uuid.uuid4().hex[:10]}")
    db.add(plan)
    db.commit()
    db.refresh(plan)
    assign_subscription(db, tenant.id, plan, SubscriptionStatus.active)

    owner_headers = login(client, platform_owner.email)
    node_response = client.post(
        "/api/v1/platform/hosting/nodes",
        headers=owner_headers,
        json={
            "name": f"runtime-{uuid.uuid4().hex[:8]}",
            "hostname": "runtime-node.example.com",
            "allocatable_storage_mb": 4096,
            "allocatable_memory_mb": 2048,
            "allocatable_cpu_millicores": 2000,
        },
    )
    assert node_response.status_code == 201, node_response.text
    node_id = uuid.UUID(node_response.json()["id"])

    tenant_headers = login(client, user.email)
    project_response = client.post(
        f"/api/v1/tenants/{tenant.id}/hosting/projects",
        headers=tenant_headers,
        json={
            "name": "Runtime App",
            "runtime": "python",
            "source_repository": "https://github.com/example/runtime-app",
            "source_branch": "main",
            "storage_mb": 1024,
            "memory_mb": 512,
            "cpu_millicores": 500,
            "pid_limit": 128,
            "container_port": 8080,
            "health_path": "/health",
            "accept_hosting_rules": True,
        },
    )
    assert project_response.status_code == 201, project_response.text
    project_id = uuid.UUID(project_response.json()["id"])

    token_response = client.post(f"/api/v1/platform/hosting/nodes/{node_id}/agent-token", headers=owner_headers)
    assert token_response.status_code == 200, token_response.text
    token = token_response.json()["token"]
    assert token.startswith("ith_host_")

    agent = db.get(HostingNodeAgent, node_id)
    db.refresh(agent)
    assert agent.token_hash
    assert agent.token_hash != token
    assert agent.token_hint and token.startswith(agent.token_hint)

    env_response = client.put(
        f"/api/v1/tenants/{tenant.id}/hosting/projects/{project_id}/environment/DATABASE_URL",
        headers=tenant_headers,
        json={"value": "postgresql://runtime-secret", "is_secret": True},
    )
    assert env_response.status_code == 200, env_response.text

    env_list = client.get(
        f"/api/v1/tenants/{tenant.id}/hosting/projects/{project_id}/environment",
        headers=tenant_headers,
    )
    assert env_list.status_code == 200, env_list.text
    assert env_list.json()["items"] == [
        {
            "key": "DATABASE_URL",
            "is_secret": True,
            "has_value": True,
            "updated_at": env_list.json()["items"][0]["updated_at"],
        }
    ]
    assert "postgresql://runtime-secret" not in env_list.text

    mutable = client.post(
        f"/api/v1/tenants/{tenant.id}/hosting/projects/{project_id}/deployments",
        headers=tenant_headers,
        json={"image_ref": "ghcr.io/ithute-stak/hosted-runtime:latest"},
    )
    assert mutable.status_code == 422

    foreign = client.post(
        f"/api/v1/tenants/{tenant.id}/hosting/projects/{project_id}/deployments",
        headers=tenant_headers,
        json={"image_ref": "ghcr.io/example/runtime@sha256:" + "b" * 64},
    )
    assert foreign.status_code == 422

    image_ref = "ghcr.io/ithute-stak/hosted-runtime@sha256:" + "a" * 64
    queued = client.post(
        f"/api/v1/tenants/{tenant.id}/hosting/projects/{project_id}/deployments",
        headers=tenant_headers,
        json={"image_ref": image_ref, "source_commit": "c" * 40},
    )
    assert queued.status_code == 201, queued.text
    deployment_id = uuid.UUID(queued.json()["id"])
    assert queued.json()["release_number"] == 1
    assert queued.json()["status"] == "queued"

    bad_heartbeat = client.post(
        "/api/v1/hosting/agent/heartbeat",
        headers={"X-Ithute-Hosting-Agent": "ith_host_wrong"},
        json={"version": "test-agent/1"},
    )
    assert bad_heartbeat.status_code == 401

    agent_headers = {"X-Ithute-Hosting-Agent": token}
    heartbeat = client.post(
        "/api/v1/hosting/agent/heartbeat",
        headers=agent_headers,
        json={"version": "test-agent/1"},
    )
    assert heartbeat.status_code == 200, heartbeat.text
    assert heartbeat.json()["node_id"] == str(node_id)

    claimed = client.post("/api/v1/hosting/agent/deployments/claim", headers=agent_headers)
    assert claimed.status_code == 200, claimed.text
    work = claimed.json()["deployment"]
    assert work["id"] == str(deployment_id)
    assert work["image_ref"] == image_ref
    assert work["image_digest"] == "sha256:" + "a" * 64
    assert work["project"]["environment"]["DATABASE_URL"] == "postgresql://runtime-secret"
    assert work["project"]["security"]["privileged"] is False
    assert work["project"]["security"]["docker_socket"] is False
    assert work["project"]["security"]["host_ports"] == []
    assert work["project"]["security"]["cap_drop"] == ["ALL"]
    assert work["project"]["security"]["no_new_privileges"] is True
    assert work["project"]["security"]["read_only_root"] is True

    duplicate_claim = client.post("/api/v1/hosting/agent/deployments/claim", headers=agent_headers)
    assert duplicate_claim.status_code == 200, duplicate_claim.text
    assert duplicate_claim.json()["deployment"] is None

    running = client.post(
        f"/api/v1/hosting/agent/deployments/{deployment_id}/status",
        headers=agent_headers,
        json={"status": "running", "message": "candidate started"},
    )
    assert running.status_code == 200, running.text
    assert running.json()["status"] == "running"

    healthy = client.post(
        f"/api/v1/hosting/agent/deployments/{deployment_id}/status",
        headers=agent_headers,
        json={"status": "healthy", "message": "health check passed"},
    )
    assert healthy.status_code == 200, healthy.text
    assert healthy.json()["status"] == "healthy"

    project = db.get(HostingProject, project_id)
    db.refresh(project)
    assert project.image_ref == image_ref
    assert project.status == "running"

    history = client.get(
        f"/api/v1/tenants/{tenant.id}/hosting/projects/{project_id}/deployments",
        headers=tenant_headers,
    )
    assert history.status_code == 200, history.text
    assert history.json()["items"][0]["id"] == str(deployment_id)

    rollback = client.post(
        f"/api/v1/tenants/{tenant.id}/hosting/projects/{project_id}/deployments/{deployment_id}/rollback",
        headers=tenant_headers,
    )
    assert rollback.status_code == 201, rollback.text
    rollback_id = uuid.UUID(rollback.json()["id"])
    assert rollback.json()["release_number"] == 2
    assert rollback.json()["previous_deployment_id"] == str(deployment_id)

    rollback_claim = client.post("/api/v1/hosting/agent/deployments/claim", headers=agent_headers)
    assert rollback_claim.status_code == 200, rollback_claim.text
    assert rollback_claim.json()["deployment"]["id"] == str(rollback_id)

    failed_rollback = client.post(
        f"/api/v1/hosting/agent/deployments/{rollback_id}/status",
        headers=agent_headers,
        json={"status": "failed", "message": "candidate health check failed"},
    )
    assert failed_rollback.status_code == 200, failed_rollback.text
    assert failed_rollback.json()["status"] == "failed"

    db.refresh(project)
    assert project.image_ref == image_ref
    assert project.status == "running"

    db.execute(delete(HostingDeployment).where(HostingDeployment.project_id == project_id))
    db.execute(delete(HostingEnvironmentVariable).where(HostingEnvironmentVariable.project_id == project_id))
    db.execute(delete(HostingProject).where(HostingProject.id == project_id))
    db.execute(delete(HostingNodeAgent).where(HostingNodeAgent.node_id == node_id))
    db.execute(delete(HostingNode).where(HostingNode.id == node_id))
    db.execute(delete(TenantSubscription).where(TenantSubscription.tenant_id == tenant.id))
    db.execute(delete(BillingPlan).where(BillingPlan.id == plan.id))
    db.commit()


def test_suspended_project_rejects_late_promotion(client, db, tenant_admin, platform_owner):
    user, tenant, _ = tenant_admin
    now = datetime.now(timezone.utc)
    token = "ith_host_" + uuid.uuid4().hex

    node = HostingNode(
        name=f"suspend-node-{uuid.uuid4().hex[:8]}",
        hostname=f"suspend-{uuid.uuid4().hex[:8]}.example.com",
        allocatable_storage_mb=4096,
        allocatable_memory_mb=2048,
        allocatable_cpu_millicores=2000,
        created_by_user_id=platform_owner.id,
    )
    db.add(node)
    db.flush()

    project = HostingProject(
        tenant_id=tenant.id,
        node_id=node.id,
        name="Suspended Runtime",
        slug=f"suspended-{uuid.uuid4().hex[:10]}",
        runtime="python",
        source_branch="main",
        container_port=8080,
        health_path="/health",
        storage_mb=1024,
        memory_mb=512,
        cpu_millicores=500,
        pid_limit=128,
        status="suspended",
        rules_accepted_at=now,
        rules_accepted_by_user_id=user.id,
        created_by_user_id=user.id,
    )
    db.add(project)
    db.flush()

    db.add(
        HostingNodeAgent(
            node_id=node.id,
            token_hash=hash_token(token),
            token_hint=token[:18],
            rotated_at=now,
            rotated_by_user_id=platform_owner.id,
        )
    )
    image_ref = "ghcr.io/ithute-stak/hosted-suspended@sha256:" + "d" * 64
    deployment = HostingDeployment(
        tenant_id=tenant.id,
        project_id=project.id,
        node_id=node.id,
        release_number=1,
        image_ref=image_ref,
        image_digest="sha256:" + "d" * 64,
        status="running",
        requested_by_user_id=user.id,
        claimed_at=now,
        started_at=now,
    )
    db.add(deployment)
    db.commit()
    db.refresh(deployment)

    agent_headers = {"X-Ithute-Hosting-Agent": token}
    late_healthy = client.post(
        f"/api/v1/hosting/agent/deployments/{deployment.id}/status",
        headers=agent_headers,
        json={"status": "healthy", "message": "late health response"},
    )
    assert late_healthy.status_code == 409, late_healthy.text

    db.refresh(project)
    db.refresh(deployment)
    assert project.status == "suspended"
    assert project.image_ref is None
    assert deployment.status == "failed"
    assert deployment.failure_message == "Project was suspended before deployment completed"

    restored_failure = client.post(
        f"/api/v1/hosting/agent/deployments/{deployment.id}/status",
        headers=agent_headers,
        json={"status": "failed", "message": "previous runtime restored"},
    )
    assert restored_failure.status_code == 200, restored_failure.text
    db.refresh(project)
    assert project.status == "suspended"

    db.execute(delete(HostingDeployment).where(HostingDeployment.project_id == project.id))
    db.execute(delete(HostingProject).where(HostingProject.id == project.id))
    db.execute(delete(HostingNodeAgent).where(HostingNodeAgent.node_id == node.id))
    db.execute(delete(HostingNode).where(HostingNode.id == node.id))
    db.commit()
