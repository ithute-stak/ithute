"""persistent connected mail accounts, snooze and scheduled delivery

Revision ID: 0016_webmail_connected_accounts
Revises: 0015_mail_intelligence
Create Date: 2026-09-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0016_webmail_connected_accounts"
down_revision = "0015_mail_intelligence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "connected_mail_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mailbox_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False, server_default="custom"),
        sa.Column("address", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("auth_type", sa.String(32), nullable=False, server_default="password"),
        sa.Column("credential_encrypted", sa.Text(), nullable=True),
        sa.Column("oauth_refresh_token_encrypted", sa.Text(), nullable=True),
        sa.Column("oauth_access_token_encrypted", sa.Text(), nullable=True),
        sa.Column("oauth_access_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("oauth_scopes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("imap_host", sa.String(253), nullable=False),
        sa.Column("imap_port", sa.Integer(), nullable=False, server_default="993"),
        sa.Column("imap_security", sa.String(20), nullable=False, server_default="ssl"),
        sa.Column("smtp_host", sa.String(253), nullable=False),
        sa.Column("smtp_port", sa.Integer(), nullable=False, server_default="587"),
        sa.Column("smtp_security", sa.String(20), nullable=False, server_default="starttls"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("sync_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("mailbox_id", "address", name="uq_connected_mail_account_mailbox_address"),
    )
    op.create_index("ix_connected_mail_accounts_tenant_id", "connected_mail_accounts", ["tenant_id"])
    op.create_index("ix_connected_mail_accounts_mailbox_id", "connected_mail_accounts", ["mailbox_id"])
    op.create_index("ix_connected_mail_account_mailbox_status", "connected_mail_accounts", ["mailbox_id", "status"])

    op.create_table(
        "mail_snoozes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("mailbox_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connected_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("connected_mail_accounts.id", ondelete="CASCADE"), nullable=True),
        sa.Column("source_key", sa.String(80), nullable=False, server_default="hosted"),
        sa.Column("folder", sa.String(255), nullable=False, server_default="INBOX"),
        sa.Column("message_uid", sa.String(128), nullable=False),
        sa.Column("message_id", sa.String(998), nullable=True),
        sa.Column("wake_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("mailbox_id", "source_key", "folder", "message_uid", name="uq_mail_snooze_source_message"),
    )
    op.create_index("ix_mail_snoozes_mailbox_id", "mail_snoozes", ["mailbox_id"])
    op.create_index("ix_mail_snoozes_connected_account_id", "mail_snoozes", ["connected_account_id"])
    op.create_index("ix_mail_snoozes_wake_at", "mail_snoozes", ["wake_at"])
    op.create_index("ix_mail_snooze_mailbox_wake", "mail_snoozes", ["mailbox_id", "wake_at"])

    op.create_table(
        "scheduled_mail",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("mailbox_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connected_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("connected_mail_accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_key", sa.String(80), nullable=False, server_default="hosted"),
        sa.Column("to_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("cc_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("bcc_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("subject", sa.String(998), nullable=False, server_default=""),
        sa.Column("body_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("body_html", sa.Text(), nullable=False, server_default=""),
        sa.Column("attachments_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("auth_secret_encrypted", sa.Text(), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_scheduled_mail_mailbox_id", "scheduled_mail", ["mailbox_id"])
    op.create_index("ix_scheduled_mail_connected_account_id", "scheduled_mail", ["connected_account_id"])
    op.create_index("ix_scheduled_mail_scheduled_at", "scheduled_mail", ["scheduled_at"])
    op.create_index("ix_scheduled_mail_status", "scheduled_mail", ["status"])
    op.create_index("ix_scheduled_mail_due", "scheduled_mail", ["status", "scheduled_at"])
    op.create_index("ix_scheduled_mail_mailbox_created", "scheduled_mail", ["mailbox_id", "created_at"])


def downgrade() -> None:
    op.drop_table("scheduled_mail")
    op.drop_table("mail_snoozes")
    op.drop_table("connected_mail_accounts")
