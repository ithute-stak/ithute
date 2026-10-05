"""add hosting operation leases and fencing

Revision ID: 0081_operation_leases
Revises: 0080_hosting_operation_retire
"""

from alembic import op
import sqlalchemy as sa

revision = "0081_operation_leases"
down_revision = "0080_hosting_operation_retire"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hosting_project_operations", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("hosting_project_operations", sa.Column("fencing_token", sa.String(length=64), nullable=True))
    op.add_column("hosting_project_operations", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("hosting_project_operations", sa.Column("lease_heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_hosting_project_operations_lease_expires_at", "hosting_project_operations", ["lease_expires_at"])
    op.create_check_constraint(
        "ck_hosting_project_operation_attempt_count_nonnegative",
        "hosting_project_operations",
        "attempt_count >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_hosting_project_operation_attempt_count_nonnegative",
        "hosting_project_operations",
        type_="check",
    )
    op.drop_index("ix_hosting_project_operations_lease_expires_at", table_name="hosting_project_operations")
    op.drop_column("hosting_project_operations", "lease_heartbeat_at")
    op.drop_column("hosting_project_operations", "lease_expires_at")
    op.drop_column("hosting_project_operations", "fencing_token")
    op.drop_column("hosting_project_operations", "attempt_count")
