"""add hosting resource reservations

Revision ID: 0077_resource_reservations
Revises: 0076_network_grants
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0077_resource_reservations"
down_revision = "0076_network_grants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hosting_resource_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("purpose", sa.String(length=80), nullable=False, server_default="placement"),
        sa.Column("cpu_millicores", sa.Integer(), nullable=False),
        sa.Column("memory_mb", sa.Integer(), nullable=False),
        sa.Column("storage_mb", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("cpu_millicores >= 0", name="ck_hosting_resource_reservation_cpu_nonnegative"),
        sa.CheckConstraint("memory_mb >= 0", name="ck_hosting_resource_reservation_memory_nonnegative"),
        sa.CheckConstraint("storage_mb >= 0", name="ck_hosting_resource_reservation_storage_nonnegative"),
    )
    op.create_index("ix_hosting_resource_reservations_node_id", "hosting_resource_reservations", ["node_id"])
    op.create_index("ix_hosting_resource_reservations_project_id", "hosting_resource_reservations", ["project_id"])
    op.create_index("ix_hosting_resource_reservations_status", "hosting_resource_reservations", ["status"])
    op.create_index("ix_hosting_resource_reservations_expires_at", "hosting_resource_reservations", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_hosting_resource_reservations_expires_at", table_name="hosting_resource_reservations")
    op.drop_index("ix_hosting_resource_reservations_status", table_name="hosting_resource_reservations")
    op.drop_index("ix_hosting_resource_reservations_project_id", table_name="hosting_resource_reservations")
    op.drop_index("ix_hosting_resource_reservations_node_id", table_name="hosting_resource_reservations")
    op.drop_table("hosting_resource_reservations")
