"""add hosting agent capability reporting

Revision ID: 0084_hosting_agent_capabilities
Revises: 0083_database_replicas
"""

from alembic import op
import sqlalchemy as sa

revision = "0084_hosting_agent_capabilities"
down_revision = "0083_database_replicas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "hosting_node_agents",
        sa.Column("capabilities_json", sa.Text(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("hosting_node_agents", "capabilities_json")
