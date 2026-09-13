"""add hosting deployment runtime queue and agent identity

Revision ID: 0021_hosting_deployment_runtime
Revises: 0020_application_hosting
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0021_hosting_deployment_runtime"
down_revision = "0020_application_hosting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hosting_nodes", sa.Column("agent_token_hash", sa.String(length=64), nullable=True))
    op.add_column("hosting_nodes", sa.Column("agent_last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("hosting_nodes", sa.Column("agent_version", sa.String(length=64), nullable=True))

    op.create_table(
        "hosting_deployments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_nodes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("image_ref", sa.String(length=500), nullable=False),
        sa.Column("source_sha", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column(
            "rollback_of_deployment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("hosting_deployments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("agent_message", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("health_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_hosting_deployments_tenant_id", "hosting_deployments", ["tenant_id"])
    op.create_index("ix_hosting_deployments_project_id", "hosting_deployments", ["project_id"])
    op.create_index("ix_hosting_deployments_node_id", "hosting_deployments", ["node_id"])
    op.create_index("ix_hosting_deployments_status", "hosting_deployments", ["status"])
    op.create_index(
        "ix_hosting_deployments_project_requested",
        "hosting_deployments",
        ["project_id", "requested_at"],
    )
    op.create_index(
        "ix_hosting_deployments_node_status_requested",
        "hosting_deployments",
        ["node_id", "status", "requested_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_hosting_deployments_node_status_requested", table_name="hosting_deployments")
    op.drop_index("ix_hosting_deployments_project_requested", table_name="hosting_deployments")
    op.drop_index("ix_hosting_deployments_status", table_name="hosting_deployments")
    op.drop_index("ix_hosting_deployments_node_id", table_name="hosting_deployments")
    op.drop_index("ix_hosting_deployments_project_id", table_name="hosting_deployments")
    op.drop_index("ix_hosting_deployments_tenant_id", table_name="hosting_deployments")
    op.drop_table("hosting_deployments")
    op.drop_column("hosting_nodes", "agent_version")
    op.drop_column("hosting_nodes", "agent_last_seen_at")
    op.drop_column("hosting_nodes", "agent_token_hash")
