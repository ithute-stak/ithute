"""add secure hosting node bootstrap tokens

Revision ID: 0068_hosting_node_bootstrap
Revises: 0067_private_origin_handoff
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0068_hosting_node_bootstrap"
down_revision = "0067_private_origin_handoff"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hosting_node_agents", sa.Column("origin_bind_ip", sa.String(length=64), nullable=True))
    op.create_table(
        "hosting_node_bootstraps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("token_hint", sa.String(length=24), nullable=False),
        sa.Column("origin_bind_ip", sa.String(length=64), nullable=True),
        sa.Column("edge_origin_cidrs", sa.Text(), nullable=False, server_default=""),
        sa.Column("backup_remote", sa.String(length=1000), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_hosting_node_bootstraps_node_id", "hosting_node_bootstraps", ["node_id"])


def downgrade() -> None:
    op.drop_index("ix_hosting_node_bootstraps_node_id", table_name="hosting_node_bootstraps")
    op.drop_table("hosting_node_bootstraps")
    op.drop_column("hosting_node_agents", "origin_bind_ip")
