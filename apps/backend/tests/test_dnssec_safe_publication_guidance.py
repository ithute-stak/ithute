"""Guard against presenting unsupported DS records for registrar publication."""
from pathlib import Path


def test_parent_ds_api_only_recommends_compatible_records():
    source = (Path(__file__).resolve().parents[1] / "app/api/v1/dns_phase5.py").read_text()
    section = source.split('def parent_ds_status(', 1)[1].split('@router.get("/dnssec/multi-resolver-validation")', 1)[0]
    assert "chosen = compatible" in section
    assert "chosen = compatible or selected" not in section
    assert '"manual_publication_ready": compatible is not None' in section


def test_frontend_requires_compatible_ds_before_manual_copy():
    source = (Path(__file__).resolve().parents[2] / "frontend/app/dns-security/page.tsx").read_text()
    assert "registrar?.manual_publication_ready&&registrar?.recommended_text" in source
    assert "Copy compatible DS" in source
