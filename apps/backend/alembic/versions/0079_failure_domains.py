"""add infrastructure failure domains

Revision ID: 0079_failure_domains
Revises: 0078_network_observations
"""

from alembic import op
import sqlalchemy as sa

revision = "0079_failure_domains"
down_revision = "0078_network_observations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("infrastructure_servers", sa.Column("datacenter", sa.String(length=120), nullable=True))
    op.add_column("infrastructure_servers", sa.Column("physical_host", sa.String(length=160), nullable=True))
    op.add_column("infrastructure_servers", sa.Column("network_segment", sa.String(length=160), nullable=True))
    op.create_index("ix_infrastructure_servers_provider", "infrastructure_servers", ["provider"])
    op.create_index("ix_infrastructure_servers_region", "infrastructure_servers", ["region"])
    op.create_index("ix_infrastructure_servers_datacenter", "infrastructure_servers", ["datacenter"])
    op.create_index("ix_infrastructure_servers_physical_host", "infrastructure_servers", ["physical_host"])
    op.create_index("ix_infrastructure_servers_network_segment", "infrastructure_servers", ["network_segment"])


def downgrade() -> None:
    op.drop_index("ix_infrastructure_servers_network_segment", table_name="infrastructure_servers")
    op.drop_index("ix_infrastructure_servers_physical_host", table_name="infrastructure_servers")
    op.drop_index("ix_infrastructure_servers_datacenter", table_name="infrastructure_servers")
    op.drop_index("ix_infrastructure_servers_region", table_name="infrastructure_servers")
    op.drop_index("ix_infrastructure_servers_provider", table_name="infrastructure_servers")
    op.drop_column("infrastructure_servers", "network_segment")
    op.drop_column("infrastructure_servers", "physical_host")
    op.drop_column("infrastructure_servers", "datacenter")
