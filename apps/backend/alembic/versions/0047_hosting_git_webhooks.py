"""add secure Git webhook rebuild triggers

Revision ID: 0047_hosting_git_webhooks
Revises: 0046_hosting_build_logs
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0047_hosting_git_webhooks"
down_revision = "0046_hosting_build_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hosting_source_webhooks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=24), nullable=False),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="active", nullable=False),
        sa.Column("pending_rebuild", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("pending_commit", sa.String(length=64), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("provider IN ('github','gitlab','bitbucket','generic')", name="ck_hosting_source_webhook_provider"),
        sa.CheckConstraint("status IN ('active','disabled')", name="ck_hosting_source_webhook_status"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["hosting_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["hosting_sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", name="uq_hosting_source_webhook_source"),
    )
    op.create_index("ix_hosting_source_webhooks_tenant_id", "hosting_source_webhooks", ["tenant_id"])
    op.create_index("ix_hosting_source_webhooks_project_id", "hosting_source_webhooks", ["project_id"])

    op.create_table(
        "hosting_webhook_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("webhook_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("delivery_id", sa.String(length=160), nullable=False),
        sa.Column("event_name", sa.String(length=80), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["webhook_id"], ["hosting_source_webhooks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("webhook_id", "delivery_id", name="uq_hosting_webhook_delivery"),
    )
    op.create_index("ix_hosting_webhook_deliveries_webhook_id", "hosting_webhook_deliveries", ["webhook_id"])
    op.create_index("ix_hosting_webhook_deliveries_received_at", "hosting_webhook_deliveries", ["received_at"])


def downgrade() -> None:
    op.drop_index("ix_hosting_webhook_deliveries_received_at", table_name="hosting_webhook_deliveries")
    op.drop_index("ix_hosting_webhook_deliveries_webhook_id", table_name="hosting_webhook_deliveries")
    op.drop_table("hosting_webhook_deliveries")
    op.drop_index("ix_hosting_source_webhooks_project_id", table_name="hosting_source_webhooks")
    op.drop_index("ix_hosting_source_webhooks_tenant_id", table_name="hosting_source_webhooks")
    op.drop_table("hosting_source_webhooks")
