import uuid

from sqlalchemy import delete

from app.models import BillingPlan, HostingDeployment, HostingNode, HostingProject, SubscriptionStatus, TenantSubscription
from app.services.billing import assign_subscription

PASSWORD = "Phase1-Test-Password!"


def login(client, email):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _plan(code: str) -> BillingPlan:
    return BillingPlan(
        code=code,
        name="Deployment Runtime Test",
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


def test_digest_pinned_deployment_agent_and_rollback(client, db, tenant_admin, platform_owner):
    user, tenant, _ = tenant_admin
    plan = _plan(f"runtime-{uuid.uuid4().hex[:10]}")
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
    agent_token = token_response.json()["token"]
    assert len(agent_token) >= 40
    node = db.get(HostingNode, node_id)
    db.refresh(node)
    assert node.agent_token_hash
    assert node.agent_token_hash != agent_token

    mutable = client.post(
        f"/api/v1/tenants/{tenant.id}/hosting/projects/{project_id}/deployments",
        headers=tenant_headers,
        json={"image_ref": "ghcr.io/ithute-stak/hosted-runtime:latest"},
    )
    assert mutable.status_code == 422

    outside_registry = client.post(
        f"/api/v1/tenants/{tenant.id}/hosting/projects/{project_id}/deployments",
        headers=tenant_headers,
        json={"image_ref": "docker.io/example/runtime@sha256:" + "b" * 64},
    )
    assert outside_registry.status_code == 422

    image_ref = "ghcr.io/ithute-stak/hosted-runtime@sha256:" + "a" * 64
    queued = client.post(
        f"/api/v1/tenants/{tenant.id}/hosting/projects/{project_id}/deployments",
        headers=tenant_headers,
        json={"image_ref": image_ref, "source_sha": "c" * 40},
    )
    assert queued.status_code == 202, queued.text
    deployment_id = uuid.UUID(queued.json()["id"])
    assert queued.json()["status"] == "queued"

    duplicate = client.post(
        f"/api/v1/tenants/{tenant.id}/hosting/projects/{project_id}/deployments",
        headers=tenant_headers,
        json={"image_ref": image_ref},
    )
    assert duplicate.status_code == 409

    bad_claim = client.post(
        f"/api/v1/hosting-agent/nodes/{node_id}/claim",
        headers={"X-Ithute-Agent-Token": "wrong-token"},
        json={"agent_version": "test-agent/1"},
    )
    assert bad_claim.status_code == 401

    agent_headers = {"X-Ithute-Agent-Token": agent_token}
    claimed = client.post(
        f"/api/v1/hosting-agent/nodes/{node_id}/claim",
        headers=agent_headers,
        json={"agent_version": "test-agent/1"},
    )
    assert claimed.status_code == 200, claimed.text
    work = claimed.json()["deployment"]
    assert work["id"] == str(deployment_id)
    assert work["status"] == "claimed"
    assert work["runtime"]["security"]["run_as_root"] is False
    assert work["runtime"]["security"]["public_host_ports"] is False
    assert work["runtime"]["security"]["cap_drop"] == ["ALL"]

    deploying = client.post(
        f"/api/v1/hosting-agent/nodes/{node_id}/deployments/{deployment_id}/report",
        headers=agent_headers,
        json={"status": "deploying", "message": "candidate container started"},
    )
    assert deploying.status_code == 200, deploying.text
    assert deploying.json()["status"] == "deploying"

    healthy = client.post(
        f"/api/v1/hosting-agent/nodes/{node_id}/deployments/{deployment_id}/report",
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
    assert rollback.status_code == 202, rollback.text
    rollback_id = uuid.UUID(rollback.json()["id"])
    assert rollback.json()["rollback_of_deployment_id"] == str(deployment_id)

    rollback_claim = client.post(
        f"/api/v1/hosting-agent/nodes/{node_id}/claim",
        headers=agent_headers,
        json={"agent_version": "test-agent/1"},
    )
    assert rollback_claim.status_code == 200, rollback_claim.text
    assert rollback_claim.json()["deployment"]["id"] == str(rollback_id)

    failed_rollback = client.post(
        f"/api/v1/hosting-agent/nodes/{node_id}/deployments/{rollback_id}/report",
        headers=agent_headers,
        json={"status": "failed", "error": "candidate health check failed"},
    )
    assert failed_rollback.status_code == 200, failed_rollback.text
    assert failed_rollback.json()["status"] == "failed"

    db.refresh(project)
    assert project.image_ref == image_ref
    assert project.status == "running"

    empty = client.post(
        f"/api/v1/hosting-agent/nodes/{node_id}/claim",
        headers=agent_headers,
        json={"agent_version": "test-agent/1"},
    )
    assert empty.status_code == 200, empty.text
    assert empty.json()["deployment"] is None

    db.execute(delete(HostingDeployment).where(HostingDeployment.project_id == project_id))
    db.execute(delete(HostingProject).where(HostingProject.id == project_id))
    db.execute(delete(HostingNode).where(HostingNode.id == node_id))
    db.execute(delete(TenantSubscription).where(TenantSubscription.tenant_id == tenant.id))
    db.execute(delete(BillingPlan).where(BillingPlan.id == plan.id))
    db.commit()
