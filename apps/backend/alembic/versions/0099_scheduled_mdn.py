"""Persist optional read receipt request on scheduled messages.

Revision ID: 0099_scheduled_mdn
Revises: 0098_sender_reputation
"""
from alembic import op
import sqlalchemy as sa

revision = "0099_scheduled_mdn"
down_revision = "0098_sender_reputation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scheduled_mail", sa.Column("request_read_receipt", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    op.drop_column("scheduled_mail", "request_read_receipt")
