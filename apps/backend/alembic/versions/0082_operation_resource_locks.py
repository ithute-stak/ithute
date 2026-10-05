"""add hosting operation resource locks and waits

Revision ID: 0082_operation_resource_locks
Revises: 0081_operation_leases
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0082_operation_resource_locks"
down_revision = "0081_operation_leases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hosting_operation_resource_locks",
        sa.Column("resource_key", sa.String(length=255), primary_key=True, nullable=False),
        sa.Column("operation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_project_operations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fencing_token", sa.String(length=64), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_hosting_operation_resource_locks_operation_id", "hosting_operation_resource_locks", ["operation_id"])
    op.create_index("ix_hosting_operation_resource_locks_lease_expires_at", "hosting_operation_resource_locks", ["lease_expires_at"])

    op.create_table(
        "hosting_operation_resource_waits",
        sa.Column("operation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_project_operations.id", ondelete="CASCADE"), primary_key=True, nullable=False),
        sa.Column("resource_key", sa.String(length=255), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_hosting_operation_resource_waits_resource_key", "hosting_operation_resource_waits", ["resource_key"])


def downgrade() -> None:
    op.drop_index("ix_hosting_operation_resource_waits_resource_key", table_name="hosting_operation_resource_waits")
    op.drop_table("hosting_operation_resource_waits")
    op.drop_index("ix_hosting_operation_resource_locks_lease_expires_at", table_name="hosting_operation_resource_locks")
    op.drop_index("ix_hosting_operation_resource_locks_operation_id", table_name="hosting_operation_resource_locks")
    op.drop_table("hosting_operation_resource_locks")
