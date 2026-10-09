"""Developer access requests, approval gated.

Revision ID: 0013_developer_access_requests
Revises: 0012_app_redirect_uris
"""
import sqlalchemy as sa
from alembic import op

revision = "0013_developer_access_requests"
down_revision = "0012_app_redirect_uris"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "developer_access_requests",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product", sa.String(40), nullable=False),
        sa.Column("justification", sa.String(1000), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_developer_access_requests_user_id", "developer_access_requests", ["user_id"])

def downgrade() -> None:
    op.drop_index("ix_developer_access_requests_user_id", table_name="developer_access_requests")
    op.drop_table("developer_access_requests")
