"""add safe application failover

Revision ID: 0071_application_failover
Revises: 0070_hosting_node_health
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0071_application_failover"
down_revision = "0070_hosting_node_health"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "hosting_projects",
        sa.Column("failover_policy", sa.String(length=32), nullable=False, server_default="manual"),
    )
    op.create_index("ix_hosting_projects_failover_policy", "hosting_projects", ["failover_policy"])

    op.create_table(
        "hosting_failover_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_nodes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("deployment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_deployments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("edge_status", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_hosting_failover_attempts_project_id", "hosting_failover_attempts", ["project_id"])
    op.create_index("ix_hosting_failover_attempts_source_node_id", "hosting_failover_attempts", ["source_node_id"])
    op.create_index("ix_hosting_failover_attempts_target_node_id", "hosting_failover_attempts", ["target_node_id"])
    op.create_index("ix_hosting_failover_attempts_deployment_id", "hosting_failover_attempts", ["deployment_id"])
    op.create_index("ix_hosting_failover_attempts_status", "hosting_failover_attempts", ["status"])


def downgrade() -> None:
    op.drop_index("ix_hosting_failover_attempts_status", table_name="hosting_failover_attempts")
    op.drop_index("ix_hosting_failover_attempts_deployment_id", table_name="hosting_failover_attempts")
    op.drop_index("ix_hosting_failover_attempts_target_node_id", table_name="hosting_failover_attempts")
    op.drop_index("ix_hosting_failover_attempts_source_node_id", table_name="hosting_failover_attempts")
    op.drop_index("ix_hosting_failover_attempts_project_id", table_name="hosting_failover_attempts")
    op.drop_table("hosting_failover_attempts")
    op.drop_index("ix_hosting_projects_failover_policy", table_name="hosting_projects")
    op.drop_column("hosting_projects", "failover_policy")
