from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
ROUTE = (ROOT / "app/api/v1/ithute_platform.py").read_text(encoding="utf-8")
ROUTER = (ROOT / "app/api/v1/router.py").read_text(encoding="utf-8")
BROKER = (ROOT / "app/services/ithute_platform_admin.py").read_text(encoding="utf-8")
PANEL_PAGE_PATH = REPO_ROOT / "apps/frontend/app/ithute-platform/page.tsx"
PANEL_SHELL_PATH = REPO_ROOT / "apps/frontend/components/control-shell.tsx"
PANEL_PAGE = PANEL_PAGE_PATH.read_text(encoding="utf-8") if PANEL_PAGE_PATH.exists() else ""
PANEL_SHELL = PANEL_SHELL_PATH.read_text(encoding="utf-8") if PANEL_SHELL_PATH.exists() else ""


def test_console_requires_local_platform_owner_and_linked_central_identity() -> None:
    assert "Depends(require_platform_owner)" in ROUTE
    assert "current.auth_user_id" in ROUTE
    assert "validate_admin_access_token" in ROUTE
    assert "/v1/admin/overview" in ROUTE


def test_step_up_uses_authorization_code_pkce_and_signed_state() -> None:
    assert '"response_type": "code"' in BROKER
    assert '"code_challenge_method": "S256"' in BROKER
    assert "sign_step_up_state" in BROKER
    assert "hmac.compare_digest" in BROKER
    assert '"nonce"' in BROKER
    assert "validate_id_token" in BROKER


def test_browser_never_receives_push_delegation_token() -> None:
    assert "push_admin_token(central_access_token" in BROKER
    assert 'headers={"Authorization": f"Bearer {delegated}"}' in BROKER
    assert "push_request(\"GET\"" in ROUTE
    assert "access_token\"" not in ROUTE.split("def combined_overview", 1)[1].split("@router.get", 1)[0]


def test_admin_cookie_is_http_only_and_short_lived() -> None:
    assert "httponly=True" in ROUTE
    assert "max_age=max_age" in ROUTE
    assert "step_up_seconds" in BROKER
    assert "refresh_token" not in ROUTE


@pytest.mark.skipif(
    not PANEL_PAGE_PATH.exists() or not PANEL_SHELL_PATH.exists(),
    reason="frontend source is not included in the backend-only container test image",
)
def test_superadmin_dashboard_is_registered_and_visible_in_panel_navigation() -> None:
    assert "api_router.include_router(ithute_platform.router)" in ROUTER
    assert 'href: "/ithute-platform"' in PANEL_SHELL
    assert 'label: "!thute Auth & Push"' in PANEL_SHELL
    assert 'title="!thute Auth & Push"' in PANEL_PAGE
    assert '"/platform/ithute/admin/status"' in PANEL_PAGE
    assert '"/platform/ithute/overview"' in PANEL_PAGE
    assert '"/platform/ithute/push/applications"' in PANEL_PAGE
    assert '"/platform/ithute/push/messages?limit=20"' in PANEL_PAGE


def test_panel_proxy_exposes_auth_and_push_superadmin_operations() -> None:
    required_fragments = (
        '@router.get("/admin/status")',
        '@router.get("/admin/login")',
        '@router.get("/admin/callback")',
        '@router.post("/admin/logout"',
        '@router.get("/overview")',
        '@router.get("/auth/users")',
        '@router.patch("/auth/users/{user_id}")',
        '@router.post("/auth/users/{user_id}/revoke-sessions")',
        '@router.get("/auth/applications")',
        '@router.patch("/auth/applications/{client_id}")',
        '@router.get("/push/applications")',
        '@router.get("/push/messages")',
    )
    for fragment in required_fragments:
        assert fragment in ROUTE
