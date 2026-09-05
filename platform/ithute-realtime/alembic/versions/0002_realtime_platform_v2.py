"""expand realtime into reliable chat, notification and broadcast backbone

Revision ID: 0002_realtime_platform_v2
Revises: 0001_realtime_chat
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_realtime_platform_v2"
down_revision = "0001_realtime_chat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)

    op.add_column("conversations", sa.Column("description", sa.String(1000), nullable=True))
    op.add_column("conversations", sa.Column("room_key", sa.String(120), nullable=True))
    op.add_column("conversations", sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_unique_constraint("uq_conversation_application_room", "conversations", ["application_id", "room_key"])

    op.add_column("messages", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("messages", sa.Column("priority", sa.String(16), nullable=False, server_default="normal"))
    op.add_column("messages", sa.Column("mentions_json", sa.Text(), nullable=False, server_default="[]"))
    op.add_column("messages", sa.Column("attachments_json", sa.Text(), nullable=False, server_default="[]"))
    op.add_column("messages", sa.Column("reply_to_message_id", uuid_type, nullable=True))
    op.add_column("messages", sa.Column("forwarded_from_message_id", uuid_type, nullable=True))
    op.create_foreign_key("fk_messages_reply_to", "messages", "messages", ["reply_to_message_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_messages_forwarded_from", "messages", "messages", ["forwarded_from_message_id"], ["id"], ondelete="SET NULL")

    op.create_table(
        "message_receipts",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("message_id", uuid_type, sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("auth_user_id", uuid_type, nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("device_key", sa.String(200), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("message_id", "auth_user_id", name="uq_message_receipt_user"),
    )
    op.create_index("ix_message_receipts_message_id", "message_receipts", ["message_id"])
    op.create_index("ix_message_receipts_auth_user_id", "message_receipts", ["auth_user_id"])

    op.create_table(
        "message_reactions",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("message_id", uuid_type, sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("auth_user_id", uuid_type, nullable=False),
        sa.Column("emoji", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("message_id", "auth_user_id", "emoji", name="uq_message_reaction_user_emoji"),
    )
    op.create_index("ix_message_reactions_message_id", "message_reactions", ["message_id"])
    op.create_index("ix_message_reactions_auth_user_id", "message_reactions", ["auth_user_id"])

    op.create_table(
        "conversation_pins",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("conversation_id", uuid_type, sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", uuid_type, sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pinned_by_sub", uuid_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("conversation_id", "message_id", name="uq_conversation_pin"),
    )
    op.create_index("ix_conversation_pins_conversation_id", "conversation_pins", ["conversation_id"])
    op.create_index("ix_conversation_pins_message_id", "conversation_pins", ["message_id"])

    op.create_table(
        "realtime_events",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("cursor", sa.String(64), nullable=False),
        sa.Column("application_id", sa.String(120), nullable=False),
        sa.Column("source_client_id", sa.String(120), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("audience_label", sa.String(160), nullable=True),
        sa.Column("idempotency_key", sa.String(160), nullable=True),
        sa.Column("request_fingerprint", sa.String(64), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("broadcast_connected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("push_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(1000), nullable=True),
        sa.Column("deliver_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("cursor", name="uq_realtime_event_cursor"),
        sa.UniqueConstraint("application_id", "idempotency_key", name="uq_realtime_event_idempotency"),
    )
    for name, cols in [
        ("ix_realtime_events_cursor", ["cursor"]),
        ("ix_realtime_events_application_id", ["application_id"]),
        ("ix_realtime_events_source_client_id", ["source_client_id"]),
        ("ix_realtime_events_event_type", ["event_type"]),
        ("ix_realtime_events_status", ["status"]),
        ("ix_realtime_events_deliver_at", ["deliver_at"]),
        ("ix_realtime_events_expires_at", ["expires_at"]),
        ("ix_realtime_events_created_at", ["created_at"]),
        ("ix_realtime_events_due", ["status", "deliver_at"]),
    ]:
        op.create_index(name, "realtime_events", cols)

    op.create_table(
        "event_recipients",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("event_id", uuid_type, sa.ForeignKey("realtime_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("auth_user_id", uuid_type, nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("push_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("event_id", "auth_user_id", name="uq_event_recipient"),
    )
    op.create_index("ix_event_recipients_event_id", "event_recipients", ["event_id"])
    op.create_index("ix_event_recipients_auth_user_id", "event_recipients", ["auth_user_id"])

    op.create_table(
        "audit_events",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("application_id", sa.String(120), nullable=False),
        sa.Column("actor_kind", sa.String(24), nullable=False),
        sa.Column("actor_sub", uuid_type, nullable=True),
        sa.Column("actor_client_id", sa.String(120), nullable=False),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("target_type", sa.String(80), nullable=False),
        sa.Column("target_id", sa.String(160), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_application_id", "audit_events", ["application_id"])
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])
    op.create_index("ix_audit_application_created", "audit_events", ["application_id", "created_at"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("event_recipients")
    op.drop_table("realtime_events")
    op.drop_table("conversation_pins")
    op.drop_table("message_reactions")
    op.drop_table("message_receipts")
    op.drop_constraint("fk_messages_forwarded_from", "messages", type_="foreignkey")
    op.drop_constraint("fk_messages_reply_to", "messages", type_="foreignkey")
    op.drop_column("messages", "forwarded_from_message_id")
    op.drop_column("messages", "reply_to_message_id")
    op.drop_column("messages", "attachments_json")
    op.drop_column("messages", "mentions_json")
    op.drop_column("messages", "priority")
    op.drop_column("messages", "version")
    op.drop_constraint("uq_conversation_application_room", "conversations", type_="unique")
    op.drop_column("conversations", "archived")
    op.drop_column("conversations", "room_key")
    op.drop_column("conversations", "description")
