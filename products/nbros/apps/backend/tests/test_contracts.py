from app.fleet_advisor import _deterministic_actions
from app.main import app


def test_operational_routes_are_registered():
    paths = set(app.openapi()["paths"])
    assert "/api/v1/fleet/advisor" in paths
    assert "/api/v1/fleet/reports/summary" in paths
    assert "/api/v1/fleet/inventory" in paths
    assert "/api/v1/fleet/dashboard" in paths
    assert "/api/fleet/files/{branch_id}/{filename}" in paths


def test_ai_advisor_never_replaces_deterministic_priorities():
    evidence = {
        "branch_summary": {
            "fleet": {"readiness": {"green": 1, "orange": 2, "red": 3}},
            "alerts": {"active": 4, "red": 2, "orange": 2},
            "service_kit_stock": {"available": 1, "reorder": 1, "stock_required": 2, "unknown": 0},
            "operations": {
                "active_assignments": 0,
                "active_trips": 0,
                "active_reservations": 0,
                "open_maintenance": 1,
            },
        }
    }
    actions = _deterministic_actions(evidence)
    assert any("blocked" in item.lower() for item in actions)
    assert any("red alert" in item.lower() for item in actions)
    assert any("service-kit" in item.lower() for item in actions)
    assert any("maintenance" in item.lower() for item in actions)
