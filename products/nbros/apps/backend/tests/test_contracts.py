from app.file_compat import router as file_compat_router
from app.fleet_advisor import _deterministic_actions
from app.main import app


def test_operational_routes_are_registered():
    paths = set(app.openapi()["paths"])
    for path in {
        "/api/v1/fleet/advisor",
        "/api/v1/fleet/reports/summary",
        "/api/v1/fleet/inventory",
        "/api/v1/fleet/dashboard",
        "/api/v1/operations/summary",
        "/api/v1/operations/workshop",
        "/api/v1/operations/procurement",
        "/api/v1/operations/dispatch",
        "/api/v1/operations/tyres",
        "/api/v1/operations/insurance/claims",
        "/api/v1/operations/telematics/events",
        "/api/v1/operations/finance/tco",
        "/api/v1/operations/executive",
    }:
        assert path in paths
    legacy_paths = {getattr(route, "path", "") for route in file_compat_router.routes}
    assert "/api/fleet/files/{branch_id}/{filename}" in legacy_paths


def test_ai_advisor_never_replaces_deterministic_priorities():
    evidence = {"branch_summary": {"fleet": {"readiness": {"green": 1, "orange": 2, "red": 3}}, "alerts": {"active": 4, "red": 2, "orange": 2}, "service_kit_stock": {"available": 1, "reorder": 1, "stock_required": 2, "unknown": 0}, "operations": {"active_assignments": 0, "active_trips": 0, "active_reservations": 0, "open_maintenance": 1}}}
    actions = _deterministic_actions(evidence)
    assert any("blocked" in item.lower() for item in actions)
    assert any("red alert" in item.lower() for item in actions)
    assert any("service-kit" in item.lower() for item in actions)
    assert any("maintenance" in item.lower() for item in actions)
