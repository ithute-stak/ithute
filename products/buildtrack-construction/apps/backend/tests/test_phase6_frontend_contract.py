from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
BACKEND = ROOT / "backend"


def test_phase6_routes_models_and_migration_are_registered() -> None:
    router = (BACKEND / "app/api/v1/router.py").read_text()
    models = (BACKEND / "app/models/__init__.py").read_text()
    project_model = (BACKEND / "app/models/project.py").read_text()
    api = (BACKEND / "app/api/v1/projects.py").read_text()
    safe = (BACKEND / "app/api/v1/projects_safe.py").read_text()
    reporting = (BACKEND / "app/api/v1/projects_reporting.py").read_text()
    migration = (BACKEND / "alembic/versions/0008_phase6_project_mobilisation.py").read_text()
    assert "project_reporting_router" in router and "project_safe_router" in router and "project_router" in router
    assert router.index("include_router(project_reporting_router") < router.index("include_router(project_safe_router") < router.index("include_router(project_router")
    assert '"phase_6"' in router and "phase7_site_operations_handoff" in router
    assert 'revision = "0008_phase6_projects"' in migration
    assert 'down_revision = "0007_phase5_submission_evidence"' in migration
    for table in (
        "projects", "project_sites", "project_team_members", "project_budget_baselines", "project_budget_lines",
        "project_milestones", "project_mobilisation_items", "project_asset_allocations", "project_risks",
        "project_handover_documents", "project_readiness_snapshots", "project_audit_events",
    ):
        assert f'"{table}"' in migration
    for model in (
        "Project", "ProjectSiteLink", "ProjectTeamMember", "ProjectBudgetBaseline", "ProjectBudgetLine",
        "ProjectMilestone", "ProjectMobilisationItem", "ProjectAssetAllocation", "ProjectRisk",
        "ProjectHandoverDocument", "ProjectReadinessSnapshot", "ProjectAuditEvent",
    ):
        assert model in models and f"class {model}" in project_model
    for contract in (
        '"PROJECT_BUDGET_BASELINE"', '"PROJECT_MOBILISATION"', '"PROJECT_RISK"',
        '"/from-tender/{tender_id}"', '"/budget/submit"', '"/budget/revise"',
        '"/readiness-approval"', '"/site-operations-handoff"', '"/exports/projects.csv"',
    ):
        assert contract in api
    assert "strict_readiness_state" in safe
    assert 'Document.status == "active"' in safe
    assert '"projects.approve"' in safe
    assert 'project.readiness_status = "ready"; project.status = "ready"' in safe
    assert '"/dashboard/alerts"' in reporting and "strict_readiness_state" in reporting


def test_phase6_browser_workspaces_cover_operational_and_control_contracts() -> None:
    page = (FRONTEND / "app/projects/page.tsx").read_text()
    control = (FRONTEND / "app/projects/control/page.tsx").read_text()
    risks = (FRONTEND / "app/projects/risks/page.tsx").read_text()
    layout = (FRONTEND / "app/layout.tsx").read_text()
    for text in (
        "Project Mobilisation", "Award → Project", "Mobilisation", "Budget baseline", "Programme", "Team",
        "Plant allocation", "Handover docs", "Risks", "/projects/from-tender/", "/projects/dashboard/summary",
        "/projects/dashboard/alerts", "/projects/exports/projects.csv", "Submit baseline", "Request readiness approval",
    ):
        assert text in page
    for text in (
        "Project Control", "/projects/policy/current", "/projects/approvals/", "Project administration",
        "Phase 7 Site Operations handoff", "Generate Phase 7 handoff", "/site-operations-handoff",
    ):
        assert text in control
    for text in ("Project Risk Workbench", "/projects/risks/", "Mitigate", "Save risk treatment", "Critical open risks"):
        assert text in risks
    assert 'href="/projects"' in layout and 'href="/projects/control"' in layout and 'href="/projects/risks"' in layout
