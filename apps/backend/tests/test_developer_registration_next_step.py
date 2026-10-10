from pathlib import Path
ROOT=Path(__file__).resolve().parents[2] / "frontend/app/developer"
def test_registration_success_points_to_developer_dashboard():
    source=(ROOT/"register/page.tsx").read_text()
    assert 'success&&<Link href="/developer/dashboard"' in source
    assert "Verify your email first" in source
    assert "service access requires approval" in source
    assert "Already registered? Open your developer workspace" in source
    assert 'href="/login" className="font-semibold text-cyan-300"' not in source
