"""Link Ithute Pay users to central !thute Auth identities.

Revision ID: 0007_ithute_central_auth
Revises: 0006_company_funding_accounts
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_ithute_central_auth"
down_revision = "0006_company_funding_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("auth_user_id", sa.String(length=36), nullable=True))
    op.create_index("ix_users_auth_user_id", "users", ["auth_user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_auth_user_id", table_name="users")
    op.drop_column("users", "auth_user_id")
