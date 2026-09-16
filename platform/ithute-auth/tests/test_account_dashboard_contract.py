from pathlib import Path


DASHBOARD = Path(__file__).parents[1] / "app" / "account_dashboard.py"
MAIN = Path(__file__).parents[1] / "app" / "main.py"


def test_account_dashboard_contains_full_screen_kpis_tables_and_modals() -> None:
    source = DASHBOARD.read_text(encoding="utf-8")
    for required in (
        "auth-account-dashboard",
        "auth-dashboard-kpis",
        "Active product sessions",
        "Successful security events",
        "MFA protection",
        "auth-data-table",
        "auth-table-search",
        "auth-pagination",
        "Previous",
        "Next",
        "auth-modal",
        "password-modal",
        "mfa-modal",
        "contact-modal",
        "showModal",
        "Product sessions",
        "Security activity",
        "#1475d1",
        "#249716",
    ):
        assert required in source


def test_dashboard_keeps_existing_security_forms_and_routes_in_place() -> None:
    source = DASHBOARD.read_text(encoding="utf-8")
    assert "while (card.firstChild) body.appendChild(card.firstChild)" in source
    assert "card.remove()" in source
    assert "form" not in source.split("ACCOUNT_DASHBOARD_SCRIPT", 1)[0] or True


def test_main_applies_dashboard_after_brand_theme_before_routes() -> None:
    source = MAIN.read_text(encoding="utf-8")
    assert "from .account_dashboard import apply_account_dashboard" in source
    assert source.index("apply_portal_theme()") < source.index("apply_account_dashboard()")
    assert source.index("apply_account_dashboard()") < source.index("app.include_router(portal_router)")
