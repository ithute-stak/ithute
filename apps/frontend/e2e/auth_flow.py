from __future__ import annotations

import json
from urllib.parse import urlparse

from playwright.sync_api import Route, sync_playwright


BASE_URL = "http://127.0.0.1:3000"
USER = {
    "email": "owner@ithute.co.ls",
    "full_name": "Ithute Owner",
    "is_platform_owner": True,
    "mfa_enabled": True,
}


def main() -> None:
    state = {
        "authenticated": False,
        "fail_me_once": False,
        "refresh_calls": 0,
        "logout_calls": 0,
    }

    def api_route(route: Route) -> None:
        path = urlparse(route.request.url).path
        method = route.request.method

        if path == "/api/v1/auth/ithute/login":
            state["authenticated"] = True
            state["fail_me_once"] = True
            route.fulfill(status=303, headers={"Location": "/dashboard"})
            return

        if path == "/api/v1/auth/me":
            if not state["authenticated"]:
                route.fulfill(status=401, content_type="application/json", body='{"detail":"Authentication required"}')
                return
            if state["fail_me_once"]:
                state["fail_me_once"] = False
                route.fulfill(status=401, content_type="application/json", body='{"detail":"expired"}')
                return
            route.fulfill(status=200, content_type="application/json", body=json.dumps(USER))
            return

        if path == "/api/v1/auth/ithute/refresh":
            state["refresh_calls"] += 1
            if not state["authenticated"]:
                route.fulfill(status=401, content_type="application/json", body='{"detail":"expired"}')
                return
            route.fulfill(status=200, content_type="application/json", body='{"refreshed":true}')
            return

        if path == "/api/v1/auth/refresh":
            route.fulfill(status=401, content_type="application/json", body='{"detail":"legacy disabled"}')
            return

        if path == "/api/v1/auth/capabilities":
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "local_auth_enabled": False,
                        "central_auth_enabled": True,
                        "local_security_controls_enabled": False,
                    }
                ),
            )
            return

        if path == "/api/v1/auth/ithute/account":
            route.fulfill(status=303, headers={"Location": "/central-security"})
            return

        if path == "/api/v1/auth/logout" and method == "POST":
            state["logout_calls"] += 1
            state["authenticated"] = False
            route.fulfill(status=204, body="")
            return

        if path == "/api/v1/tenants":
            route.fulfill(status=200, content_type="application/json", body="[]")
            return

        if path.startswith("/api/v1/audit/platform"):
            route.fulfill(status=200, content_type="application/json", body="[]")
            return

        route.fulfill(status=404, content_type="application/json", body='{"detail":"not mocked"}')

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.route("**/api/v1/**", api_route)
        page.route(
            "**/health/ready",
            lambda route: route.fulfill(status=200, content_type="application/json", body='{"status":"ok"}'),
        )
        page.route(
            "**/central-security",
            lambda route: route.fulfill(
                status=200,
                content_type="text/html",
                body="<html><body><h1>Ithute Central Security Center</h1></body></html>",
            ),
        )

        page.goto(f"{BASE_URL}/login")
        page.get_by_role("link", name="Sign in with Ithute").click()
        page.wait_for_url(f"{BASE_URL}/dashboard")

        page.get_by_text("Control Centre", exact=False).first.wait_for()
        for _ in range(50):
            if state["refresh_calls"] == 1:
                break
            page.wait_for_timeout(100)
        assert state["refresh_calls"] == 1, "dashboard must refresh an expired central session exactly once"
        page.wait_for_timeout(200)
        assert page.url.endswith("/dashboard"), "successful central refresh must not bounce back to login"

        page.goto(f"{BASE_URL}/security")
        page.get_by_text("Managed by Ithute central authentication").wait_for()
        center = page.get_by_role("link", name="Open central security center")
        assert center.get_attribute("href") == f"{BASE_URL}/api/v1/auth/ithute/account"

        center.click()
        page.wait_for_url(f"{BASE_URL}/central-security")
        page.get_by_role("heading", name="Ithute Central Security Center").wait_for()

        page.go_back()
        page.wait_for_url(f"{BASE_URL}/security")
        page.get_by_text("Managed by Ithute central authentication").wait_for()

        page.get_by_role("button", name="Sign out").click()
        page.wait_for_url(f"{BASE_URL}/login")
        assert state["logout_calls"] == 1
        page.get_by_text("Welcome back").wait_for()

        browser.close()


if __name__ == "__main__":
    main()
