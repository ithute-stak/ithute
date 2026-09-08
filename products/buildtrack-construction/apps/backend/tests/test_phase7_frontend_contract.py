from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
BACKEND = ROOT / "backend"


def test_phase7_routes_models_and_migration_are_registered() -> None:
    router = (BACKEND / "app/api/v1/router.py").read_text()
    models = (BACKEND / "app/models/__init__.py").read_text()
    site_models = (BACKEND / "app/models/site_operations.py").read_text()
    api = (BACKEND / "app/api/v1/site_operations.py").read_text()
    safe = (BACKEND / "app/api/v1/site_operations_safe.py").read_text()
    control = (BACKEND / "app/api/v1/site_operations_control.py").read_text()
    handoff = (BACKEND / "app/api/v1/projects_siteops_handoff.py").read_text()
    migration = (BACKEND / "alembic/versions/0009_phase7_site_operations.py").read_text()

    assert "site_operations_control_router" in router
    assert "site_operations_safe_router" in router
    assert "site_operations_router" in router
    assert router.index("include_router(site_operations_control_router") < router.index("include_router(site_operations_safe_router") < router.index("include_router(site_operations_router")
    assert router.index("include_router(project_siteops_handoff_router") < router.index("include_router(project_router")
    assert '"phase_7"' in router and "immutable_approved_daily_report_snapshots" in router

    assert 'revision = "0009_phase7_site_ops"' in migration
    assert 'down_revision = "0008_phase6_projects"' in migration
    for table in (
        "site_operations_activations", "site_daily_reports", "site_labour_entries", "site_plant_usage",
        "site_material_entries", "site_progress_entries", "site_evidence", "site_incidents",
        "site_quality_checks", "site_operations_audit_events",
    ):
        assert f'"{table}"' in migration

    for model in (
        "SiteOperationsActivation", "SiteDailyReport", "SiteLabourEntry", "SitePlantUsage",
        "SiteMaterialEntry", "SiteProgressEntry", "SiteEvidence", "SiteIncident",
        "SiteQualityCheck", "SiteOperationsAuditEvent",
    ):
        assert model in models and f"class {model}" in site_models

    for contract in (
        '"SITE_DAILY_REPORT"', '"SITE_INCIDENT"', '"SITE_QUALITY"',
        '"/activations/{project_id:int}"', '"/reports/{report_id:int}/submit"',
        '"/approvals/{request_id:int}/decision"', '"/exports/daily-reports.csv"',
        "submission_blockers", "approved_snapshot", "report_snapshot",
    ):
        assert contract in api
    assert "employees on leave or inactive cannot be recorded as working" in safe
    assert "Timesheet must belong to the same employee, branch, site and report date" in safe
    assert "Document belongs to another branch" in safe and "Document belongs to another site" in safe
    assert '"require_daily_report_approval": True' in safe
    assert '{"critical", "fatal"}' in safe
    assert 'project.status not in {"ready", "active"}' in handoff
    assert '"/control/queue"' in control


def test_phase7_browser_workspaces_cover_operational_and_control_contracts() -> None:
    page = (FRONTEND / "app/site-operations/page.tsx").read_text()
    control = (FRONTEND / "app/site-operations/control/page.tsx").read_text()
    layout = (FRONTEND / "app/layout.tsx").read_text()
    readme = (ROOT.parent / "README.md").read_text() if (ROOT.parent / "README.md").exists() else (ROOT / "../README.md").resolve().read_text()

    for text in (
        "Site Operations", "Activate site", "Daily diary", "Labour", "Plant", "Materials", "Progress",
        "Evidence", "Incidents", "Quality", "/site-ops/activations/", "/site-ops/reports/",
        "Submit for approval", "Export approved CSV", "Phase 8 will own procurement/stores inventory ledgers",
    ):
        assert text in page
    for text in (
        "Site Operations Control", "/site-ops/control/queue", "/site-ops/approvals/", "Daily report maker/checker queue",
        "Open incidents", "Quality / NCR actions", "Site activation lifecycle", "Site Operations policy",
    ):
        assert text in control
    assert 'href="/site-operations"' in layout and 'href="/site-operations/control"' in layout
    assert "Phase 7 — Site Operations: complete" in readme
