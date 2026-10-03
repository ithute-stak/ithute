"""domain health monitoring state

Revision ID: 0061_domain_health_monitor
Revises: 0060_mail_node_backup_policy
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0061_domain_health_monitor"
down_revision = "0060_mail_node_backup_policy"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "domain_health_monitor_states",
        sa.Column("domain_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("domains.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("last_status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("last_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failing_checks_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("first_unhealthy_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recovered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_domain_health_monitor_states_tenant_id", "domain_health_monitor_states", ["tenant_id"])
    op.create_index("ix_domain_health_monitor_states_last_status", "domain_health_monitor_states", ["last_status"])


def downgrade():
    op.drop_index("ix_domain_health_monitor_states_last_status", table_name="domain_health_monitor_states")
    op.drop_index("ix_domain_health_monitor_states_tenant_id", table_name="domain_health_monitor_states")
    op.drop_table("domain_health_monitor_states")
