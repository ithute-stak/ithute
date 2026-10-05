"""add fenced database failover attempts

Revision ID: 0085_database_failover_attempts
Revises: 0084_hosting_agent_capabilities
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0085_database_failover_attempts"
down_revision = "0084_hosting_agent_capabilities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hosting_database_failover_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("database_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_databases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("replica_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_database_replicas.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("target_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="requested"),
        sa.Column("source_fence_token", sa.String(length=64), nullable=True),
        sa.Column("target_promote_token", sa.String(length=64), nullable=True),
        sa.Column("source_fenced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_message", sa.String(length=2000), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("source_node_id <> target_node_id", name="ck_hosting_database_failover_distinct_nodes"),
        sa.CheckConstraint(
            "status IN ('requested','fence_claimed','source_fenced','promote_claimed','succeeded','failed')",
            name="ck_hosting_database_failover_status",
        ),
    )
    op.create_index("ix_hosting_database_failover_database_id", "hosting_database_failover_attempts", ["database_id"])
    op.create_index("ix_hosting_database_failover_source_node_id", "hosting_database_failover_attempts", ["source_node_id"])
    op.create_index("ix_hosting_database_failover_target_node_id", "hosting_database_failover_attempts", ["target_node_id"])
    op.create_index("ix_hosting_database_failover_status", "hosting_database_failover_attempts", ["status"])


def downgrade() -> None:
    op.drop_index("ix_hosting_database_failover_status", table_name="hosting_database_failover_attempts")
    op.drop_index("ix_hosting_database_failover_target_node_id", table_name="hosting_database_failover_attempts")
    op.drop_index("ix_hosting_database_failover_source_node_id", table_name="hosting_database_failover_attempts")
    op.drop_index("ix_hosting_database_failover_database_id", table_name="hosting_database_failover_attempts")
    op.drop_table("hosting_database_failover_attempts")
