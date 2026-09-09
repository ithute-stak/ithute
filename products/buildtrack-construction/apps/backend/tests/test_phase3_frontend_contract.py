from pathlib import Path


def test_phase3_workforce_ui_exposes_complete_operational_flow() -> None:
    root = Path(__file__).resolve().parents[2]
    page = (root / "frontend" / "app" / "workforce" / "page.tsx").read_text()
    css = (root / "frontend" / "app" / "workforce" / "workforce.module.css").read_text()
    navigation = (root / "frontend" / "app" / "components" / "buildtrack-navigation.tsx").read_text()

    for capability in (
        "Workforce overview",
        "Employees & contracts",
        "Leave",
        "Attendance",
        "Timesheets",
        "Payroll preparation",
        "Configuration",
        "Audit",
        "Initialise Phase 3",
        "Add employee",
        "Add draft contract",
        "Request leave",
        "Capture attendance",
        "New timesheet entry",
        "Calculate / recalculate",
        "Review",
        "Approve",
        "Download CSV",
        "BuildTrack does not invent Lesotho statutory payroll rates",
    ):
        assert capability in page

    assert 'href="/workforce"' in navigation
    assert "Workforce & Payroll" in navigation
    assert "@media(max-width:720px)" in css


def test_phase3_backend_contract_mentions_scope_and_control_boundaries() -> None:
    root = Path(__file__).resolve().parents[2]
    api = (root / "backend" / "app" / "api" / "v1" / "workforce.py").read_text()
    migration = (root / "backend" / "alembic" / "versions" / "0004_phase3_workforce_payroll.py").read_text()

    for contract in (
        'require_scope(principal, "people.manage"',
        'require_scope(principal, "payroll.manage"',
        'require_scope(principal, "payroll.approve"',
        '"people.sensitive"',
        '"timesheets.approve"',
        '"payroll.export"',
        '"workforce_policy"',
        '"Overtime multiplier is using safe default 1.0',
        '"Approved unpaid leave overlaps this period',
        'run.status not in {"draft", "calculated"}',
        'run.status != "reviewed"',
    ):
        assert contract in api

    assert 'revision = "0004_phase3_workforce_payroll"' in migration
    assert 'down_revision = "0003_phase2_access_security"' in migration
