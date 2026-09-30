"""add isolated hosting build queue

Revision ID: 0040_hosting_builds
Revises: 0039_db_pending_password
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0040_hosting_builds"
down_revision = "0039_db_pending_password"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hosting_builder_agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_hint", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="active", nullable=False),
        sa.Column("agent_version", sa.String(length=64), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotated_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("status IN ('active','disabled')", name="ck_hosting_builder_agent_status"),
        sa.ForeignKeyConstraint(["rotated_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("token_hash"),
    )

    op.create_table(
        "hosting_builds",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("builder_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("runtime", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("source_commit", sa.String(length=64), nullable=True),
        sa.Column("image_ref", sa.String(length=500), nullable=True),
        sa.Column("image_digest", sa.String(length=80), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('queued','claimed','building','succeeded','failed','cancelled')", name="ck_hosting_build_status"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["hosting_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["hosting_sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["builder_agent_id"], ["hosting_builder_agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ["tenant_id", "project_id", "source_id", "builder_agent_id", "status"]:
        op.create_index(f"ix_hosting_builds_{column}", "hosting_builds", [column])


def downgrade() -> None:
    op.drop_table("hosting_builds")
    op.drop_table("hosting_builder_agents")
