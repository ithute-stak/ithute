from pathlib import Path
ROOT = Path(__file__).resolve().parents[2] / "frontend/app/developer"

def test_developer_home_uses_packaged_sdk_name_and_first_party_routes():
    page = (ROOT / "page.tsx").read_text()
    assert '@ithute/auth-nextjs' not in page
    assert 'from "ithute-auth"' in page
    assert 'href: "/developer/docs/accounts-and-mail"' in page
    assert 'href: "/developer/docs/api-reference"' in page
    assert 'href: "/ithute-platform"' not in page

def test_docs_index_no_longer_recommends_repository_package():
    page = (ROOT / "docs/page.tsx").read_text()
    assert "SDK is distributed from the repository" not in page
    assert '<Link key={p.file} href={`/developer/docs/${p.file}`}' in page
