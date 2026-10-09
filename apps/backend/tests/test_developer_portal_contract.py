"""Public developer signup remains gated by server-side verification."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "frontend/app/developer"

def test_signup_is_not_a_mailbox_provisioning_endpoint():
    portal = (ROOT / "page.tsx").read_text()
    assert "mailbox" in portal.lower()
    assert "separate" in portal.lower()
    assert "/developer/register" in portal

def test_signup_requires_server_verified_challenge():
    route = (ROOT / "api/register/route.ts").read_text()
    assert "ITHUTE_DEVELOPER_TURNSTILE_SECRET" in route
    assert "turnstile/v0/siteverify" in route
    assert "outcome.hostname!==request.nextUrl.hostname" in route
    assert "Cross-origin registration rejected." in route
    assert 'fetch(new URL("/v1/users/register",target)' in route

def test_browser_form_supplies_turnstile_token():
    page = (ROOT / "register/page.tsx").read_text()
    assert "NEXT_PUBLIC_ITHUTE_DEVELOPER_TURNSTILE_SITE_KEY" in page
    assert "verificationToken" in page
    assert "cf-turnstile" in page
