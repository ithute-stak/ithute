"""add hosting quarantine upload agents

Revision ID: 0044_hosting_upload_agents
Revises: 0043_hosting_project_ops
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0044_hosting_upload_agents"
down_revision = "0043_hosting_project_ops"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hosting_upload_agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_hint", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="active", nullable=False),
        sa.Column("agent_version", sa.String(length=64), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotated_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("status IN ('active','disabled')", name="ck_hosting_upload_agent_status"),
        sa.ForeignKeyConstraint(["rotated_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("token_hash"),
    )


def downgrade() -> None:
    op.drop_table("hosting_upload_agents")
