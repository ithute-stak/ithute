"""add managed inbound forwarding destination

Revision ID: 0026_mail_forwarding
Revises: 0025_platform_mail_send
"""

from alembic import op
import sqlalchemy as sa


revision = "0026_mail_forwarding"
down_revision = "0025_platform_mail_send"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "platform_mailbox_bindings",
        sa.Column("inbound_forward_to", sa.String(length=320), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("platform_mailbox_bindings", "inbound_forward_to")
