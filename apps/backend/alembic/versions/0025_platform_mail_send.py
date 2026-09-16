"""add idempotent managed-service mail sending

Revision ID: 0025_platform_mail_send
Revises: 0024_mail_namespace
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0025_platform_mail_send"
down_revision = "0024_mail_namespace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_mail_outbound_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_client_id", sa.String(length=120), nullable=False),
        sa.Column("external_reference", sa.String(length=200), nullable=False),
        sa.Column("mailbox_binding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipient", sa.String(length=320), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("transactional_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider_message_id", sa.String(length=320), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="submitting"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["mailbox_binding_id"], ["platform_mailbox_bindings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transactional_message_id"], ["transactional_messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "service_client_id",
            "external_reference",
            name="uq_platform_mail_outbound_client_reference",
        ),
    )
    op.create_index(
        "ix_platform_mail_outbound_deliveries_service_client_id",
        "platform_mail_outbound_deliveries",
        ["service_client_id"],
    )
    op.create_index(
        "ix_platform_mail_outbound_deliveries_external_reference",
        "platform_mail_outbound_deliveries",
        ["external_reference"],
    )
    op.create_index(
        "ix_platform_mail_outbound_deliveries_mailbox_binding_id",
        "platform_mail_outbound_deliveries",
        ["mailbox_binding_id"],
    )
    op.create_index(
        "ix_platform_mail_outbound_deliveries_transactional_message_id",
        "platform_mail_outbound_deliveries",
        ["transactional_message_id"],
    )
    op.create_index(
        "ix_platform_mail_outbound_deliveries_status",
        "platform_mail_outbound_deliveries",
        ["status"],
    )


def downgrade() -> None:
    op.drop_table("platform_mail_outbound_deliveries")
