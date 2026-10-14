"""First-click navigation regression for actual Ithute control-centre links.

Run against the local Next.js server started by auth-browser-e2e.yml.
API responses are mocked so navigation is not conflated with backend latency.
"""
import json
import time
from itertools import count
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:3000"
CLICK_TRACE_SEQUENCE = count()


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
    """Record the first actual click before waiting for a route transition."""
    link = page.locator("aside:visible").get_by_role("link", name=target, exact=True)
    assert link.get_attribute("href") == expected_path, (
        f"{target}: href differs from expected {expected_path}"
    )
    # The document-level capture handler runs before React's delegated click
    # handlers. It establishes whether the browser delivered the first click.
    click_events = []
    callback = "recordIthuteNavigationClick" + str(next(CLICK_TRACE_SEQUENCE))
    page.expose_function(callback, lambda event: click_events.append(event))
    page.evaluate("""(callback) => {
      document.addEventListener("click", event => {
        const link = event.target.closest?.('a[href]');
        if (link) window[callback]({
          href: link.getAttribute("href"),
          trusted: event.isTrusted,
          time: performance.now()
        });
      }, {capture: true, once: true});
    }""", callback)
    started = time.monotonic()
    link.click()
    try:
        page.wait_for_url(f"{BASE_URL}{expected_path}", timeout=15000)
    except Exception as error:
        raise AssertionError(
            f"First-click navigation failed: {target} -> {expected_path}; "
            f"observed_url={page.url}; clicks={click_events}; "
            f"elapsed_ms={int((time.monotonic() - started) * 1000)}"
        ) from error
    assert click_events and click_events[0]["href"] == expected_path, (
        f"{target}: route changed without expected initial click evidence: {click_events}"
    )
    print(json.dumps({
        "event": "first_click_navigation",
        "label": target,
        "destination": expected_path,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "clicks": click_events,
    }))


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for viewport in ({"width": 1440, "height": 900}, {"width": 390, "height": 844}):
            context = browser.new_context(viewport=viewport, service_workers="block")
            page = context.new_page()
            page.route("**/api/v1/**", mock_api)
            page.route("**/health/ready", lambda route: route.fulfill(status=200, body="ok"))
            page.goto(f"{BASE_URL}/dashboard")
            page.locator(".control-shell-topbar").wait_for(state="visible", timeout=15000)

            mobile = viewport["width"] < 1024
            if mobile:
                page.get_by_role("button", name="Toggle navigation").click()
            # Expanders are distinct from direct links: one click expands a category.
            page.locator("aside:visible").get_by_role("button", name="Expand Mail platform").click()
            verify_direct_navigation(page, "Mailboxes", "/mailboxes")
            if mobile:
                page.get_by_role("button", name="Toggle navigation").click()
            verify_direct_navigation(page, "Command centre", "/dashboard")
            # Each direct route should navigate after exactly one click, not a retry.
            for group, label, destination in (
                ("Domains & DNS", "Domain portfolio", "/domains"),
                ("Domains & DNS", "DNS zones", "/dns"),
                ("Application hosting", "Hosted projects", "/hosting"),
                ("Business", "Billing & subscription", "/billing"),
            ):
                page.goto(f"{BASE_URL}/dashboard")
                page.locator(".control-shell-topbar").wait_for(state="visible", timeout=15000)
                if mobile:
                    page.get_by_role("button", name="Toggle navigation").click()
                sidebar = page.locator("aside:visible")
                sidebar.get_by_role("button", name=f"Expand {group}").click()
                assert sidebar.get_by_role("link", name=label, exact=True).is_visible()
                verify_direct_navigation(page, label, destination)
            if not mobile:
                # Category text itself is a real link; expansion has a separate control.
                page.goto(f"{BASE_URL}/dashboard")
                page.locator(".control-shell-topbar").wait_for(state="visible", timeout=15000)
                page.locator("aside:visible").get_by_role("link", name="Domains & DNS", exact=True).click()
                page.wait_for_url(f"{BASE_URL}/domains", timeout=15000)
            if not mobile:
                # Compact desktop sidebar also exposes the primary destination
                # directly; opening the submenu is a separate chevron action.
                page.goto(f"{BASE_URL}/dashboard")
                page.locator(".control-shell-topbar").wait_for(state="visible", timeout=15000)
                page.get_by_role("button", name="Toggle navigation").click()
                sidebar = page.locator("aside:visible")
                sidebar.get_by_role("link", name="Domains & DNS", exact=True).click()
                page.wait_for_url(f"{BASE_URL}/domains", timeout=15000)
                sidebar.get_by_role("button", name="Expand Domains & DNS").click()
                assert sidebar.get_by_role("menuitem", name="DNS zones").is_visible()
            context.close()
        browser.close()


if __name__ == "__main__":
    main()
