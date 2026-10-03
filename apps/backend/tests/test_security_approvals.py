import json
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.security_governance import SecurityApprovalRequest
from app.services.security_approvals import SecurityApprovalError, consume_security_approval, now


class FakeDb:
    def __init__(self, row):
        self.row = row

    def get(self, model, key):
        if model is SecurityApprovalRequest and self.row.id == key:
            return self.row
        return None


def approval(**overrides):
    values = {
        "id": uuid4(),
        "action": "mail_node.failover",
        "resource_type": "mail_node",
        "resource_id": str(uuid4()),
        "payload_json": json.dumps({"target_node_id": "target", "snapshot_id": "snapshot"}),
        "status": "approved",
        "approved_at": now(),
        "expires_at": now() + timedelta(minutes=30),
        "consumed_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_security_approval_is_single_use_and_payload_bound():
    row = approval()
    db = FakeDb(row)
    consume_security_approval(
        db,
        approval_id=row.id,
        action=row.action,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        payload_match={"target_node_id": "target", "snapshot_id": "snapshot"},
    )
    assert row.status == "consumed"
    assert row.consumed_at is not None

    with pytest.raises(SecurityApprovalError, match="not approved|already consumed"):
        consume_security_approval(
            db,
            approval_id=row.id,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
        )


def test_security_approval_rejects_payload_mismatch():
    row = approval()
    with pytest.raises(SecurityApprovalError, match="payload"):
        consume_security_approval(
            FakeDb(row),
            approval_id=row.id,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            payload_match={"target_node_id": "wrong"},
        )
