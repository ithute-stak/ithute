"""add PostgreSQL RPO policy

Revision ID: 0091_pg_rpo_policy
Revises: 0090_pg_topology_repair
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0091_pg_rpo_policy"
down_revision = "0090_pg_topology_repair"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "hosting_postgres_replication_groups",
        sa.Column("rpo_class", sa.String(length=24), nullable=False, server_default="async"),
    )
    op.add_column(
        "hosting_postgres_replication_groups",
        sa.Column("required_sync_standbys", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "hosting_postgres_replication_groups",
        sa.Column("rpo_healthy", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "hosting_postgres_replication_groups",
        sa.Column("observed_synchronous_commit", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "hosting_postgres_replication_groups",
        sa.Column("observed_sync_standbys", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "hosting_postgres_replication_groups",
        sa.Column("rpo_last_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_pg_replication_group_rpo_class",
        "hosting_postgres_replication_groups",
        "rpo_class IN ('async','sync_flush','sync_apply')",
    )
    op.create_check_constraint(
        "ck_pg_replication_group_required_sync_standbys",
        "hosting_postgres_replication_groups",
        "required_sync_standbys >= 0 AND required_sync_standbys <= 8",
    )

    op.create_table(
        "hosting_postgres_rpo_policy_ops",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_postgres_replication_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("rpo_class", sa.String(length=24), nullable=False),
        sa.Column("required_sync_standbys", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("claim_token", sa.String(length=64), nullable=True),
        sa.Column("failure_message", sa.String(length=2000), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("rpo_class IN ('async','sync_flush','sync_apply')", name="ck_pg_rpo_policy_op_class"),
        sa.CheckConstraint("required_sync_standbys >= 0 AND required_sync_standbys <= 8", name="ck_pg_rpo_policy_op_required"),
        sa.CheckConstraint("status IN ('queued','claimed','succeeded','failed')", name="ck_pg_rpo_policy_op_status"),
    )
    op.create_index("ix_pg_rpo_policy_ops_group", "hosting_postgres_rpo_policy_ops", ["group_id"])
    op.create_index("ix_pg_rpo_policy_ops_node", "hosting_postgres_rpo_policy_ops", ["node_id"])
    op.create_index("ix_pg_rpo_policy_ops_status", "hosting_postgres_rpo_policy_ops", ["status"])


def downgrade() -> None:
    op.drop_index("ix_pg_rpo_policy_ops_status", table_name="hosting_postgres_rpo_policy_ops")
    op.drop_index("ix_pg_rpo_policy_ops_node", table_name="hosting_postgres_rpo_policy_ops")
    op.drop_index("ix_pg_rpo_policy_ops_group", table_name="hosting_postgres_rpo_policy_ops")
    op.drop_table("hosting_postgres_rpo_policy_ops")
    op.drop_constraint("ck_pg_replication_group_required_sync_standbys", "hosting_postgres_replication_groups", type_="check")
    op.drop_constraint("ck_pg_replication_group_rpo_class", "hosting_postgres_replication_groups", type_="check")
    op.drop_column("hosting_postgres_replication_groups", "rpo_last_checked_at")
    op.drop_column("hosting_postgres_replication_groups", "observed_sync_standbys")
    op.drop_column("hosting_postgres_replication_groups", "observed_synchronous_commit")
    op.drop_column("hosting_postgres_replication_groups", "rpo_healthy")
    op.drop_column("hosting_postgres_replication_groups", "required_sync_standbys")
    op.drop_column("hosting_postgres_replication_groups", "rpo_class")
