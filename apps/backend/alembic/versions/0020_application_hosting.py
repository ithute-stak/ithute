"""add shared application hosting control-plane schema

Revision ID: 0020_application_hosting
Revises: 0019_managed_dns_ns
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0020_application_hosting"
down_revision = "0019_managed_dns_ns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("billing_plans", sa.Column("included_hosted_projects", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("billing_plans", sa.Column("hosting_storage_mb", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("billing_plans", sa.Column("hosting_memory_mb_per_project", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("billing_plans", sa.Column("hosting_cpu_millicores_per_project", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("billing_plans", sa.Column("hosting_pids_per_project", sa.Integer(), nullable=False, server_default="0"))

    # Existing commercial plans become complete email + DNS + app-hosting plans.
    # The system owner can change these values immediately from Packages & pricing.
    op.execute(
        "UPDATE billing_plans SET included_hosted_projects=1, hosting_storage_mb=1024, "
        "hosting_memory_mb_per_project=512, hosting_cpu_millicores_per_project=500, hosting_pids_per_project=128 "
        "WHERE code='starter'"
    )
    op.execute(
        "UPDATE billing_plans SET included_hosted_projects=3, hosting_storage_mb=5120, "
        "hosting_memory_mb_per_project=1024, hosting_cpu_millicores_per_project=1000, hosting_pids_per_project=256 "
        "WHERE code='business'"
    )
    op.execute(
        "UPDATE billing_plans SET included_hosted_projects=10, hosting_storage_mb=10240, "
        "hosting_memory_mb_per_project=2048, hosting_cpu_millicores_per_project=2000, hosting_pids_per_project=512 "
        "WHERE code='enterprise'"
    )

    op.create_table(
        "hosting_nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("hostname", sa.String(length=253), nullable=False),
        sa.Column("public_ip", sa.String(length=64), nullable=True),
        sa.Column("allocatable_storage_mb", sa.Integer(), nullable=False),
        sa.Column("allocatable_memory_mb", sa.Integer(), nullable=False),
        sa.Column("allocatable_cpu_millicores", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("accepts_new_projects", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", name="uq_hosting_node_name"),
    )
    op.create_index("ix_hosting_nodes_status", "hosting_nodes", ["status"])

    op.create_table(
        "hosting_projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_nodes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("domain_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("domains.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("hostname", sa.String(length=253), nullable=True),
        sa.Column("runtime", sa.String(length=32), nullable=False),
        sa.Column("source_repository", sa.String(length=1000), nullable=True),
        sa.Column("source_branch", sa.String(length=160), nullable=False, server_default="main"),
        sa.Column("image_ref", sa.String(length=500), nullable=True),
        sa.Column("container_port", sa.Integer(), nullable=False, server_default="8080"),
        sa.Column("health_path", sa.String(length=500), nullable=False, server_default="/"),
        sa.Column("storage_mb", sa.Integer(), nullable=False),
        sa.Column("memory_mb", sa.Integer(), nullable=False),
        sa.Column("cpu_millicores", sa.Integer(), nullable=False),
        sa.Column("pid_limit", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="configured"),
        sa.Column("rules_version", sa.String(length=32), nullable=False, server_default="2026-09-13"),
        sa.Column("rules_accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rules_accepted_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_hosting_project_tenant_slug"),
        sa.UniqueConstraint("hostname", name="uq_hosting_project_hostname"),
    )
    op.create_index("ix_hosting_projects_tenant_id", "hosting_projects", ["tenant_id"])
    op.create_index("ix_hosting_projects_node_id", "hosting_projects", ["node_id"])
    op.create_index("ix_hosting_projects_domain_id", "hosting_projects", ["domain_id"])
    op.create_index("ix_hosting_projects_status", "hosting_projects", ["status"])


def downgrade() -> None:
    op.drop_index("ix_hosting_projects_status", table_name="hosting_projects")
    op.drop_index("ix_hosting_projects_domain_id", table_name="hosting_projects")
    op.drop_index("ix_hosting_projects_node_id", table_name="hosting_projects")
    op.drop_index("ix_hosting_projects_tenant_id", table_name="hosting_projects")
    op.drop_table("hosting_projects")
    op.drop_index("ix_hosting_nodes_status", table_name="hosting_nodes")
    op.drop_table("hosting_nodes")
    op.drop_column("billing_plans", "hosting_pids_per_project")
    op.drop_column("billing_plans", "hosting_cpu_millicores_per_project")
    op.drop_column("billing_plans", "hosting_memory_mb_per_project")
    op.drop_column("billing_plans", "hosting_storage_mb")
    op.drop_column("billing_plans", "included_hosted_projects")
