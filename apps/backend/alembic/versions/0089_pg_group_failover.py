"""add PostgreSQL group failover attempts

Revision ID: 0089_pg_group_failover
Revises: 0088_pg_replication_groups
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0089_pg_group_failover"
down_revision = "0088_pg_replication_groups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hosting_postgres_group_failovers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_postgres_replication_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("standby_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_postgres_replication_standbys.id", ondelete="RESTRICT"), nullable=False),
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
        sa.CheckConstraint("source_node_id <> target_node_id", name="ck_pg_group_failover_distinct_nodes"),
        sa.CheckConstraint(
            "status IN ('requested','fence_claimed','source_fenced','promote_claimed','succeeded','failed')",
            name="ck_pg_group_failover_status",
        ),
    )
    op.create_index("ix_pg_group_failovers_group", "hosting_postgres_group_failovers", ["group_id"])
    op.create_index("ix_pg_group_failovers_source", "hosting_postgres_group_failovers", ["source_node_id"])
    op.create_index("ix_pg_group_failovers_target", "hosting_postgres_group_failovers", ["target_node_id"])
    op.create_index("ix_pg_group_failovers_status", "hosting_postgres_group_failovers", ["status"])

    op.add_column(
        "infrastructure_fence_attempts",
        sa.Column(
            "postgres_group_failover_attempt_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("hosting_postgres_group_failovers.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_infrastructure_fence_attempts_pg_group_failover",
        "infrastructure_fence_attempts",
        ["postgres_group_failover_attempt_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_infrastructure_fence_attempts_pg_group_failover", table_name="infrastructure_fence_attempts")
    op.drop_column("infrastructure_fence_attempts", "postgres_group_failover_attempt_id")
    op.drop_index("ix_pg_group_failovers_status", table_name="hosting_postgres_group_failovers")
    op.drop_index("ix_pg_group_failovers_target", table_name="hosting_postgres_group_failovers")
    op.drop_index("ix_pg_group_failovers_source", table_name="hosting_postgres_group_failovers")
    op.drop_index("ix_pg_group_failovers_group", table_name="hosting_postgres_group_failovers")
    op.drop_table("hosting_postgres_group_failovers")
