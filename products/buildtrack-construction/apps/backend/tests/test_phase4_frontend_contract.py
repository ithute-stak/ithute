from pathlib import Path


def test_phase4_fleet_workspace_contract() -> None:
    root = Path(__file__).resolve().parents[3]
    page = (root / "apps" / "frontend" / "app" / "fleet" / "page.tsx").read_text(encoding="utf-8")
    control = (root / "apps" / "frontend" / "app" / "fleet" / "control" / "page.tsx").read_text(encoding="utf-8")
    layout = (root / "apps" / "frontend" / "app" / "layout.tsx").read_text(encoding="utf-8")
    router = (root / "apps" / "backend" / "app" / "api" / "v1" / "router.py").read_text(encoding="utf-8")
    fleet_admin = (root / "apps" / "backend" / "app" / "api" / "v1" / "fleet_admin.py").read_text(encoding="utf-8")
    fleet_guard = (root / "apps" / "backend" / "app" / "security" / "fleet_guard.py").read_text(encoding="utf-8")
    migration = (root / "apps" / "backend" / "alembic" / "versions" / "0005_phase4_fleet_plant.py").read_text(encoding="utf-8")

    for label in (
        "Fleet & Plant", "Asset register", "Assignments", "Fuel", "Inspections & defects",
        "Compliance", "Maintenance", "Costs & alerts", "Audit",
    ):
        assert label in page

    for endpoint in (
        "/fleet/bootstrap", "/fleet/assets", "/assignments", "/fuel", "/inspections",
        "/compliance", "/maintenance-plans", "/maintenance-jobs", "/fleet/costs", "/fleet/audit",
    ):
        assert endpoint in page

    assert "Critical defects automatically remove equipment from service" in page
    assert "draft → approved → in progress → completed" in page

    for label in ("Fleet Control", "Asset lifecycle & meters", "Fleet policy", "Inspection approval queue", "Active assignments / handover", "Compliance register", "Maintenance-plan register"):
        assert label in control
    assert "Always enforced" in control
    assert "maintenance maker/checker approval" in control
    assert "Compliance reminder days are set on each licence" in control
    assert "/fleet/policy" in control and "/fleet/assignments/" in control and "/fleet/inspections/" in control

    assert 'href="/fleet"' in layout and 'href="/fleet/control"' in layout
    assert "fleet_admin_router" in router and "fleet_safe_router" in router and "fleet_router" in router
    assert router.index("fleet_admin_router") < router.index("fleet_safe_router") < router.index("router.include_router(fleet_router")

    assert '"require_maintenance_approval": True' in fleet_admin
    assert '"critical_defect_blocks_operation": True' in fleet_admin
    assert "compliance_reminder_days" not in fleet_admin
    assert "An unserviceable asset cannot be placed into active service" in fleet_guard
    assert "Operator/driver must belong to the asset/assignment branch" in fleet_guard

    assert 'down_revision = "0004_phase3_workforce_payroll"' in migration
    for table in ("fleet_assets", "fleet_assignments", "fleet_meter_readings", "fleet_compliance", "fleet_inspections", "fleet_defects", "fleet_fuel_transactions", "fleet_maintenance_plans", "fleet_maintenance_jobs", "fleet_audit_events"):
        assert table in migration
