"""Continuous Fleet evaluation and persistent alerts.

Revision ID: 0003_fleet_alerts
Revises: 0002_fleet_management
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_fleet_alerts"
down_revision = "0002_fleet_management"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fleet_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alert_key", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("source_id", sa.String(length=80), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vehicle_id", "alert_key", name="uq_fleet_alert_vehicle_key"),
    )
    op.create_index("ix_fleet_alerts_branch_id", "fleet_alerts", ["branch_id"], unique=False)
    op.create_index("ix_fleet_alerts_vehicle_id", "fleet_alerts", ["vehicle_id"], unique=False)
    op.create_index(
        "ix_fleet_alerts_active_branch",
        "fleet_alerts",
        ["branch_id", "resolved_at", "severity"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_fleet_alerts_active_branch", table_name="fleet_alerts")
    op.drop_index("ix_fleet_alerts_vehicle_id", table_name="fleet_alerts")
    op.drop_index("ix_fleet_alerts_branch_id", table_name="fleet_alerts")
    op.drop_table("fleet_alerts")
