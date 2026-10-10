"""Public developer docs must stay inside Ithute and use broad layout."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]/"frontend/app/developer"

def test_public_pages_do_not_link_to_source_repository():
    for name in ("page.tsx","auth/page.tsx","docs/page.tsx","docs/[slug]/page.tsx"):
        source=(ROOT/name).read_text()
        assert "https://github.com/" not in source,name

def test_docs_are_rendered_as_ithute_pages():
    index=(ROOT/"docs/page.tsx").read_text()
    guides=(ROOT/"docs/[slug]/page.tsx").read_text()
    assert "href={`/developer/docs/${p.file}`}" in index
    for slug in ("authentication","nextjs","accounts-and-mail","api-reference","security"):
        assert f'"{slug}"' in guides
    assert "generateStaticParams" in guides

def test_installation_not_claimed_published():
    guide=(ROOT/"docs/[slug]/page.tsx").read_text()
    assert "Public npm installation is not yet available" in guide
    assert "npm install ithute-auth" in guide
    assert "Planned after npm publishing" in guide
