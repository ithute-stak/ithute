"""create centralized realtime chat tables

Revision ID: 0001_realtime_chat
Revises:
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_realtime_chat"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    op.create_table(
        "conversations",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("application_id", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("created_by_sub", uuid_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_conversations_application_id", "conversations", ["application_id"])

    op.create_table(
        "conversation_members",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("conversation_id", uuid_type, sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("auth_user_id", uuid_type, nullable=False),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_read_message_id", uuid_type, nullable=True),
        sa.Column("muted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("conversation_id", "auth_user_id", name="uq_conversation_member"),
    )
    op.create_index("ix_conversation_members_conversation_id", "conversation_members", ["conversation_id"])
    op.create_index("ix_conversation_members_auth_user_id", "conversation_members", ["auth_user_id"])

    op.create_table(
        "messages",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("conversation_id", uuid_type, sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("application_id", sa.String(120), nullable=False),
        sa.Column("sender_sub", uuid_type, nullable=True),
        sa.Column("sender_client_id", sa.String(120), nullable=False),
        sa.Column("sender_kind", sa.String(24), nullable=False),
        sa.Column("message_type", sa.String(32), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("data_json", sa.Text(), nullable=False),
        sa.Column("client_message_id", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("conversation_id", "client_message_id", name="uq_conversation_client_message"),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index("ix_messages_application_id", "messages", ["application_id"])
    op.create_index("ix_messages_sender_sub", "messages", ["sender_sub"])
    op.create_index("ix_messages_created_at", "messages", ["created_at"])
    op.create_index("ix_messages_conversation_created", "messages", ["conversation_id", "created_at"])


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_table("conversation_members")
    op.drop_table("conversations")
