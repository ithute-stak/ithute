"""Production hardening and notification delivery audit.

Revision ID: 0008_production_hardening
Revises: 0007_operations_maturity
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_production_hardening"
down_revision = "0007_operations_maturity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fleet_alerts", sa.Column("notification_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("fleet_alerts", sa.Column("last_notification_error", sa.Text(), nullable=True))
    op.alter_column("fleet_alerts", "notification_attempts", server_default=None)


def downgrade() -> None:
    op.drop_column("fleet_alerts", "last_notification_error")
    op.drop_column("fleet_alerts", "notification_attempts")
