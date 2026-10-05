"""add PostgreSQL replication groups

Revision ID: 0088_pg_replication_groups
Revises: 0087_pg_wal_telemetry
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0088_pg_replication_groups"
down_revision = "0087_pg_wal_telemetry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hosting_postgres_replication_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("primary_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('active','maintenance','failed')", name="ck_pg_replication_group_status"),
    )
    op.create_index("ix_pg_replication_groups_primary_node", "hosting_postgres_replication_groups", ["primary_node_id"])

    op.create_table(
        "hosting_postgres_replication_members",
        sa.Column("group_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_postgres_replication_groups.id", ondelete="CASCADE"), primary_key=True, nullable=False),
        sa.Column("database_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_databases.id", ondelete="CASCADE"), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("database_id", name="uq_pg_replication_member_database"),
    )
    op.create_index("ix_pg_replication_members_database", "hosting_postgres_replication_members", ["database_id"])

    op.create_table(
        "hosting_postgres_replication_standbys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_postgres_replication_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="planned"),
        sa.Column("healthy", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("receive_lsn", sa.String(length=64), nullable=True),
        sa.Column("replay_lsn", sa.String(length=64), nullable=True),
        sa.Column("replay_backlog_bytes", sa.BigInteger(), nullable=True),
        sa.Column("replay_age_seconds", sa.Float(), nullable=True),
        sa.Column("in_recovery", sa.Boolean(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("telemetry_error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("group_id", "node_id", name="uq_pg_replication_standby_group_node"),
        sa.CheckConstraint("status IN ('planned','streaming','ready','failed')", name="ck_pg_replication_standby_status"),
        sa.CheckConstraint("replay_backlog_bytes IS NULL OR replay_backlog_bytes >= 0", name="ck_pg_replication_standby_backlog"),
    )
    op.create_index("ix_pg_replication_standbys_group", "hosting_postgres_replication_standbys", ["group_id"])
    op.create_index("ix_pg_replication_standbys_node", "hosting_postgres_replication_standbys", ["node_id"])


def downgrade() -> None:
    op.drop_index("ix_pg_replication_standbys_node", table_name="hosting_postgres_replication_standbys")
    op.drop_index("ix_pg_replication_standbys_group", table_name="hosting_postgres_replication_standbys")
    op.drop_table("hosting_postgres_replication_standbys")
    op.drop_index("ix_pg_replication_members_database", table_name="hosting_postgres_replication_members")
    op.drop_table("hosting_postgres_replication_members")
    op.drop_index("ix_pg_replication_groups_primary_node", table_name="hosting_postgres_replication_groups")
    op.drop_table("hosting_postgres_replication_groups")
