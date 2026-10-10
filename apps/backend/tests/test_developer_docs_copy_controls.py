from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "frontend/app/developer/docs"

def test_documentation_code_examples_use_first_party_copy_control():
    page = (ROOT / "[slug]/page.tsx").read_text()
    component = (ROOT / "developer-code-block.tsx").read_text()
    assert 'import { DeveloperCodeBlock } from "../developer-code-block"' in page
    assert "<DeveloperCodeBlock code={section.code}/>" in page
    assert '"use client"' in component
    assert 'navigator.clipboard.writeText(code)' in component
    assert 'aria-label={copied ? "Code copied" : "Copy code"}' in component
    assert "window.location" not in component
