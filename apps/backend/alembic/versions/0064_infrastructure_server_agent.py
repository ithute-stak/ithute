"""add infrastructure server agent telemetry

Revision ID: 0064_infrastructure_server_agent
Revises: 0063_infrastructure_servers
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0064_infrastructure_server_agent"
down_revision = "0063_infrastructure_servers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "infrastructure_server_agents",
        sa.Column("server_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("infrastructure_servers.id", ondelete="CASCADE"), primary_key=True, nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("token_hint", sa.String(length=24), nullable=False),
        sa.Column("agent_version", sa.String(length=80), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("os_name", sa.String(length=160), nullable=True),
        sa.Column("kernel_version", sa.String(length=160), nullable=True),
        sa.Column("uptime_seconds", sa.Integer(), nullable=True),
        sa.Column("telemetry_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("capabilities_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("infrastructure_server_agents")
