"""add hardware supervised failure labels

Revision ID: 0087_hw_failure_labels
Revises: 0086_hw_remediation_verify
Create Date: 2026-10-06
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0087_hw_failure_labels"
down_revision = "0086_hw_remediation_verify"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hardware_failure_labels",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("server_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("label", sa.String(length=32), nullable=False),
        sa.Column("component", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False, server_default=""),
        sa.Column("confirmed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["incident_id"], ["hardware_incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["server_id"], ["infrastructure_servers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["hardware_telemetry_snapshots.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["confirmed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("incident_id", name="uq_hardware_failure_label_incident"),
    )
    op.create_index("ix_hardware_failure_labels_incident_id", "hardware_failure_labels", ["incident_id"])
    op.create_index("ix_hardware_failure_labels_server_id", "hardware_failure_labels", ["server_id"])
    op.create_index("ix_hardware_failure_labels_snapshot_id", "hardware_failure_labels", ["snapshot_id"])
    op.create_index("ix_hardware_failure_labels_label", "hardware_failure_labels", ["label"])
    op.create_index("ix_hardware_failure_labels_component", "hardware_failure_labels", ["component"])
    op.create_index("ix_hardware_failure_labels_confirmed_by_user_id", "hardware_failure_labels", ["confirmed_by_user_id"])
    op.create_index("ix_hardware_failure_labels_confirmed_at", "hardware_failure_labels", ["confirmed_at"])


def downgrade() -> None:
    op.drop_index("ix_hardware_failure_labels_confirmed_at", table_name="hardware_failure_labels")
    op.drop_index("ix_hardware_failure_labels_confirmed_by_user_id", table_name="hardware_failure_labels")
    op.drop_index("ix_hardware_failure_labels_component", table_name="hardware_failure_labels")
    op.drop_index("ix_hardware_failure_labels_label", table_name="hardware_failure_labels")
    op.drop_index("ix_hardware_failure_labels_snapshot_id", table_name="hardware_failure_labels")
    op.drop_index("ix_hardware_failure_labels_server_id", table_name="hardware_failure_labels")
    op.drop_index("ix_hardware_failure_labels_incident_id", table_name="hardware_failure_labels")
    op.drop_table("hardware_failure_labels")
