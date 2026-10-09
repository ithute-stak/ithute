"""Developer review management is gated by Ithute platform ownership and Auth step-up."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
GATEWAY=ROOT / "backend/app/api/v1/ithute_platform.py"
UI=ROOT / "frontend/app/ithute-platform/page.tsx"

def test_review_gateway_requires_platform_owner_and_step_up():
    source=GATEWAY.read_text()
    assert '@router.get("/developer/access-requests")' in source
    assert '@router.post("/developer/access-requests/{request_id}/decision")' in source
    assert "token = _elevated_token(request, current)" in source
    assert 'action="ithute.developer.access.decision"' in source

def test_review_ui_is_not_auto_provisioning():
    source=UI.read_text()
    assert "Developer access requests" in source
    assert 'decideDeveloperRequest(r.id,"approved")' in source
    assert 'decideDeveloperRequest(r.id,"rejected")' in source
    assert "Product provisioning remains a separate step." in source
