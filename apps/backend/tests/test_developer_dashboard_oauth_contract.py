"""Developer workspace uses backend OAuth session without browser token handling."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
API=(ROOT/"backend/app/api/v1/ithute_auth.py").read_text()
UI=(ROOT/"frontend/app/developer/dashboard/page.tsx").read_text()

def test_developer_proxy_requires_central_cookie_and_identity_match():
    assert 'token = request.cookies.get(settings.access_cookie_name)' in API
    assert 'UUID(str(claims["sub"])) != user.auth_user_id' in API
    assert '@router.get("/developer/requests")' in API
    assert '@router.post("/developer/requests", status_code=201)' in API
    assert 'request.headers.get("origin") != settings.frontend_url.rstrip("/")' in API

def test_workspace_never_requests_pasted_bearer_tokens():
    assert "/api/v1/auth/ithute/login?next=%2Fdeveloper%2Fdashboard" in UI
    assert "/api/v1/auth/ithute/developer/requests" in UI
    assert "Bearer " not in UI
    assert "sessionStorage" not in UI
