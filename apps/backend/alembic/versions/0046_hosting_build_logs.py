"""add bounded hosting build logs

Revision ID: 0046_hosting_build_logs
Revises: 0045_hosting_metering
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0046_hosting_build_logs"
down_revision = "0045_hosting_metering"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hosting_build_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("build_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=48), nullable=False),
        sa.Column("level", sa.String(length=16), server_default="info", nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("level IN ('info','warning','error')", name="ck_hosting_build_log_level"),
        sa.ForeignKeyConstraint(["build_id"], ["hosting_builds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("build_id", "sequence", name="uq_hosting_build_log_sequence"),
    )
    op.create_index("ix_hosting_build_logs_build_id", "hosting_build_logs", ["build_id"])


def downgrade() -> None:
    op.drop_index("ix_hosting_build_logs_build_id", table_name="hosting_build_logs")
    op.drop_table("hosting_build_logs")
