from pathlib import Path


def test_hosting_provisioning_contract_exists():
    root = Path(__file__).parents[2]
    api = (root / "app" / "api" / "v1" / "hosting_provisioning.py").read_text(encoding="utf-8")
    model = (root / "app" / "models" / "hosting_operations.py").read_text(encoding="utf-8")
    shared = (root / "app" / "api" / "v1" / "shared_hosting.py").read_text(encoding="utf-8")
    frontend = (root.parent / "frontend" / "app" / "hosting" / "page.tsx").read_text(encoding="utf-8")

    assert "class HostingProvisioningWorkflow" in model
    assert '@router.post("/tenants/{tenant_id}/hosting/projects/{project_id}/provision"' in api
    assert '@router.get("/tenants/{tenant_id}/hosting/projects/{project_id}/provisioning")' in api
    assert "HostingBuild(" in api
    assert "HostingDatabase(" in api
    assert "HostingEnvironmentVariable" in api
    assert "EdgeApplication(" in api
    assert '"DATABASE_PASSWORD"' in api
    assert '"DATABASE_PORT"' in api
    assert "DATABASE_URL" in shared
    assert "Provision automatically" in frontend
    assert "Application + PostgreSQL" in frontend
    assert "Application + MySQL" in frontend


def test_provisioning_does_not_fake_edge_success():
    root = Path(__file__).parents[2]
    api = (root / "app" / "api" / "v1" / "hosting_provisioning.py").read_text(encoding="utf-8")

    assert "pending_origin" in api
    assert "route.status == \"active\"" in api
    assert "edge_pending" in api


def test_suspended_database_does_not_count_as_provisioning_ready():
    root = Path(__file__).parents[2]
    api = (root / "app" / "api" / "v1" / "hosting_provisioning.py").read_text(encoding="utf-8")

    assert 'database.status == "ready"' in api
    assert 'database_suspended = database is not None and database.status == "suspended"' in api
    assert 'status = "database_suspended"' in api
    assert 'database.status in {"ready", "suspended"}' not in api
