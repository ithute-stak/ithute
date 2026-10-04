"""add managed private network peer registry

Revision ID: 0069_managed_private_network
Revises: 0068_hosting_node_bootstrap
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0069_managed_private_network"
down_revision = "0068_hosting_node_bootstrap"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "infrastructure_wireguard_peers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("server_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("infrastructure_servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("public_key", sa.String(length=128), nullable=False),
        sa.Column("assigned_ipv4", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
        sa.Column("last_handshake_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latest_rx_bytes", sa.Integer(), nullable=True),
        sa.Column("latest_tx_bytes", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("server_id", name="uq_infrastructure_wireguard_server"),
        sa.UniqueConstraint("public_key", name="uq_infrastructure_wireguard_public_key"),
        sa.UniqueConstraint("assigned_ipv4", name="uq_infrastructure_wireguard_ipv4"),
    )
    op.create_index("ix_infrastructure_wireguard_peers_server_id", "infrastructure_wireguard_peers", ["server_id"])
    op.create_index("ix_infrastructure_wireguard_peers_status", "infrastructure_wireguard_peers", ["status"])


def downgrade() -> None:
    op.drop_index("ix_infrastructure_wireguard_peers_status", table_name="infrastructure_wireguard_peers")
    op.drop_index("ix_infrastructure_wireguard_peers_server_id", table_name="infrastructure_wireguard_peers")
    op.drop_table("infrastructure_wireguard_peers")
