"""add hosting project runtime operations queue

Revision ID: 0043_hosting_project_ops
Revises: 0042_zip_quarantine
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0043_hosting_project_ops"
down_revision = "0042_zip_quarantine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hosting_project_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="queued", nullable=False),
        sa.Column("requested_lines", sa.Integer(), nullable=True),
        sa.Column("output_text", sa.Text(), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("operation IN ('restart','logs')", name="ck_hosting_project_operation_kind"),
        sa.CheckConstraint("status IN ('queued','claimed','succeeded','failed')", name="ck_hosting_project_operation_status"),
        sa.CheckConstraint("requested_lines IS NULL OR (requested_lines >= 1 AND requested_lines <= 2000)", name="ck_hosting_project_operation_lines"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["hosting_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_id"], ["hosting_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_hosting_project_operations_tenant_id", "hosting_project_operations", ["tenant_id"])
    op.create_index("ix_hosting_project_operations_project_id", "hosting_project_operations", ["project_id"])
    op.create_index("ix_hosting_project_operations_node_id", "hosting_project_operations", ["node_id"])
    op.create_index("ix_hosting_project_operations_status", "hosting_project_operations", ["status"])


def downgrade() -> None:
    op.drop_table("hosting_project_operations")
