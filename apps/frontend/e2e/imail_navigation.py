"""iMail floating navigation must respond to the first click across input sizes.

Run against local Next.js with mocked API responses; not a production auth test.
"""
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:3000"


def api_mock(route):
    path = urlparse(route.request.url).path
    if path == "/api/v1/auth/me":
        route.fulfill(status=200, content_type="application/json",
                      body='{"email":"owner@ithute.co.ls","is_platform_owner":true}')
    else:
        route.fulfill(status=200, content_type="application/json", body="{}")


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for width, height in ((1440, 900), (390, 844)):
            context = browser.new_context(viewport={"width": width, "height": height},
                                          service_workers="block")
            page = context.new_page()
            page.route("**/api/v1/**", api_mock)
            page.goto(BASE + "/webmail/settings")
            button = page.get_by_role("button", name="Open iMail Hub")
            button.wait_for(state="visible", timeout=15000)
            button.click()
            dialog = page.get_by_role("dialog", name="iMail navigation")
            dialog.wait_for(state="visible")
            link = dialog.get_by_role("link", name="Migration Center")
            assert link.get_attribute("href") == "/webmail/migrate"
            link.click()
            page.wait_for_url(BASE + "/webmail/migrate", timeout=15000)
            dialog.wait_for(state="hidden", timeout=15000)
            button.click()
            dialog.wait_for(state="visible")
            page.keyboard.press("Escape")
            dialog.wait_for(state="hidden")
            awaitable = page.get_by_role("button", name="Open iMail Hub")
            awaitable.click()
            dialog.wait_for(state="visible")
            page.locator("body").click(position={"x": 12, "y": 12})
            dialog.wait_for(state="hidden")
            context.close()
        browser.close()


if __name__ == "__main__":
    main()
