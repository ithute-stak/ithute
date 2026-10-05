"""hardware intelligence telemetry

Revision ID: 0079_hardware_intelligence
Revises: 0078_network_observations
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0079_hardware_intelligence"
down_revision = "0078_network_observations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hardware_telemetry_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("server_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("infrastructure_servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("nonce", sa.String(length=32), nullable=False),
        sa.Column("signature", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("health_score", sa.Integer(), nullable=False),
        sa.Column("health_status", sa.String(length=24), nullable=False),
        sa.Column("temperature_celsius", sa.Float(), nullable=True),
        sa.Column("memory_pressure_avg10", sa.Float(), nullable=True),
        sa.Column("io_pressure_avg10", sa.Float(), nullable=True),
        sa.Column("filesystem_used_percent", sa.Float(), nullable=True),
        sa.Column("storage_warning_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("nonce", name="uq_hardware_telemetry_nonce"),
    )
    op.create_index("ix_hardware_telemetry_server_id", "hardware_telemetry_snapshots", ["server_id"])
    op.create_index("ix_hardware_telemetry_agent_id", "hardware_telemetry_snapshots", ["agent_id"])
    op.create_index("ix_hardware_telemetry_issued_at", "hardware_telemetry_snapshots", ["issued_at"])
    op.create_index("ix_hardware_telemetry_health_status", "hardware_telemetry_snapshots", ["health_status"])
    op.create_index("ix_hardware_telemetry_created_at", "hardware_telemetry_snapshots", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_hardware_telemetry_created_at", table_name="hardware_telemetry_snapshots")
    op.drop_index("ix_hardware_telemetry_health_status", table_name="hardware_telemetry_snapshots")
    op.drop_index("ix_hardware_telemetry_issued_at", table_name="hardware_telemetry_snapshots")
    op.drop_index("ix_hardware_telemetry_agent_id", table_name="hardware_telemetry_snapshots")
    op.drop_index("ix_hardware_telemetry_server_id", table_name="hardware_telemetry_snapshots")
    op.drop_table("hardware_telemetry_snapshots")
