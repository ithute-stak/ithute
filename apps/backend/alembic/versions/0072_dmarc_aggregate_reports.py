"""add DMARC aggregate reports

Revision ID: 0072_dmarc_aggregate_reports
Revises: 0071_application_failover
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0072_dmarc_aggregate_reports"
down_revision = "0071_application_failover"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dmarc_aggregate_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("domain_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("domains.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reporter_org", sa.String(length=255), nullable=False),
        sa.Column("reporter_email", sa.String(length=320), nullable=True),
        sa.Column("report_id", sa.String(length=512), nullable=False),
        sa.Column("period_begin", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("policy_domain", sa.String(length=253), nullable=False),
        sa.Column("policy_p", sa.String(length=32), nullable=True),
        sa.Column("policy_sp", sa.String(length=32), nullable=True),
        sa.Column("policy_pct", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("total_messages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("passed_messages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_messages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pass_rate_percent", sa.Float(), nullable=False, server_default="0"),
        sa.Column("parser_engine", sa.String(length=32), nullable=False),
        sa.Column("parser_version", sa.String(length=32), nullable=False, server_default="1"),
        sa.Column("report_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("domain_id", "reporter_org", "report_id", name="uq_dmarc_domain_report"),
    )
    op.create_index("ix_dmarc_aggregate_reports_tenant_id", "dmarc_aggregate_reports", ["tenant_id"])
    op.create_index("ix_dmarc_aggregate_reports_domain_id", "dmarc_aggregate_reports", ["domain_id"])
    op.create_index("ix_dmarc_aggregate_reports_report_sha256", "dmarc_aggregate_reports", ["report_sha256"])

    op.create_table(
        "dmarc_aggregate_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("dmarc_aggregate_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_ip", sa.String(length=64), nullable=False),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("disposition", sa.String(length=32), nullable=True),
        sa.Column("dkim_result", sa.String(length=32), nullable=True),
        sa.Column("spf_result", sa.String(length=32), nullable=True),
        sa.Column("header_from", sa.String(length=253), nullable=True),
        sa.Column("envelope_from", sa.String(length=253), nullable=True),
        sa.Column("dmarc_pass", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_dmarc_aggregate_sources_report_id", "dmarc_aggregate_sources", ["report_id"])
    op.create_index("ix_dmarc_aggregate_sources_source_ip", "dmarc_aggregate_sources", ["source_ip"])


def downgrade() -> None:
    op.drop_index("ix_dmarc_aggregate_sources_source_ip", table_name="dmarc_aggregate_sources")
    op.drop_index("ix_dmarc_aggregate_sources_report_id", table_name="dmarc_aggregate_sources")
    op.drop_table("dmarc_aggregate_sources")
    op.drop_index("ix_dmarc_aggregate_reports_report_sha256", table_name="dmarc_aggregate_reports")
    op.drop_index("ix_dmarc_aggregate_reports_domain_id", table_name="dmarc_aggregate_reports")
    op.drop_index("ix_dmarc_aggregate_reports_tenant_id", table_name="dmarc_aggregate_reports")
    op.drop_table("dmarc_aggregate_reports")
