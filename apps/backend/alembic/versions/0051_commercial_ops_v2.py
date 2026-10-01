"""commercial operations v2

Revision ID: 0051_commercial_ops_v2
Revises: 0050_effective_plan
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0051_commercial_ops_v2"
down_revision = "0050_effective_plan"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "billing_contracts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("billing_interval", sa.String(16), nullable=False, server_default="annual"),
        sa.Column("auto_renew", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("invoice_lead_days", sa.Integer(), nullable=False, server_default="14"),
        sa.Column("grace_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("discount_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("credit_balance_minor", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("setup_fee_applied", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("next_invoice_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", name="uq_billing_contract_tenant"),
    )
    op.create_index("ix_billing_contracts_tenant_id", "billing_contracts", ["tenant_id"])
    op.create_index("ix_billing_contracts_next_invoice_at", "billing_contracts", ["next_invoice_at"])

    op.create_table(
        "uptime_monitors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("expected_status", sa.Integer(), nullable=False, server_default="200"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_status", sa.String(24), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_response_ms", sa.Integer(), nullable=True),
        sa.Column("last_http_status", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_uptime_monitors_tenant_id", "uptime_monitors", ["tenant_id"])
    op.create_index("ix_uptime_monitors_enabled", "uptime_monitors", ["enabled"])

    op.create_table(
        "uptime_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("monitor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("uptime_monitors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("response_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_uptime_checks_monitor_id", "uptime_checks", ["monitor_id"])
    op.create_index("ix_uptime_checks_checked_at", "uptime_checks", ["checked_at"])


def downgrade():
    op.drop_index("ix_uptime_checks_checked_at", table_name="uptime_checks")
    op.drop_index("ix_uptime_checks_monitor_id", table_name="uptime_checks")
    op.drop_table("uptime_checks")
    op.drop_index("ix_uptime_monitors_enabled", table_name="uptime_monitors")
    op.drop_index("ix_uptime_monitors_tenant_id", table_name="uptime_monitors")
    op.drop_table("uptime_monitors")
    op.drop_index("ix_billing_contracts_next_invoice_at", table_name="billing_contracts")
    op.drop_index("ix_billing_contracts_tenant_id", table_name="billing_contracts")
    op.drop_table("billing_contracts")
