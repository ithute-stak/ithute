"""add infrastructure agent commands and container drift snapshots

Revision ID: 0072_infrastructure_agent_ops
Revises: 0071_application_failover
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0072_infrastructure_agent_ops"
down_revision = "0071_application_failover"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "infrastructure_agent_commands",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("server_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("infrastructure_servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("result_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_infrastructure_agent_commands_server_id", "infrastructure_agent_commands", ["server_id"])
    op.create_index("ix_infrastructure_agent_commands_kind", "infrastructure_agent_commands", ["kind"])
    op.create_index("ix_infrastructure_agent_commands_status", "infrastructure_agent_commands", ["status"])

    op.create_table(
        "infrastructure_container_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("server_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("infrastructure_servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("containers_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("expected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("running_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("missing_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unexpected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("drift_status", sa.String(length=24), nullable=False, server_default="unknown"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_infrastructure_container_snapshots_server_id", "infrastructure_container_snapshots", ["server_id"])
    op.create_index("ix_infrastructure_container_snapshots_drift_status", "infrastructure_container_snapshots", ["drift_status"])
    op.create_index("ix_infrastructure_container_snapshots_created_at", "infrastructure_container_snapshots", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_infrastructure_container_snapshots_created_at", table_name="infrastructure_container_snapshots")
    op.drop_index("ix_infrastructure_container_snapshots_drift_status", table_name="infrastructure_container_snapshots")
    op.drop_index("ix_infrastructure_container_snapshots_server_id", table_name="infrastructure_container_snapshots")
    op.drop_table("infrastructure_container_snapshots")
    op.drop_index("ix_infrastructure_agent_commands_status", table_name="infrastructure_agent_commands")
    op.drop_index("ix_infrastructure_agent_commands_kind", table_name="infrastructure_agent_commands")
    op.drop_index("ix_infrastructure_agent_commands_server_id", table_name="infrastructure_agent_commands")
    op.drop_table("infrastructure_agent_commands")
