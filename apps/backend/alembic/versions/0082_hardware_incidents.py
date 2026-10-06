"""hardware risk incidents

Revision ID: 0082_hardware_incidents
Revises: 0081_hardware_operations
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0082_hardware_incidents"
down_revision = "0081_hardware_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hardware_incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("server_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("infrastructure_servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("latest_snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hardware_telemetry_snapshots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(length=64), nullable=False, server_default="hardware_risk"),
        sa.Column("severity", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="open"),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("predictive_state", sa.String(length=24), nullable=False, server_default="learning"),
        sa.Column("predictive_risk_score", sa.Integer(), nullable=True),
        sa.Column("health_status", sa.String(length=24), nullable=False),
        sa.Column("notification_suppressed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    for name, columns in (
        ("ix_hw_incident_server_id", ["server_id"]),
        ("ix_hw_incident_latest_snapshot_id", ["latest_snapshot_id"]),
        ("ix_hw_incident_kind", ["kind"]),
        ("ix_hw_incident_severity", ["severity"]),
        ("ix_hw_incident_status", ["status"]),
        ("ix_hw_incident_opened_at", ["opened_at"]),
        ("ix_hw_incident_last_seen_at", ["last_seen_at"]),
        ("ix_hw_incident_resolved_at", ["resolved_at"]),
    ):
        op.create_index(name, "hardware_incidents", columns)


def downgrade() -> None:
    for name in (
        "ix_hw_incident_resolved_at",
        "ix_hw_incident_last_seen_at",
        "ix_hw_incident_opened_at",
        "ix_hw_incident_status",
        "ix_hw_incident_severity",
        "ix_hw_incident_kind",
        "ix_hw_incident_latest_snapshot_id",
        "ix_hw_incident_server_id",
    ):
        op.drop_index(name, table_name="hardware_incidents")
    op.drop_table("hardware_incidents")
