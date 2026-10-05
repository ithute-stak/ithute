"""add policy-controlled private network grants

Revision ID: 0076_network_grants
Revises: 0075_customer_profitability
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0076_network_grants"
down_revision = "0075_customer_profitability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "infrastructure_network_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_server_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("infrastructure_servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_server_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("infrastructure_servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("protocol", sa.String(length=8), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("service", sa.String(length=80), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "source_server_id",
            "target_server_id",
            "protocol",
            "port",
            name="uq_infrastructure_network_grant_flow",
        ),
    )
    op.create_index("ix_infrastructure_network_grants_source_server_id", "infrastructure_network_grants", ["source_server_id"])
    op.create_index("ix_infrastructure_network_grants_target_server_id", "infrastructure_network_grants", ["target_server_id"])
    op.create_index("ix_infrastructure_network_grants_enabled", "infrastructure_network_grants", ["enabled"])


def downgrade() -> None:
    op.drop_index("ix_infrastructure_network_grants_enabled", table_name="infrastructure_network_grants")
    op.drop_index("ix_infrastructure_network_grants_target_server_id", table_name="infrastructure_network_grants")
    op.drop_index("ix_infrastructure_network_grants_source_server_id", table_name="infrastructure_network_grants")
    op.drop_table("infrastructure_network_grants")
