"""add mail threat shadow predictions

Revision ID: 0090_mail_threat_shadow
Revises: 0089_mail_threat_models
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0090_mail_threat_shadow"
down_revision = "0089_mail_threat_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mail_threat_shadow_predictions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mailbox_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mail_threat_model_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_ref", sa.String(512), nullable=False),
        sa.Column("probabilities_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("baseline_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("feature_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("verified_label", sa.String(32), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("model_id", "mailbox_id", "message_ref", name="uq_mail_threat_shadow_model_mailbox_message"),
    )
    op.create_index("ix_mail_threat_shadow_tenant", "mail_threat_shadow_predictions", ["tenant_id"])
    op.create_index("ix_mail_threat_shadow_model", "mail_threat_shadow_predictions", ["model_id"])
    op.create_index("ix_mail_threat_shadow_created", "mail_threat_shadow_predictions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_mail_threat_shadow_created", table_name="mail_threat_shadow_predictions")
    op.drop_index("ix_mail_threat_shadow_model", table_name="mail_threat_shadow_predictions")
    op.drop_index("ix_mail_threat_shadow_tenant", table_name="mail_threat_shadow_predictions")
    op.drop_table("mail_threat_shadow_predictions")
