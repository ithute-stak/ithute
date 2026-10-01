import uuid

from sqlalchemy import delete, select

from app.models import BillingPlan, HostingNode, HostingProject, SubscriptionStatus, TenantSubscription
from app.services.billing import assign_subscription

PASSWORD = "Phase1-Test-Password!"


def login(client, email):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def hosting_plan(code: str) -> BillingPlan:
    return BillingPlan(
        code=code,
        name="Application Hosting Test",
        currency="LSL",
        monthly_price_minor=9900,
        included_mailboxes=0,
        included_domains=1,
        included_storage_mb=0,
        max_api_keys=1,
        included_hosted_projects=1,
        hosting_storage_mb=1024,
        hosting_memory_mb_per_project=512,
        hosting_cpu_millicores_per_project=500,
        hosting_pids_per_project=128,
        is_active=True,
    )


def test_public_hosting_rules_and_pricing_contract(client):
    rules = client.get("/api/v1/hosting/rules")
    assert rules.status_code == 200
    body = rules.json()
    assert body["version"] == "2026-09-13"
    assert "node" in body["allowed_runtimes"]
    assert any("root" in item.lower() for item in body["rules"])
    assert any("resource" in item.lower() for item in body["rules"])

    pricing = client.get("/api/v1/public/hosting-pricing")
    assert pricing.status_code == 200
    assert "items" in pricing.json()


