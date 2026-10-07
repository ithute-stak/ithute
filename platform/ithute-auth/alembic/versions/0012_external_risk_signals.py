"""add verified external identity risk signals

Revision ID: 0012_external_risk_signals
Revises: 0011_notification_gateway_client
"""

from datetime import datetime, timezone
import json
import uuid

from alembic import op
import sqlalchemy as sa


revision = "0012_external_risk_signals"
down_revision = "0011_notification_gateway_client"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_risk_signals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("source_client_id", sa.String(length=120), nullable=False),
        sa.Column("source_ref", sa.String(length=160), nullable=False),
        sa.Column("signal_type", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("risk_weight", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_client_id", "source_ref", name="uq_external_risk_source_ref"),
    )
    op.create_index("ix_external_risk_signals_user_id", "external_risk_signals", ["user_id"])
    op.create_index("ix_external_risk_signals_source_client_id", "external_risk_signals", ["source_client_id"])
    op.create_index("ix_external_risk_signals_signal_type", "external_risk_signals", ["signal_type"])
    op.create_index("ix_external_risk_signals_expires_at", "external_risk_signals", ["expires_at"])
    op.create_index("ix_external_risk_signals_created_at", "external_risk_signals", ["created_at"])

    connection = op.get_bind()
    exists = connection.scalar(
        sa.text("SELECT 1 FROM managed_service_clients WHERE client_id = :client_id"),
        {"client_id": "ithute-mail-intelligence"},
    )
    if not exists:
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
                "client_id": "ithute-mail-intelligence",
                "name": "Ithute Mail Intelligence",
                "description": "Publishes human-verified mail threat exposure into the central identity risk engine.",
                "audiences": json.dumps(["ithute-auth"], separators=(",", ":")),
                "scopes": json.dumps(["security.risk.write"], separators=(",", ":")),
                "created_at": now,
                "updated_at": now,
            },
        )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM managed_service_clients WHERE client_id = 'ithute-mail-intelligence'"))
    op.drop_index("ix_external_risk_signals_created_at", table_name="external_risk_signals")
    op.drop_index("ix_external_risk_signals_expires_at", table_name="external_risk_signals")
    op.drop_index("ix_external_risk_signals_signal_type", table_name="external_risk_signals")
    op.drop_index("ix_external_risk_signals_source_client_id", table_name="external_risk_signals")
    op.drop_index("ix_external_risk_signals_user_id", table_name="external_risk_signals")
    op.drop_table("external_risk_signals")
