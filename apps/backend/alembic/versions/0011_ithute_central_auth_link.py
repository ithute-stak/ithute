"""link Mailbox DNS users to central Ithute identities

Revision ID: 0011_ithute_central_auth_link
Revises: 0010_platform_self_domain
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011_ithute_central_auth_link"
down_revision = "0010_platform_self_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("auth_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_users_auth_user_id", "users", ["auth_user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_auth_user_id", table_name="users")
    op.drop_column("users", "auth_user_id")
