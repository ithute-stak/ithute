from pathlib import Path


def test_workforce_setup_exposes_remaining_phase3_administration() -> None:
    root = Path(__file__).resolve().parents[2]
    page = (root / "frontend" / "app" / "workforce" / "setup" / "page.tsx").read_text(encoding="utf-8")
    navigation = (root / "frontend" / "app" / "components" / "buildtrack-navigation.tsx").read_text(encoding="utf-8")

    for label in (
        "Leave balance setup",
        "Recurring pay assignment",
        "Shift assignment",
        "Employee account link",
        "Employee lifecycle",
        "Contract signature activation",
        "Employee export",
        "Payroll period close",
    ):
        assert label in page

    for endpoint in (
        "/workforce/leave-balances",
        "/workforce/employee-pay-components",
        "/workforce/shift-assignments",
        "/link-user",
        "/lifecycle",
        "/activate-signed",
        "/workforce/employees/export.csv",
        "/close-reviewed",
    ):
        assert endpoint in page

    assert "employee_signed" in page
    assert "company_signed" in page
    assert "does not send salary payments" in page
    assert "does not invent statutory tax or pension rates" in page
    assert 'href: "/workforce/setup"' in navigation
