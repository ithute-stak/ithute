"""Regression guards for elevated OAuth app-management APIs and dashboard."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CENTRAL = ROOT.parent.parent / "platform/ithute-auth/app/admin.py"
GATEWAY = ROOT / "app/api/v1/ithute_platform.py"
DASHBOARD = ROOT.parent / "frontend/app/ithute-platform/page.tsx"


def test_upstream_registration_requires_admin_and_is_inactive_by_default():
    source = CENTRAL.read_text()
    assert '@router.post("/applications", response_model=AdminApplicationResponse, status_code=201)' in source
    assert "context: AuthContext = Depends(require_admin)" in source
    assert "register_application(" in source
    assert "event_type=\"admin_application_created\"" in source


def test_gateway_requires_elevation_for_registration_and_callback_changes():
    source = GATEWAY.read_text()
    assert '@router.post("/auth/applications", status_code=201)' in source
    assert '@router.put("/auth/applications/{client_id}/redirects")' in source
    assert "token = _elevated_token(request, current)" in source


def test_dashboard_registers_disabled_applications_through_server():
    source = DASHBOARD.read_text()
    assert "Create disabled application" in source
    assert 'apiMutation("/platform/ithute/auth/applications"' in source
    assert "redirect_uris" in source
