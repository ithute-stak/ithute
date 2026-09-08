from pathlib import Path


def test_phase31_vendor_portal_contract_is_wired() -> None:
    root = Path(__file__).resolve().parents[1]
    api = (root / "app/api/v1/vendor_portal.py").read_text()
    models = (root / "app/models/vendor_portal.py").read_text()
    migration = (root / "alembic/versions/0032_phase31_vendor_portal.py").read_text()
    guard = (root / "app/security/access_guard.py").read_text()
    internal_ui = root.parents[0] / "frontend/app/vendor-portal/page.tsx"
    external_ui = root.parents[0] / "frontend/app/vendor-submissions/[token]/page.tsx"

    assert 'revision="0032_phase31_vendor_portal"' in migration and 'down_revision="0031_phase30_client_portal"' in migration
    for value in ("vendor_portal_requests", "vendor_portal_evidence", "vendor_portal_audit_events", "token_hash"):
        assert value in models or value in migration
    for value in ("secrets.token_urlsafe", "Self-publication is disabled", "Only a published vendor request can be revoked", "/public/{token}/respond", "Evidence exceeds the 25 MB upload limit", 'action="vendorportal.request.evidence_received"'):
        assert value in api
    assert 'request.url.path.startswith("/api/v1/vendor-portal/public/")' in guard
    assert internal_ui.exists() and "FormDialog" in internal_ui.read_text() and "Supplier &amp; Subcontractor Evidence Portal" in internal_ui.read_text()
    assert external_ui.exists() and "Submit evidence" in external_ui.read_text()
