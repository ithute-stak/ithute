"""add mail threat canary lifecycle fields

Revision ID: 0091_mail_threat_canary
Revises: 0090_mail_threat_shadow
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0091_mail_threat_canary"
down_revision = "0090_mail_threat_shadow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mail_threat_model_versions",
        sa.Column("canary_started_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("mail_threat_model_versions", "canary_started_at")
