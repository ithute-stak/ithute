"""NBros neutral product foundation.

Revision ID: 0001_foundation
Revises: None
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("auth_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email_snapshot", sa.String(length=320), nullable=True),
        sa.Column("role", sa.String(length=64), nullable=False, server_default="admin"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("auth_user_id", name="uq_profiles_auth_user_id"),
    )
    op.create_index("ix_profiles_email_snapshot", "profiles", ["email_snapshot"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_profiles_email_snapshot", table_name="profiles")
    op.drop_table("profiles")
