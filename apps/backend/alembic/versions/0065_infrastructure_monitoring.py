"""add infrastructure monitoring history and thresholds

Revision ID: 0065_infrastructure_monitoring
Revises: 0064_infrastructure_server_agent
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0065_infrastructure_monitoring"
down_revision = "0064_infrastructure_server_agent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("infrastructure_servers", sa.Column("cpu_alert_percent", sa.Integer(), nullable=False, server_default="90"))
    op.add_column("infrastructure_servers", sa.Column("memory_alert_percent", sa.Integer(), nullable=False, server_default="90"))
    op.add_column("infrastructure_servers", sa.Column("disk_alert_percent", sa.Integer(), nullable=False, server_default="85"))
    op.add_column("infrastructure_servers", sa.Column("offline_alert_minutes", sa.Integer(), nullable=False, server_default="5"))

    op.create_table(
        "infrastructure_telemetry_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("server_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("infrastructure_servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cpu_percent", sa.Float(), nullable=True),
        sa.Column("memory_percent", sa.Float(), nullable=True),
        sa.Column("disk_percent", sa.Float(), nullable=True),
        sa.Column("load_1m", sa.Float(), nullable=True),
        sa.Column("docker_running", sa.Integer(), nullable=True),
        sa.Column("docker_total", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_infrastructure_telemetry_server_id", "infrastructure_telemetry_snapshots", ["server_id"])
    op.create_index("ix_infrastructure_telemetry_created_at", "infrastructure_telemetry_snapshots", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_infrastructure_telemetry_created_at", table_name="infrastructure_telemetry_snapshots")
    op.drop_index("ix_infrastructure_telemetry_server_id", table_name="infrastructure_telemetry_snapshots")
    op.drop_table("infrastructure_telemetry_snapshots")
    op.drop_column("infrastructure_servers", "offline_alert_minutes")
    op.drop_column("infrastructure_servers", "disk_alert_percent")
    op.drop_column("infrastructure_servers", "memory_alert_percent")
    op.drop_column("infrastructure_servers", "cpu_alert_percent")
