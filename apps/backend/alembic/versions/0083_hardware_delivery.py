"""hardware incident delivery outbox and maintenance tasks

Revision ID: 0083_hardware_delivery
Revises: 0082_hardware_incidents
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0083_hardware_delivery"
down_revision = "0082_hardware_incidents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hardware_incident_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hardware_incidents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recipient_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "incident_id",
            "recipient_user_id",
            "channel",
            name="uq_hardware_incident_delivery_recipient_channel",
        ),
    )
    for name, cols in (
        ("ix_hw_delivery_incident", ["incident_id"]),
        ("ix_hw_delivery_recipient", ["recipient_user_id"]),
        ("ix_hw_delivery_channel", ["channel"]),
        ("ix_hw_delivery_status", ["status"]),
        ("ix_hw_delivery_next_attempt", ["next_attempt_at"]),
        ("ix_hw_delivery_delivered_at", ["delivered_at"]),
    ):
        op.create_index(name, "hardware_incident_deliveries", cols)

    op.create_table(
        "hardware_maintenance_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hardware_incidents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("server_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("infrastructure_servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("priority", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="open"),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("assigned_to_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("completed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("completion_note", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("incident_id", name="uq_hardware_maintenance_task_incident"),
    )
    for name, cols in (
        ("ix_hw_task_incident", ["incident_id"]),
        ("ix_hw_task_server", ["server_id"]),
        ("ix_hw_task_priority", ["priority"]),
        ("ix_hw_task_status", ["status"]),
        ("ix_hw_task_assignee", ["assigned_to_user_id"]),
        ("ix_hw_task_completed_by", ["completed_by_user_id"]),
        ("ix_hw_task_completed_at", ["completed_at"]),
    ):
        op.create_index(name, "hardware_maintenance_tasks", cols)


def downgrade() -> None:
    for name in (
        "ix_hw_task_completed_at",
        "ix_hw_task_completed_by",
        "ix_hw_task_assignee",
        "ix_hw_task_status",
        "ix_hw_task_priority",
        "ix_hw_task_server",
        "ix_hw_task_incident",
    ):
        op.drop_index(name, table_name="hardware_maintenance_tasks")
    op.drop_table("hardware_maintenance_tasks")

    for name in (
        "ix_hw_delivery_delivered_at",
        "ix_hw_delivery_next_attempt",
        "ix_hw_delivery_status",
        "ix_hw_delivery_channel",
        "ix_hw_delivery_recipient",
        "ix_hw_delivery_incident",
    ):
        op.drop_index(name, table_name="hardware_incident_deliveries")
    op.drop_table("hardware_incident_deliveries")
