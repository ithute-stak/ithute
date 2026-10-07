"""add first-contact relationship graph

Revision ID: 0092_mail_relationships
Revises: 0091_mail_threat_canary
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0092_mail_relationships"
down_revision = "0091_mail_threat_canary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mail_relationships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mailbox_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("peer_address", sa.String(length=320), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False, server_default="new"),
        sa.Column("messages_sent", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("replies_received", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("first_contact_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reply_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mailbox_id"], ["mailboxes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mailbox_id", "peer_address", name="uq_mail_relationship_mailbox_peer"),
    )
    op.create_index("ix_mail_relationships_tenant_id", "mail_relationships", ["tenant_id"])
    op.create_index("ix_mail_relationships_mailbox_id", "mail_relationships", ["mailbox_id"])
    op.create_index("ix_mail_relationships_peer_address", "mail_relationships", ["peer_address"])
    op.create_index("ix_mail_relationships_state", "mail_relationships", ["state"])


def downgrade() -> None:
    op.drop_index("ix_mail_relationships_state", table_name="mail_relationships")
    op.drop_index("ix_mail_relationships_peer_address", table_name="mail_relationships")
    op.drop_index("ix_mail_relationships_mailbox_id", table_name="mail_relationships")
    op.drop_index("ix_mail_relationships_tenant_id", table_name="mail_relationships")
    op.drop_table("mail_relationships")
