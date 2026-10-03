from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services import security_approvals
from app.models.security_governance import SecurityApprovalRequest


class FakeDb:
    def __init__(self, row=None):
        self.row = row
        self.added = []
        self.commits = 0

    def get(self, model, key):
        if model is SecurityApprovalRequest and self.row and self.row.id == key:
            return self.row
        return None

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.commits += 1


def _row(requester, approver=None, status="approved"):
    now = security_approvals._now()
    payload = {"target_node_id": "target", "snapshot_id": "snapshot"}
    body, digest = security_approvals.canonical_payload(
        action="mail_node.failover",
        resource_type="mail_node",
        resource_id="source",
        payload=payload,
    )
    return SecurityApprovalRequest(
        id=uuid4(),
        action="mail_node.failover",
        resource_type="mail_node",
        resource_id="source",
        payload_json=body,
        payload_hash=digest,
        status=status,
        requested_by_user_id=requester,
        approved_by_user_id=approver,
        created_at=now,
        expires_at=now + timedelta(minutes=10),
        approved_at=now if approver else None,
    )


def test_requester_cannot_self_approve():
    user_id = uuid4()
    row = _row(user_id, status="pending")
    db = FakeDb(row)
    with pytest.raises(HTTPException, match="different administrator"):
        security_approvals.approve_dual_control(
            db,
            current=SimpleNamespace(id=user_id),
            approval_id=row.id,
        )


def test_approval_is_payload_bound_and_single_use():
    requester = uuid4()
    row = _row(requester, approver=uuid4())
    db = FakeDb(row)
    current = SimpleNamespace(id=requester)

    security_approvals.consume_dual_control(
        db,
        current=current,
        approval_id=row.id,
        action="mail_node.failover",
        resource_type="mail_node",
        resource_id="source",
        payload={"target_node_id": "target", "snapshot_id": "snapshot"},
    )
    assert row.status == "executed"
    assert row.executed_at is not None

    with pytest.raises(HTTPException, match="already used|has not been approved"):
        security_approvals.consume_dual_control(
            db,
            current=current,
            approval_id=row.id,
            action="mail_node.failover",
            resource_type="mail_node",
            resource_id="source",
            payload={"target_node_id": "target", "snapshot_id": "snapshot"},
        )


def test_changed_payload_is_rejected():
    requester = uuid4()
    row = _row(requester, approver=uuid4())
    db = FakeDb(row)
    with pytest.raises(HTTPException, match="does not match"):
        security_approvals.consume_dual_control(
            db,
            current=SimpleNamespace(id=requester),
            approval_id=row.id,
            action="mail_node.failover",
            resource_type="mail_node",
            resource_id="source",
            payload={"target_node_id": "other", "snapshot_id": "snapshot"},
        )
