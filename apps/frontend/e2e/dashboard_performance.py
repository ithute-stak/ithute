"""Dashboard performance regression: slow optional APIs must not block independent widgets."""
from __future__ import annotations

import json
import time
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:3000"


def main():
    calls = {"domains": 0, "audit": 0, "health": 0}
    def route_api(route):
        path = urlparse(route.request.url).path
        if path == "/api/v1/auth/me":
            body = {"email":"owner@ithute.co.ls","full_name":"Ithute Owner","is_platform_owner":True,"mfa_enabled":True}
        elif path == "/api/v1/me/customer-application":
            body = {"application":None}
        elif path == "/api/v1/tenants":
            body = [{"id":str(i),"name":f"Tenant {i}","status":"active"} for i in range(1,11)]
        elif path.startswith("/api/v1/tenants/") and path.endswith("/domains"):
            calls["domains"] += 1
            time.sleep(0.18)
            body = {"items":[]}
        elif path.startswith("/api/v1/audit/platform"):
            calls["audit"] += 1
            body = []
        else:
            body = {}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.route("**/api/v1/**", route_api)
        def health(route):
            calls["health"] += 1
            route.fulfill(status=200, body='{"status":"ok"}')
        page.route("**/health/ready", health)
        page.goto(BASE + "/dashboard")
        page.get_by_text("Reviewing your domains").wait_for(timeout=15000)
        # Audit and health should start while slow per-tenant domains remain in flight.
        page.wait_for_function("() => document.body.textContent.includes('Recent activity') || document.body.textContent.includes('No recent')", timeout=15000)
        page.get_by_text("Reviewing your domains").wait_for(timeout=15000)
        page.wait_for_function("() => !document.body.textContent.includes('Reviewing your domains')", timeout=20000)
        assert calls["domains"] == 10, calls
        assert calls["audit"] >= 1, calls
        assert calls["health"] >= 1, calls
        browser.close()


if __name__ == "__main__":
    main()
