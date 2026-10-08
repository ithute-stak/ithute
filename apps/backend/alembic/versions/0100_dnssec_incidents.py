"""Persist DNSSEC monitor state and incident history separately from general domain health.

Revision ID: 0100_dnssec_incidents
Revises: 0099_scheduled_mdn
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0100_dnssec_incidents"
down_revision = "0099_scheduled_mdn"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dnssec_monitor_states",
        sa.Column("domain_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("domains.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="healthy"),
        sa.Column("code", sa.String(length=100), nullable=True),
        sa.Column("failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_dnssec_monitor_states_tenant_id", "dnssec_monitor_states", ["tenant_id"])
    op.create_table(
        "dnssec_incident_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("domain_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("domains.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("severity", sa.String(length=24), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="open"),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("recovered_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_dnssec_incident_history_tenant_id", "dnssec_incident_history", ["tenant_id"])
    op.create_index("ix_dnssec_incident_history_domain_id", "dnssec_incident_history", ["domain_id"])


def downgrade() -> None:
    op.drop_index("ix_dnssec_incident_history_domain_id", table_name="dnssec_incident_history")
    op.drop_index("ix_dnssec_incident_history_tenant_id", table_name="dnssec_incident_history")
    op.drop_table("dnssec_incident_history")
    op.drop_index("ix_dnssec_monitor_states_tenant_id", table_name="dnssec_monitor_states")
    op.drop_table("dnssec_monitor_states")
