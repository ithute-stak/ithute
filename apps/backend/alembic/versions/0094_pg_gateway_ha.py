"""add HA PostgreSQL gateway pools

Revision ID: 0094_pg_gateway_ha
Revises: 0093_pg_stable_endpoints
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0094_pg_gateway_ha"
down_revision = "0093_pg_stable_endpoints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hosting_database_gateways", sa.Column("advertise_ipv4", sa.String(length=45), nullable=True))
    op.add_column("hosting_database_gateways", sa.Column("advertise_ipv6", sa.String(length=64), nullable=True))
    op.create_table(
        "hosting_database_gateway_pools",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
        sa.Column("frontend_hostname", sa.String(length=253), nullable=False, unique=True),
        sa.Column("dns_domain_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("domains.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("required_ready_gateways", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("required_ready_gateways >= 1 AND required_ready_gateways <= 8", name="ck_db_gateway_pool_required_ready"),
        sa.CheckConstraint("status IN ('active','degraded','disabled')", name="ck_db_gateway_pool_status"),
    )
    op.create_table(
        "hosting_database_gateway_pool_members",
        sa.Column("pool_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_database_gateway_pools.id", ondelete="CASCADE"), primary_key=True, nullable=False),
        sa.Column("gateway_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_database_gateways.id", ondelete="CASCADE"), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_db_gateway_pool_members_gateway", "hosting_database_gateway_pool_members", ["gateway_id"])

    op.add_column(
        "hosting_postgres_endpoints",
        sa.Column("gateway_pool_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_database_gateway_pools.id", ondelete="RESTRICT"), nullable=True),
    )
    op.add_column(
        "hosting_postgres_endpoints",
        sa.Column("required_gateway_acks", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("ix_pg_endpoints_gateway_pool", "hosting_postgres_endpoints", ["gateway_pool_id"])
    op.create_check_constraint(
        "ck_pg_endpoint_required_gateway_acks",
        "hosting_postgres_endpoints",
        "required_gateway_acks >= 1 AND required_gateway_acks <= 8",
    )

    op.create_table(
        "hosting_postgres_endpoint_gateway_acks",
        sa.Column("endpoint_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_postgres_endpoints.id", ondelete="CASCADE"), primary_key=True, nullable=False),
        sa.Column("gateway_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_database_gateways.id", ondelete="CASCADE"), primary_key=True, nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("generation >= 1", name="ck_pg_endpoint_gateway_ack_generation"),
    )
    op.create_index("ix_pg_endpoint_gateway_acks_gateway", "hosting_postgres_endpoint_gateway_acks", ["gateway_id"])


def downgrade() -> None:
    op.drop_index("ix_pg_endpoint_gateway_acks_gateway", table_name="hosting_postgres_endpoint_gateway_acks")
    op.drop_table("hosting_postgres_endpoint_gateway_acks")
    op.drop_constraint("ck_pg_endpoint_required_gateway_acks", "hosting_postgres_endpoints", type_="check")
    op.drop_index("ix_pg_endpoints_gateway_pool", table_name="hosting_postgres_endpoints")
    op.drop_column("hosting_postgres_endpoints", "required_gateway_acks")
    op.drop_column("hosting_postgres_endpoints", "gateway_pool_id")
    op.drop_index("ix_db_gateway_pool_members_gateway", table_name="hosting_database_gateway_pool_members")
    op.drop_table("hosting_database_gateway_pool_members")
    op.drop_table("hosting_database_gateway_pools")
    op.drop_column("hosting_database_gateways", "advertise_ipv6")
    op.drop_column("hosting_database_gateways", "advertise_ipv4")
