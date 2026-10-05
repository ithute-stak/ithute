"""add stable PostgreSQL endpoints

Revision ID: 0093_pg_stable_endpoints
Revises: 0092_pg_rto_slo
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0093_pg_stable_endpoints"
down_revision = "0092_pg_rto_slo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hosting_database_gateways",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
        sa.Column("hostname", sa.String(length=253), nullable=False, unique=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("token_hint", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("agent_version", sa.String(length=64), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('active','disabled')", name="ck_hosting_database_gateway_status"),
    )

    op.create_table(
        "hosting_postgres_endpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_postgres_replication_groups.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("gateway_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_database_gateways.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("hostname", sa.String(length=253), nullable=False, unique=True),
        sa.Column("listen_port", sa.Integer(), nullable=False, server_default="5432"),
        sa.Column("current_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("target_host", sa.String(length=253), nullable=False),
        sa.Column("target_port", sa.Integer(), nullable=False, server_default="5432"),
        sa.Column("generation", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("applied_generation", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("last_routed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("listen_port >= 1 AND listen_port <= 65535", name="ck_pg_endpoint_listen_port"),
        sa.CheckConstraint("target_port >= 1 AND target_port <= 65535", name="ck_pg_endpoint_target_port"),
        sa.CheckConstraint("generation >= 1", name="ck_pg_endpoint_generation"),
        sa.CheckConstraint("applied_generation >= 0", name="ck_pg_endpoint_applied_generation"),
        sa.CheckConstraint("status IN ('pending','ready','degraded')", name="ck_pg_endpoint_status"),
        sa.UniqueConstraint("gateway_id", "listen_port", name="uq_pg_endpoint_gateway_port"),
    )
    op.create_index("ix_pg_endpoints_gateway", "hosting_postgres_endpoints", ["gateway_id"])
    op.create_index("ix_pg_endpoints_current_node", "hosting_postgres_endpoints", ["current_node_id"])


def downgrade() -> None:
    op.drop_index("ix_pg_endpoints_current_node", table_name="hosting_postgres_endpoints")
    op.drop_index("ix_pg_endpoints_gateway", table_name="hosting_postgres_endpoints")
    op.drop_table("hosting_postgres_endpoints")
    op.drop_table("hosting_database_gateways")
