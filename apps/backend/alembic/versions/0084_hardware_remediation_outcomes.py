"""hardware remediation outcome learning

Revision ID: 0084_hardware_remediation_outcomes
Revises: 0083_hardware_delivery
"""

from alembic import op
import sqlalchemy as sa

revision = "0084_hardware_remediation_outcomes"
down_revision = "0083_hardware_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hardware_maintenance_tasks", sa.Column("remediation_action", sa.String(length=128), nullable=False, server_default=""))
    op.add_column("hardware_maintenance_tasks", sa.Column("remediation_outcome", sa.String(length=24), nullable=False, server_default=""))
    op.add_column("hardware_maintenance_tasks", sa.Column("outcome_recorded_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_hw_task_remediation_action", "hardware_maintenance_tasks", ["remediation_action"])
    op.create_index("ix_hw_task_remediation_outcome", "hardware_maintenance_tasks", ["remediation_outcome"])
    op.create_index("ix_hw_task_outcome_recorded_at", "hardware_maintenance_tasks", ["outcome_recorded_at"])


def downgrade() -> None:
    op.drop_index("ix_hw_task_outcome_recorded_at", table_name="hardware_maintenance_tasks")
    op.drop_index("ix_hw_task_remediation_outcome", table_name="hardware_maintenance_tasks")
    op.drop_index("ix_hw_task_remediation_action", table_name="hardware_maintenance_tasks")
    op.drop_column("hardware_maintenance_tasks", "outcome_recorded_at")
    op.drop_column("hardware_maintenance_tasks", "remediation_outcome")
    op.drop_column("hardware_maintenance_tasks", "remediation_action")
