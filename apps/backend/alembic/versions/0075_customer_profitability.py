"""add customer profitability and infrastructure cost allocation

Revision ID: 0075_customer_profitability
Revises: 0074_metered_overages
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0075_customer_profitability"
down_revision = "0074_metered_overages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "infrastructure_commercial_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("server_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("infrastructure_servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="LSL"),
        sa.Column("provider_cost_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("backup_cost_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bandwidth_cost_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("other_cost_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_cpu_millicores", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_memory_mb", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_storage_mb", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("included_bandwidth_gb", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("target_margin_bps", sa.Integer(), nullable=False, server_default="3000"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("server_id", name="uq_infrastructure_commercial_server"),
    )
    op.create_index("ix_infrastructure_commercial_profiles_server_id", "infrastructure_commercial_profiles", ["server_id"])

    op.create_table(
        "tenant_infrastructure_allocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("server_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("infrastructure_servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("allocation_weight", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("cpu_millicores", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("memory_mb", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("storage_mb", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bandwidth_gb", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "server_id", name="uq_tenant_infrastructure_allocation"),
    )
    op.create_index("ix_tenant_infrastructure_allocations_tenant_id", "tenant_infrastructure_allocations", ["tenant_id"])
    op.create_index("ix_tenant_infrastructure_allocations_server_id", "tenant_infrastructure_allocations", ["server_id"])
    op.create_index("ix_tenant_infrastructure_allocations_active", "tenant_infrastructure_allocations", ["active"])


def downgrade() -> None:
    op.drop_index("ix_tenant_infrastructure_allocations_active", table_name="tenant_infrastructure_allocations")
    op.drop_index("ix_tenant_infrastructure_allocations_server_id", table_name="tenant_infrastructure_allocations")
    op.drop_index("ix_tenant_infrastructure_allocations_tenant_id", table_name="tenant_infrastructure_allocations")
    op.drop_table("tenant_infrastructure_allocations")
    op.drop_index("ix_infrastructure_commercial_profiles_server_id", table_name="infrastructure_commercial_profiles")
    op.drop_table("infrastructure_commercial_profiles")
