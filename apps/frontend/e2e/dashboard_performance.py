"""Exercise concurrent dashboard loading with deterministic delayed API mocks.

Uses async Playwright so delayed domain handlers don't block unrelated routes.
"""
from __future__ import annotations

import asyncio
import json
from urllib.parse import urlparse

from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:3000"


async def main():
    requests = {"domains": 0, "audit": 0, "health": 0}
    in_flight = 0
    peak_in_flight = 0

    async def route_api(route):
        nonlocal in_flight, peak_in_flight
        path = urlparse(route.request.url).path
        if path == "/api/v1/auth/me":
            body = {"email": "owner@ithute.co.ls", "full_name": "Ithute Owner",
                    "is_platform_owner": True, "mfa_enabled": True}
        elif path == "/api/v1/me/customer-application":
            body = {"application": None}
        elif path == "/api/v1/tenants":
            body = [{"id": str(i), "name": f"Tenant {i}", "status": "active"}
                    for i in range(1, 11)]
        elif path.startswith("/api/v1/tenants/") and path.endswith("/domains"):
            requests["domains"] += 1
            in_flight += 1
            peak_in_flight = max(peak_in_flight, in_flight)
            try:
                await asyncio.sleep(0.5)
                body = {"items": []}
            finally:
                in_flight -= 1
        elif path.startswith("/api/v1/audit/platform"):
            requests["audit"] += 1
            body = []
        else:
            body = {}
        await route.fulfill(status=200, content_type="application/json",
                            body=json.dumps(body))

    async def health(route):
        requests["health"] += 1
        await route.fulfill(status=200, content_type="application/json",
                            body='{"status":"ok"}')

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        await page.route("**/api/v1/**", route_api)
        await page.route("**/health/ready", health)
        await page.goto(BASE + "/dashboard")
        await page.get_by_text("Reviewing your domains").wait_for(timeout=15000)
        # Independent audit should finish before deliberately delayed domains.
        await page.get_by_text("Loading activity...", exact=True).wait_for(
            state="hidden", timeout=15000
        )
        assert await page.get_by_text("Reviewing your domains").is_visible(), (
            "Audit awaited domain aggregation instead of running independently"
        )
        await page.get_by_text("Reviewing your domains").wait_for(
            state="hidden", timeout=20000
        )
        assert requests == {"domains": 10, "audit": 1, "health": 1}, requests
        assert 1 < peak_in_flight <= 5, peak_in_flight
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
