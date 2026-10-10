from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]/"frontend/app/developer"

def test_developer_dashboard_uses_wide_layout_and_first_party_docs():
    dashboard=(ROOT/"dashboard/page.tsx").read_text()
    assert "mx-3 max-w-none" in dashboard
    assert 'href="/developer/docs"' in dashboard
    assert "Approval is a review decision, not automatic service provisioning" in dashboard

def test_guides_have_route_back_to_authenticated_workspace():
    guide=(ROOT/"docs/[slug]/page.tsx").read_text()
    assert 'href="/developer/dashboard"' in guide
    assert 'href="/developer/docs"' in guide
