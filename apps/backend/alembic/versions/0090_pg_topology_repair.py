"""add PostgreSQL topology repair jobs

Revision ID: 0090_pg_topology_repair
Revises: 0089_pg_group_failover
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0090_pg_topology_repair"
down_revision = "0089_pg_group_failover"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hosting_postgres_topology_repairs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_postgres_replication_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("method", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("claim_token", sa.String(length=64), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_message", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("node_id <> source_node_id", name="ck_pg_topology_repair_distinct_nodes"),
        sa.CheckConstraint("method IN ('rewind','basebackup')", name="ck_pg_topology_repair_method"),
        sa.CheckConstraint("status IN ('queued','claimed','succeeded','failed')", name="ck_pg_topology_repair_status"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_pg_topology_repair_attempt_count"),
        sa.UniqueConstraint("group_id", "node_id", "status", name="uq_pg_topology_repair_group_node_status"),
    )
    op.create_index("ix_pg_topology_repairs_group", "hosting_postgres_topology_repairs", ["group_id"])
    op.create_index("ix_pg_topology_repairs_node", "hosting_postgres_topology_repairs", ["node_id"])
    op.create_index("ix_pg_topology_repairs_status", "hosting_postgres_topology_repairs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_pg_topology_repairs_status", table_name="hosting_postgres_topology_repairs")
    op.drop_index("ix_pg_topology_repairs_node", table_name="hosting_postgres_topology_repairs")
    op.drop_index("ix_pg_topology_repairs_group", table_name="hosting_postgres_topology_repairs")
    op.drop_table("hosting_postgres_topology_repairs")
