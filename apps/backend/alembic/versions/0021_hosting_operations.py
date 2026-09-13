"""add hosting deployment operations

Revision ID: 0021_hosting_operations
Revises: 0020_application_hosting
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0021_hosting_operations"
down_revision = "0020_application_hosting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hosting_node_agents",
        sa.Column("node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_nodes.id", ondelete="CASCADE"), primary_key=True, nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_hint", sa.String(length=24), nullable=False),
        sa.Column("agent_version", sa.String(length=64), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.UniqueConstraint("token_hash", name="uq_hosting_node_agent_token_hash"),
    )

    op.create_table(
        "hosting_environment_variables",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("is_secret", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("project_id", "key", name="uq_hosting_env_project_key"),
    )
    op.create_index("ix_hosting_environment_variables_project_id", "hosting_environment_variables", ["project_id"])

    op.create_table(
        "hosting_deployments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_nodes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("previous_deployment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_deployments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("release_number", sa.Integer(), nullable=False),
        sa.Column("image_ref", sa.String(length=500), nullable=False),
        sa.Column("image_digest", sa.String(length=80), nullable=False),
        sa.Column("source_commit", sa.String(length=64), nullable=True),
        sa.Column("runtime_manifest_version", sa.String(length=16), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_health_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("project_id", "release_number", name="uq_hosting_deployment_project_release"),
    )
    op.create_index("ix_hosting_deployments_tenant_id", "hosting_deployments", ["tenant_id"])
    op.create_index("ix_hosting_deployments_project_id", "hosting_deployments", ["project_id"])
    op.create_index("ix_hosting_deployments_node_id", "hosting_deployments", ["node_id"])
    op.create_index("ix_hosting_deployments_status", "hosting_deployments", ["status"])


def downgrade() -> None:
    op.drop_index("ix_hosting_deployments_status", table_name="hosting_deployments")
    op.drop_index("ix_hosting_deployments_node_id", table_name="hosting_deployments")
    op.drop_index("ix_hosting_deployments_project_id", table_name="hosting_deployments")
    op.drop_index("ix_hosting_deployments_tenant_id", table_name="hosting_deployments")
    op.drop_table("hosting_deployments")
    op.drop_index("ix_hosting_environment_variables_project_id", table_name="hosting_environment_variables")
    op.drop_table("hosting_environment_variables")
    op.drop_table("hosting_node_agents")
