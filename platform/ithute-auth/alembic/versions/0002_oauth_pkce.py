"""add OAuth authorization code storage

Revision ID: 0002_oauth_pkce
Revises: 0001_central_identity
Create Date: 2026-09-04
"""
from alembic import op
import sqlalchemy as sa


revision = "0002_oauth_pkce"
down_revision = "0001_central_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "authorization_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.String(length=120), nullable=False),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("code_challenge", sa.String(length=128), nullable=False),
        sa.Column("nonce", sa.String(length=512), nullable=False),
        sa.Column("scope", sa.String(length=512), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash"),
    )
    op.create_index("ix_authorization_codes_code_hash", "authorization_codes", ["code_hash"])
    op.create_index("ix_authorization_codes_user_id", "authorization_codes", ["user_id"])
    op.create_index("ix_authorization_codes_client_id", "authorization_codes", ["client_id"])
    op.create_index("ix_authorization_codes_expires_at", "authorization_codes", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_authorization_codes_expires_at", table_name="authorization_codes")
    op.drop_index("ix_authorization_codes_client_id", table_name="authorization_codes")
    op.drop_index("ix_authorization_codes_user_id", table_name="authorization_codes")
    op.drop_index("ix_authorization_codes_code_hash", table_name="authorization_codes")
    op.drop_table("authorization_codes")
