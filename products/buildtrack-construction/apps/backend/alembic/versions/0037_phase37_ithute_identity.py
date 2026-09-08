"""Phase 37: link BuildTrack users to central Ithute Auth identities."""

from alembic import op
import sqlalchemy as sa

revision = "0037_phase37_ithute_identity"
down_revision = "0036_phase35_automation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("auth_user_id", sa.String(length=36), nullable=True))
    op.create_index("ix_users_auth_user_id", "users", ["auth_user_id"], unique=False)
    op.create_unique_constraint("uq_user_auth_user_id", "users", ["auth_user_id"])


def downgrade() -> None:
    op.drop_constraint("uq_user_auth_user_id", "users", type_="unique")
    op.drop_index("ix_users_auth_user_id", table_name="users")
    op.drop_column("users", "auth_user_id")
