from pathlib import Path


def test_phase30_client_portal_contract_is_wired() -> None:
    root = Path(__file__).resolve().parents[1]
    api = (root / "app/api/v1/client_portal.py").read_text()
    models = (root / "app/models/client_portal.py").read_text()
    migration = (root / "alembic/versions/0031_phase30_client_portal.py").read_text()
    frontend = root.parents[0] / "frontend/app/client-portal/page.tsx"
    guard = (root / "app/security/access_guard.py").read_text()
    navigation = (root.parents[0] / "frontend/app/components/buildtrack-navigation.tsx").read_text()

    assert 'revision="0031_phase30_client_portal"' in migration
    assert 'down_revision="0030_phase29_tools"' in migration
    for value in ("client_share_packs", "client_portal_audit_events", "token_hash", "expiry_date"):
        assert value in models or value in migration
    for value in (
        "secrets.token_urlsafe",
        "Self-publication is disabled",
        "Only an active public controlled document from this project site may be shared",
        'action="clientportal.pack.viewed"',
        'action="clientportal.pack.document_downloaded"',
        "/public/{token}/document",
    ):
        assert value in api
    assert 'request.url.path.startswith("/api/v1/client-portal/public/")' in guard
    assert frontend.exists() and "FormDialog" in frontend.read_text() and "Client Portal &amp; Controlled Sharing" in frontend.read_text()
    assert 'href: "/client-portal"' in navigation
