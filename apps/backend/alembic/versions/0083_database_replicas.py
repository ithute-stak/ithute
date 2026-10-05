"""add hosting database replicas

Revision ID: 0083_database_replicas
Revises: 0082_operation_resource_locks
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0083_database_replicas"
down_revision = "0082_operation_resource_locks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hosting_database_replicas",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("database_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_databases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_nodes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("role", sa.String(length=24), nullable=False, server_default="replica"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="planned"),
        sa.Column("healthy", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("lag_bytes", sa.BigInteger(), nullable=True),
        sa.Column("lag_seconds", sa.Float(), nullable=True),
        sa.Column("last_replayed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("database_id", "node_id", name="uq_hosting_database_replica_database_node"),
        sa.CheckConstraint("role IN ('replica','promoting','primary')", name="ck_hosting_database_replica_role"),
        sa.CheckConstraint("lag_bytes IS NULL OR lag_bytes >= 0", name="ck_hosting_database_replica_lag_bytes"),
        sa.CheckConstraint("lag_seconds IS NULL OR lag_seconds >= 0", name="ck_hosting_database_replica_lag_seconds"),
    )
    op.create_index("ix_hosting_database_replicas_database_id", "hosting_database_replicas", ["database_id"])
    op.create_index("ix_hosting_database_replicas_node_id", "hosting_database_replicas", ["node_id"])
    op.create_index("ix_hosting_database_replicas_status", "hosting_database_replicas", ["status"])


def downgrade() -> None:
    op.drop_index("ix_hosting_database_replicas_status", table_name="hosting_database_replicas")
    op.drop_index("ix_hosting_database_replicas_node_id", table_name="hosting_database_replicas")
    op.drop_index("ix_hosting_database_replicas_database_id", table_name="hosting_database_replicas")
    op.drop_table("hosting_database_replicas")
