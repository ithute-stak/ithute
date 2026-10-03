"""add Ithute Notification managed service client

Revision ID: 0011_notification_gateway_client
Revises: 0010_zero_trust_identity
"""

from datetime import datetime, timezone
import json
import uuid

from alembic import op
import sqlalchemy as sa

revision = "0011_notification_gateway_client"
down_revision = "0010_zero_trust_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    exists = connection.scalar(
        sa.text("SELECT 1 FROM managed_service_clients WHERE client_id = :client_id"),
        {"client_id": "ithute-notification"},
    )
    if exists:
        return
    now = datetime.now(timezone.utc)
    connection.execute(
        sa.text(
            """
            INSERT INTO managed_service_clients (
                id, client_id, name, description, allowed_audiences_json,
                allowed_scopes_json, is_active, created_at, updated_at
            ) VALUES (
                :id, :client_id, :name, :description, :audiences,
                :scopes, true, :created_at, :updated_at
            )
            """
        ),
        {
            "id": uuid.uuid4(),
            "client_id": "ithute-notification",
            "name": "Ithute Notification Gateway",
            "description": "Platform gateway that delegates Push delivery while coordinating email and SMS notifications.",
            "audiences": json.dumps(["ithute-push"], separators=(",", ":")),
            "scopes": json.dumps(["push.send.delegated"], separators=(",", ":")),
            "created_at": now,
            "updated_at": now,
        },
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM managed_service_clients WHERE client_id = 'ithute-notification'"))
