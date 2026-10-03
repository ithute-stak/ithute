from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_security_operations_api_is_owner_only_and_supports_resolution():
    source = (ROOT / "app" / "api" / "v1" / "security_operations.py").read_text()
    assert "require_platform_owner" in source
    assert '@router.get("/summary")' in source
    assert '@router.get("/audit-integrity")' in source
    assert '@router.post("/events/{event_id}/resolve")' in source


def test_audit_integrity_listener_is_installed_at_startup():
    source = (ROOT / "app" / "main.py").read_text()
    assert "install_audit_integrity()" in source
