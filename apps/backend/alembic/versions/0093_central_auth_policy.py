"""add irreversible central auth policy

Revision ID: 0093_central_auth_policy
Revises: 0092_mail_relationships
Create Date: 2026-10-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0093_central_auth_policy"
down_revision = "0092_mail_relationships"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("central_auth_enforced", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "users",
        sa.Column("central_auth_enforced_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "central_auth_enforced_at")
    op.drop_column("users", "central_auth_enforced")
