"""create centralized Ithute push tables

Revision ID: 0001_push_delivery
Revises:
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_push_delivery"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_endpoints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("auth_user_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.String(120), nullable=False),
        sa.Column("device_key", sa.String(200), nullable=False),
        sa.Column("platform", sa.String(24), nullable=False),
        sa.Column("provider", sa.String(24), nullable=False),
        sa.Column("endpoint_ciphertext", sa.Text(), nullable=False),
        sa.Column("endpoint_hash", sa.String(64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("auth_user_id", "application_id", "device_key", name="uq_push_endpoint_identity"),
    )
    op.create_index("ix_push_endpoints_auth_user_id", "push_endpoints", ["auth_user_id"])
    op.create_index("ix_push_endpoints_application_id", "push_endpoints", ["application_id"])
    op.create_index("ix_push_endpoints_device_key", "push_endpoints", ["device_key"])
    op.create_index("ix_push_endpoints_endpoint_hash", "push_endpoints", ["endpoint_hash"])

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_client_id", sa.String(120), nullable=False),
        sa.Column("recipient_user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("body", sa.String(500), nullable=False),
        sa.Column("route", sa.String(500), nullable=True),
        sa.Column("sound", sa.String(64), nullable=True),
        sa.Column("data_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_messages_source_client_id", "messages", ["source_client_id"])
    op.create_index("ix_messages_recipient_user_id", "messages", ["recipient_user_id"])
    op.create_index("ix_messages_status", "messages", ["status"])
    op.create_index("ix_messages_expires_at", "messages", ["expires_at"])

    op.create_table(
        "deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("endpoint_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("provider_message_id", sa.String(300), nullable=True),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["endpoint_id"], ["push_endpoints.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "endpoint_id", name="uq_delivery_message_endpoint"),
    )
    op.create_index("ix_deliveries_message_id", "deliveries", ["message_id"])
    op.create_index("ix_deliveries_endpoint_id", "deliveries", ["endpoint_id"])
    op.create_index("ix_deliveries_status", "deliveries", ["status"])
    op.create_index("ix_deliveries_next_attempt_at", "deliveries", ["next_attempt_at"])


def downgrade() -> None:
    op.drop_table("deliveries")
    op.drop_table("messages")
    op.drop_table("push_endpoints")
