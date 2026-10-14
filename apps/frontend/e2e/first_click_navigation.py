"""First-click navigation regression for actual Ithute control-centre links.

Run against the local Next.js server started by auth-browser-e2e.yml.
API responses are mocked so navigation is not conflated with backend latency.
"""
import json
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:3000"


def mock_api(route):
    path = urlparse(route.request.url).path
    payload = {"items": [], "total": 0}
    if path == "/api/v1/auth/me":
        payload = {"email": "owner@ithute.co.ls", "full_name": "Ithute Owner", "is_platform_owner": True, "mfa_enabled": True}
    elif path in ("/api/v1/tenants", "/api/v1/me/memberships", "/api/v1/audit/platform"):
        payload = []
    elif path == "/api/v1/me/customer-application":
        payload = {"application": None}
    elif path == "/api/v1/auth/capabilities":
        payload = {"local_auth_enabled": True, "central_auth_enabled": False}
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))


def verify_direct_navigation(page, target, expected_path):
    page.get_by_role("link", name=target, exact=True).click()
    page.wait_for_url(f"{BASE_URL}{expected_path}", timeout=15000)
    assert urlparse(page.url).path == expected_path


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for viewport in ({"width": 1440, "height": 900}, {"width": 390, "height": 844}):
            context = browser.new_context(viewport=viewport, service_workers="block")
            page = context.new_page()
            page.route("**/api/v1/**", mock_api)
            page.route("**/health/ready", lambda route: route.fulfill(status=200, body="ok"))
            page.goto(f"{BASE_URL}/dashboard")
            page.get_by_text("Ithute Control Centre", exact=True).first.wait_for(timeout=15000)

            mobile = viewport["width"] < 1024
            if mobile:
                page.get_by_role("button", name="Toggle navigation").click()
            # Expanders are distinct from direct links: one click expands a category.
            page.get_by_role("button", name="Mail platform").click()
            verify_direct_navigation(page, "Mailboxes", "/mailboxes")
            if mobile:
                page.get_by_role("button", name="Toggle navigation").click()
            verify_direct_navigation(page, "Command centre", "/dashboard")
            context.close()
        browser.close()


if __name__ == "__main__":
    main()
