"""mail retention, dmarc analytics, phishing and automations

Revision ID: 0015_mail_intelligence
Revises: 0014_ithute_operating_ops
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0015_mail_intelligence"
down_revision = "0014_ithute_operating_ops"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mail_retention_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default="2555"),
        sa.Column("legal_hold", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("immutable_archive", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("mailbox_scope_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "name", name="uq_mail_retention_tenant_name"),
    )
    op.create_index("ix_mail_retention_policies_tenant_id", "mail_retention_policies", ["tenant_id"])

    op.create_table(
        "dmarc_aggregate_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("report_id", sa.String(255), nullable=False),
        sa.Column("reporter", sa.String(255), nullable=True),
        sa.Column("period_begin", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_messages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("aligned_messages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_messages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sources_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("raw_summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "report_id", name="uq_dmarc_tenant_report"),
    )
    op.create_index("ix_dmarc_aggregate_reports_domain", "dmarc_aggregate_reports", ["domain"])
    op.create_index("ix_dmarc_tenant_begin", "dmarc_aggregate_reports", ["tenant_id", "period_begin"])

    op.create_table(
        "phishing_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mailbox_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mailboxes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("message_ref", sa.String(512), nullable=False),
        sa.Column("severity", sa.String(40), nullable=False, server_default="medium"),
        sa.Column("finding_type", sa.String(120), nullable=False),
        sa.Column("sender", sa.String(320), nullable=True),
        sa.Column("subject", sa.String(500), nullable=True),
        sa.Column("indicators_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("action_taken", sa.String(120), nullable=True),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_phishing_tenant_created", "phishing_findings", ["tenant_id", "created_at"])

    op.create_table(
        "mail_automation_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("trigger_event", sa.String(160), nullable=False, server_default="mail.received"),
        sa.Column("conditions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("actions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("run_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "name", name="uq_mail_automation_tenant_name"),
    )


def downgrade() -> None:
    for table in ("mail_automation_rules", "phishing_findings", "dmarc_aggregate_reports", "mail_retention_policies"):
        op.drop_table(table)
