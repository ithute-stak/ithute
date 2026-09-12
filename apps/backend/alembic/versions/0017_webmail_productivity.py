"""mailbox-owned Webmail productivity rules

Revision ID: 0017_webmail_productivity
Revises: 0016_webmail_connected_accounts
Create Date: 2026-09-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0017_webmail_productivity"
down_revision = "0016_webmail_connected_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mailbox_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("mailbox_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connected_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("connected_mail_accounts.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("conditions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("actions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("run_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("mailbox_id", "name", name="uq_mailbox_rule_name"),
    )
    op.create_index("ix_mailbox_rules_mailbox_id", "mailbox_rules", ["mailbox_id"])
    op.create_index("ix_mailbox_rules_connected_account_id", "mailbox_rules", ["connected_account_id"])
    op.create_index("ix_mailbox_rule_mailbox_enabled", "mailbox_rules", ["mailbox_id", "enabled"])


def downgrade() -> None:
    op.drop_table("mailbox_rules")
