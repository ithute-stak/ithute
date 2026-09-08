from pathlib import Path


def test_phase1_workspace_exposes_complete_control_plane() -> None:
    root = Path(__file__).resolve().parents[2]
    page = (root / "frontend" / "app" / "page.tsx").read_text(encoding="utf-8")
    css = (root / "frontend" / "app" / "globals.css").read_text(encoding="utf-8")

    for label in (
        "Company profile",
        "Branches",
        "Sites",
        "Departments",
        "Cost centres",
        "Roles & permissions",
        "Approvals",
        "Document control",
        "Master data",
        "Settings & numbering",
        "Audit trail",
    ):
        assert label in page

    for endpoint in (
        "/foundation/bootstrap",
        "/foundation/summary",
        "/foundation/branches",
        "/foundation/sites",
        "/foundation/departments",
        "/foundation/cost-centres",
        "/foundation/roles",
        "/foundation/approval-workflows",
        "/foundation/approval-requests",
        "/foundation/documents",
        "/foundation/master-data/categories",
        "/foundation/settings",
        "/foundation/number-sequences",
        "/foundation/audit",
    ):
        assert endpoint in page

    assert "Lesotho · Maloti (M)" in page
    assert "Phase 1 operational" in page
    assert "@media (max-width: 880px)" in css
    assert "@media (max-width: 560px)" in css
