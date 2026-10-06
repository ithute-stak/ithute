"""hardware intelligence operations

Revision ID: 0081_hardware_operations
Revises: 0080_hardware_prediction
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0081_hardware_operations"
down_revision = "0080_hardware_prediction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hardware_maintenance_windows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("server_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("infrastructure_servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("suppress_notifications", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_hw_maint_server_id", "hardware_maintenance_windows", ["server_id"])
    op.create_index("ix_hw_maint_starts_at", "hardware_maintenance_windows", ["starts_at"])
    op.create_index("ix_hw_maint_ends_at", "hardware_maintenance_windows", ["ends_at"])
    op.create_index("ix_hw_maint_created_by", "hardware_maintenance_windows", ["created_by_user_id"])
    op.create_index("ix_hw_maint_cancelled_at", "hardware_maintenance_windows", ["cancelled_at"])

    op.create_table(
        "hardware_alert_acknowledgements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("server_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("infrastructure_servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hardware_telemetry_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("acknowledged_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("note", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("snapshot_id", name="uq_hardware_alert_ack_snapshot"),
    )
    op.create_index("ix_hw_ack_server_id", "hardware_alert_acknowledgements", ["server_id"])
    op.create_index("ix_hw_ack_snapshot_id", "hardware_alert_acknowledgements", ["snapshot_id"])
    op.create_index("ix_hw_ack_user_id", "hardware_alert_acknowledgements", ["acknowledged_by_user_id"])
    op.create_index("ix_hw_ack_at", "hardware_alert_acknowledgements", ["acknowledged_at"])


def downgrade() -> None:
    op.drop_index("ix_hw_ack_at", table_name="hardware_alert_acknowledgements")
    op.drop_index("ix_hw_ack_user_id", table_name="hardware_alert_acknowledgements")
    op.drop_index("ix_hw_ack_snapshot_id", table_name="hardware_alert_acknowledgements")
    op.drop_index("ix_hw_ack_server_id", table_name="hardware_alert_acknowledgements")
    op.drop_table("hardware_alert_acknowledgements")

    op.drop_index("ix_hw_maint_cancelled_at", table_name="hardware_maintenance_windows")
    op.drop_index("ix_hw_maint_created_by", table_name="hardware_maintenance_windows")
    op.drop_index("ix_hw_maint_ends_at", table_name="hardware_maintenance_windows")
    op.drop_index("ix_hw_maint_starts_at", table_name="hardware_maintenance_windows")
    op.drop_index("ix_hw_maint_server_id", table_name="hardware_maintenance_windows")
    op.drop_table("hardware_maintenance_windows")
