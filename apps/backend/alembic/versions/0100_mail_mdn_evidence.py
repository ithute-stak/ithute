"""Store mailbox-scoped MDN evidence, without asserting that mail was read.

Revision ID: 0100_mail_mdn_evidence
Revises: 0099_scheduled_mdn
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0100_mail_mdn_evidence"
down_revision = "0099_scheduled_mdn"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mail_read_receipt_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("mailbox_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_message_id", sa.String(998), nullable=False),
        sa.Column("recipient", sa.String(320), nullable=False),
        sa.Column("disposition", sa.String(32), nullable=False),
        sa.Column("evidence_status", sa.String(48), nullable=False),
        sa.Column("evidence_key", sa.String(128), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("mailbox_id", "evidence_key", name="uq_mail_mdn_mailbox_key"),
    )
    op.create_index("ix_mail_mdn_message", "mail_read_receipt_evidence", ["mailbox_id", "original_message_id"])
    op.create_index("ix_mail_read_receipt_evidence_mailbox_id", "mail_read_receipt_evidence", ["mailbox_id"])


def downgrade():
    op.drop_index("ix_mail_read_receipt_evidence_mailbox_id", table_name="mail_read_receipt_evidence")
    op.drop_index("ix_mail_mdn_message", table_name="mail_read_receipt_evidence")
    op.drop_table("mail_read_receipt_evidence")
