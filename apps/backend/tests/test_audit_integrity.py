from types import SimpleNamespace
from uuid import uuid4

from app.services.audit_integrity import calculate_event_hash, classify_security_event


def _row(**overrides):
    values = {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "actor_user_id": uuid4(),
        "action": "mail_node.failover.complete",
        "resource_type": "mail_node",
        "resource_id": "node-1",
        "metadata_json": '{"target":"node-2"}',
        "event_hash": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_audit_hash_changes_when_protected_event_content_changes():
    row = _row()
    first = calculate_event_hash(row, "a" * 64)
    row.action = "mail_node.failover.failed"
    second = calculate_event_hash(row, "a" * 64)
    assert first != second


def test_audit_hash_links_to_previous_event():
    row = _row()
    first = calculate_event_hash(row, "a" * 64)
    second = calculate_event_hash(row, "b" * 64)
    assert first != second


def test_security_event_classifier_escalates_revocation_and_failure():
    revoked = classify_security_event(_row(action="api_key.revoke", resource_type="api_key"))
    failed = classify_security_event(_row(action="mail_node.restore.failed"))
    assert revoked["severity"] == "high"
    assert revoked["category"] == "security"
    assert failed["severity"] == "high"


def test_audit_migration_blocks_update_and_delete():
    from pathlib import Path
    source = (Path(__file__).parents[1] / "alembic" / "versions" / "0063_audit_integrity.py").read_text()
    assert "BEFORE UPDATE OR DELETE ON audit_logs" in source
    assert "audit_logs is append-only" in source
    assert "pg_advisory_xact_lock" in source
