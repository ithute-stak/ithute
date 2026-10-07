"""index phishing findings by mailbox and created time

Revision ID: 0096_mail_identity_idx
Revises: 0095_passkey_credentials
Create Date: 2026-10-07
"""
from alembic import op

revision = "0096_mail_identity_idx"
down_revision = "0095_passkey_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_phishing_mailbox_created",
        "phishing_findings",
        ["mailbox_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_phishing_mailbox_created", table_name="phishing_findings")
