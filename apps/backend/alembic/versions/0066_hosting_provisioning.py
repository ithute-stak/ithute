"""add hosting provisioning workflows

Revision ID: 0066_hosting_provisioning
Revises: 0065_infrastructure_monitoring
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0066_hosting_provisioning"
down_revision = "0065_infrastructure_monitoring"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hosting_provisioning_workflows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("database_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_databases.id", ondelete="SET NULL"), nullable=True),
        sa.Column("build_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_builds.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("request_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_hosting_provisioning_tenant_id", "hosting_provisioning_workflows", ["tenant_id"])
    op.create_index("ix_hosting_provisioning_project_id", "hosting_provisioning_workflows", ["project_id"])
    op.create_index("ix_hosting_provisioning_status", "hosting_provisioning_workflows", ["status"])


def downgrade() -> None:
    op.drop_index("ix_hosting_provisioning_status", table_name="hosting_provisioning_workflows")
    op.drop_index("ix_hosting_provisioning_project_id", table_name="hosting_provisioning_workflows")
    op.drop_index("ix_hosting_provisioning_tenant_id", table_name="hosting_provisioning_workflows")
    op.drop_table("hosting_provisioning_workflows")
