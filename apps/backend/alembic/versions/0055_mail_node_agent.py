"""mail node agent and command queue

Revision ID: 0055_mail_node_agent
Revises: 0054_mail_node_infrastructure
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0055_mail_node_agent"
down_revision = "0054_mail_node_infrastructure"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mail_node_agents",
        sa.Column("node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mail_nodes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("token_hint", sa.String(24), nullable=False),
        sa.Column("agent_version", sa.String(80), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
    )

    op.create_table(
        "mail_node_commands",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mail_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mailbox_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_mail_node_commands_node_id", "mail_node_commands", ["node_id"])
    op.create_index("ix_mail_node_commands_tenant_id", "mail_node_commands", ["tenant_id"])
    op.create_index("ix_mail_node_commands_mailbox_id", "mail_node_commands", ["mailbox_id"])
    op.create_index("ix_mail_node_commands_status", "mail_node_commands", ["status"])


def downgrade():
    op.drop_index("ix_mail_node_commands_status", table_name="mail_node_commands")
    op.drop_index("ix_mail_node_commands_mailbox_id", table_name="mail_node_commands")
    op.drop_index("ix_mail_node_commands_tenant_id", table_name="mail_node_commands")
    op.drop_index("ix_mail_node_commands_node_id", table_name="mail_node_commands")
    op.drop_table("mail_node_commands")
    op.drop_table("mail_node_agents")