def test_system_owner_creates_full_hosting_package(client, platform_owner, db):
    headers = login(client, platform_owner.email)
    code = f"host-{uuid.uuid4().hex[:10]}"
    payload = {
        "code": code,
        "name": "Five GB Hosting",
        "currency": "LSL",
        "monthly_price_minor": 19900,
        "included_mailboxes": 0,
        "included_domains": 2,
        "included_storage_mb": 0,
        "max_api_keys": 2,
        "included_hosted_projects": 3,
        "hosting_storage_mb": 5120,
        "hosting_memory_mb_per_project": 1024,
        "hosting_cpu_millicores_per_project": 1000,
        "hosting_pids_per_project": 256,
        "hosting_database_limit": 2,
        "hosting_database_storage_mb": 2048,
        "hosting_source_storage_mb": 2048,
        "is_active": True,
    }
    response = client.post("/api/v1/platform/billing/plans", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["hosting_storage_mb"] == 5120
    assert created["included_hosted_projects"] == 3
    assert created["included_mailboxes"] == 0

    # Large aggregate organisation quotas are valid commercial products. Actual
    # workloads are still constrained by per-project limits and hosting-node
    # allocatable capacity when projects are provisioned.
    large_payload = {
        **payload,
        "code": f"large-{uuid.uuid4().hex[:8]}",
        "name": "Enterprise Capacity",
        "hosting_storage_mb": 153600,
        "hosting_database_storage_mb": 153600,
        "hosting_source_storage_mb": 153600,
    }
    large = client.post("/api/v1/platform/billing/plans", headers=headers, json=large_payload)
    assert large.status_code == 201, large.text
    assert large.json()["hosting_storage_mb"] == 153600

    impossible = {
        **payload,
        "code": f"invalid-{uuid.uuid4().hex[:8]}",
        "hosting_storage_mb": 2_000_001,
    }
    rejected = client.post("/api/v1/platform/billing/plans", headers=headers, json=impossible)
    assert rejected.status_code == 422

    plan_ids = [uuid.UUID(created["id"]), uuid.UUID(large.json()["id"])]
    db.execute(delete(BillingPlan).where(BillingPlan.id.in_(plan_ids)))
    db.commit()


def test_hosted_project_requires_rules_and_both_capacity_gates(client, db, tenant_admin, platform_owner):
    user, tenant, _ = tenant_admin
    code = f"allocation-{uuid.uuid4().hex[:10]}"
    plan = hosting_plan(code)
    db.add(plan)
    db.commit()
    db.refresh(plan)
    assign_subscription(db, tenant.id, plan, SubscriptionStatus.active)

    owner_headers = login(client, platform_owner.email)
    node_response = client.post(
        "/api/v1/platform/hosting/nodes",
        headers=owner_headers,
        json={
            "name": f"node-{uuid.uuid4().hex[:8]}",
            "hostname": "hosting-node.example.com",
            "public_ip": "192.0.2.20",
            "allocatable_storage_mb": 2048,
            "allocatable_memory_mb": 1024,
            "allocatable_cpu_millicores": 1000,
            "accepts_new_projects": True,
        },
    )
    assert node_response.status_code == 201, node_response.text
    node_id = uuid.UUID(node_response.json()["id"])

    headers = login(client, user.email)
    payload = {
        "name": "Tenant Website",
        "runtime": "node",
        "source_repository": "https://github.com/example/site",
        "source_branch": "main",
        "container_port": 3000,
        "health_path": "/health",
        "storage_mb": 1024,
        "memory_mb": 512,
        "cpu_millicores": 500,
        "pid_limit": 128,
        "accept_hosting_rules": False,
    }
    rules_rejected = client.post(f"/api/v1/tenants/{tenant.id}/hosting/projects", headers=headers, json=payload)
    assert rules_rejected.status_code == 422

    created = client.post(
        f"/api/v1/tenants/{tenant.id}/hosting/projects",
        headers=headers,
        json={**payload, "accept_hosting_rules": True},
    )
    assert created.status_code == 201, created.text
    project = created.json()
    assert project["node_id"] == str(node_id)
    assert project["rules_version"] == "2026-09-13"
    assert project["isolation"]["root_access"] is False
    assert project["isolation"]["docker_socket"] is False

    # Package allows only one project, even though the node still has capacity.
    second = client.post(
        f"/api/v1/tenants/{tenant.id}/hosting/projects",
        headers=headers,
        json={**payload, "name": "Second Website", "slug": "second-website", "storage_mb": 128, "accept_hosting_rules": True},
    )
    assert second.status_code == 402

    db.execute(delete(HostingProject).where(HostingProject.tenant_id == tenant.id))
    db.execute(delete(HostingNode).where(HostingNode.id == node_id))
    db.execute(delete(TenantSubscription).where(TenantSubscription.tenant_id == tenant.id))
    db.execute(delete(BillingPlan).where(BillingPlan.id == plan.id))
    db.commit()


def test_node_capacity_cannot_be_reduced_below_allocations(client, db, tenant_admin, platform_owner):
    user, tenant, _ = tenant_admin
    plan = hosting_plan(f"node-limit-{uuid.uuid4().hex[:10]}")
    db.add(plan)
    db.commit()
    db.refresh(plan)
    assign_subscription(db, tenant.id, plan, SubscriptionStatus.active)

    owner_headers = login(client, platform_owner.email)
    node = client.post(
        "/api/v1/platform/hosting/nodes",
        headers=owner_headers,
        json={
            "name": f"capacity-{uuid.uuid4().hex[:8]}",
            "hostname": "capacity.example.com",
            "allocatable_storage_mb": 2048,
            "allocatable_memory_mb": 1024,
            "allocatable_cpu_millicores": 1000,
        },
    )
    assert node.status_code == 201, node.text
    node_id = uuid.UUID(node.json()["id"])

    headers = login(client, user.email)
    project = client.post(
        f"/api/v1/tenants/{tenant.id}/hosting/projects",
        headers=headers,
        json={
            "name": "Reserved App",
            "runtime": "python",
            "storage_mb": 1024,
            "memory_mb": 512,
            "cpu_millicores": 500,
            "pid_limit": 128,
            "accept_hosting_rules": True,
        },
    )
    assert project.status_code == 201, project.text

    reduced = client.patch(
        f"/api/v1/platform/hosting/nodes/{node_id}",
        headers=owner_headers,
        json={"allocatable_memory_mb": 256},
    )
    assert reduced.status_code in {409, 422}

    db.execute(delete(HostingProject).where(HostingProject.tenant_id == tenant.id))
    db.execute(delete(HostingNode).where(HostingNode.id == node_id))
    db.execute(delete(TenantSubscription).where(TenantSubscription.tenant_id == tenant.id))
    db.execute(delete(BillingPlan).where(BillingPlan.id == plan.id))
    db.commit()
