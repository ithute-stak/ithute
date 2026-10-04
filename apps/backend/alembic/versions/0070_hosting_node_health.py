"""add hosting node self-healing state

Revision ID: 0070_hosting_node_health
Revises: 0069_managed_private_network
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0070_hosting_node_health"
down_revision = "0069_managed_private_network"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hosting_node_health_states",
        sa.Column("node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_nodes.id", ondelete="CASCADE"), primary_key=True, nullable=False),
        sa.Column("automation_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("health_status", sa.String(length=24), nullable=False, server_default="unknown"),
        sa.Column("healthy_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unhealthy_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_transition_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_transition", sa.String(length=32), nullable=True),
        sa.Column("last_reason", sa.Text(), nullable=True),
    )
    op.create_index("ix_hosting_node_health_states_health_status", "hosting_node_health_states", ["health_status"])


def downgrade() -> None:
    op.drop_index("ix_hosting_node_health_states_health_status", table_name="hosting_node_health_states")
    op.drop_table("hosting_node_health_states")
