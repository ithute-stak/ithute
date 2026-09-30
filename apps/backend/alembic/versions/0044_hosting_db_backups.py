"""add managed hosting database backups

Revision ID: 0044_hosting_db_backups
Revises: 0043_hosting_project_ops
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0044_hosting_db_backups"
down_revision = "0043_hosting_project_ops"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hosting_database_backups",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("database_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_backup_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("operation", sa.String(length=24), server_default="backup", nullable=False),
        sa.Column("status", sa.String(length=24), server_default="queued", nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("operation IN ('backup','restore')", name="ck_hosting_database_backup_operation"),
        sa.CheckConstraint("status IN ('queued','claimed','succeeded','failed')", name="ck_hosting_database_backup_status"),
        sa.CheckConstraint("(operation = 'backup' AND source_backup_id IS NULL) OR (operation = 'restore' AND source_backup_id IS NOT NULL)", name="ck_hosting_database_backup_source"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["database_id"], ["hosting_databases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_id"], ["hosting_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_backup_id"], ["hosting_database_backups.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_hosting_database_backups_tenant_id", "hosting_database_backups", ["tenant_id"])
    op.create_index("ix_hosting_database_backups_database_id", "hosting_database_backups", ["database_id"])
    op.create_index("ix_hosting_database_backups_node_id", "hosting_database_backups", ["node_id"])
    op.create_index("ix_hosting_database_backups_source_backup_id", "hosting_database_backups", ["source_backup_id"])
    op.create_index("ix_hosting_database_backups_status", "hosting_database_backups", ["status"])


def downgrade() -> None:
    op.drop_table("hosting_database_backups")
