"""add durable Auth lifecycle event outbox

Revision ID: 0005_push_event_outbox
Revises: 0004_webauthn_passkeys
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_push_event_outbox"
down_revision = "0004_webauthn_passkeys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_event_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("subject_user_id", sa.Uuid(), nullable=True),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("client_id", sa.String(length=120), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_event_outbox_event_type", "auth_event_outbox", ["event_type"])
    op.create_index("ix_auth_event_outbox_subject_user_id", "auth_event_outbox", ["subject_user_id"])
    op.create_index("ix_auth_event_outbox_session_id", "auth_event_outbox", ["session_id"])
    op.create_index("ix_auth_event_outbox_client_id", "auth_event_outbox", ["client_id"])
    op.create_index("ix_auth_event_outbox_next_attempt_at", "auth_event_outbox", ["next_attempt_at"])
    op.create_index("ix_auth_event_outbox_delivered_at", "auth_event_outbox", ["delivered_at"])


def downgrade() -> None:
    op.drop_table("auth_event_outbox")
