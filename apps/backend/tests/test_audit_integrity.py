import json

from app.models.entities import AuditLog
from app.services import audit_integrity


def test_signed_audit_row_detects_tampering():
    row = AuditLog(
        action="api_key.create",
        resource_type="api_key",
        resource_id="key-1",
        metadata_json="{}",
    )
    metadata = {
        "_audit_integrity_version": 1,
        "_audit_integrity_prev": "genesis",
    }
    metadata["_audit_integrity_signature"] = audit_integrity._sign(
        audit_integrity._canonical(row, metadata, "genesis")
    )
    row.metadata_json = json.dumps(metadata)
    assert audit_integrity.verify_audit_row(row)["valid"] is True

    row.action = "api_key.delete"
    assert audit_integrity.verify_audit_row(row)["valid"] is False


def test_unsigned_legacy_row_is_identified():
    row = AuditLog(action="legacy", resource_type="test", metadata_json="{}")
    result = audit_integrity.verify_audit_row(row)
    assert result["signed"] is False
    assert result["valid"] is False
