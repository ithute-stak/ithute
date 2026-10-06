"""verify remediation outcomes from telemetry

Revision ID: 0086_hw_remediation_verify
Revises: 0085_hw_ai_models
Create Date: 2026-10-06
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0086_hw_remediation_verify"
down_revision = "0085_hw_ai_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hardware_maintenance_tasks", sa.Column("remediation_baseline_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("hardware_maintenance_tasks", sa.Column("remediation_verified_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("hardware_maintenance_tasks", sa.Column("measured_outcome", sa.String(length=24), nullable=False, server_default=""))
    op.add_column("hardware_maintenance_tasks", sa.Column("verification_confidence", sa.Float(), nullable=True))
    op.add_column("hardware_maintenance_tasks", sa.Column("verification_sample_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("hardware_maintenance_tasks", sa.Column("verification_evidence_json", sa.Text(), nullable=False, server_default="[]"))
    op.add_column("hardware_maintenance_tasks", sa.Column("verification_evaluated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_hw_task_remediation_baseline_snapshot",
        "hardware_maintenance_tasks",
        "hardware_telemetry_snapshots",
        ["remediation_baseline_snapshot_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_hw_task_remediation_verified_snapshot",
        "hardware_maintenance_tasks",
        "hardware_telemetry_snapshots",
        ["remediation_verified_snapshot_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_hw_task_measured_outcome", "hardware_maintenance_tasks", ["measured_outcome"])
    op.create_index("ix_hw_task_verification_evaluated_at", "hardware_maintenance_tasks", ["verification_evaluated_at"])


def downgrade() -> None:
    op.drop_index("ix_hw_task_verification_evaluated_at", table_name="hardware_maintenance_tasks")
    op.drop_index("ix_hw_task_measured_outcome", table_name="hardware_maintenance_tasks")
    op.drop_constraint("fk_hw_task_remediation_verified_snapshot", "hardware_maintenance_tasks", type_="foreignkey")
    op.drop_constraint("fk_hw_task_remediation_baseline_snapshot", "hardware_maintenance_tasks", type_="foreignkey")
    op.drop_column("hardware_maintenance_tasks", "verification_evaluated_at")
    op.drop_column("hardware_maintenance_tasks", "verification_evidence_json")
    op.drop_column("hardware_maintenance_tasks", "verification_sample_count")
    op.drop_column("hardware_maintenance_tasks", "verification_confidence")
    op.drop_column("hardware_maintenance_tasks", "measured_outcome")
    op.drop_column("hardware_maintenance_tasks", "remediation_verified_snapshot_id")
    op.drop_column("hardware_maintenance_tasks", "remediation_baseline_snapshot_id")
