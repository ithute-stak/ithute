"""phase 1 core platform

Revision ID: 0002_phase1_core_platform
Revises: 0001_initial_buildtrack
Create Date: 2026-08-23
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_phase1_core_platform"
down_revision = "0001_initial_buildtrack"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("code", sa.String(length=32), nullable=False, server_default="NTHANE"))
    op.add_column("companies", sa.Column("legal_name", sa.String(length=255), nullable=True))
    op.add_column("companies", sa.Column("registration_number", sa.String(length=100), nullable=True))
    op.add_column("companies", sa.Column("tax_number", sa.String(length=100), nullable=True))
    op.add_column("companies", sa.Column("currency_symbol", sa.String(length=8), nullable=False, server_default="M"))
    op.add_column("companies", sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Africa/Maseru"))
    op.add_column("companies", sa.Column("fiscal_year_start_month", sa.Integer(), nullable=False, server_default="4"))
    op.add_column("companies", sa.Column("phone", sa.String(length=64), nullable=True))
    op.add_column("companies", sa.Column("email", sa.String(length=255), nullable=True))
    op.add_column("companies", sa.Column("physical_address", sa.Text(), nullable=True))
    op.add_column("companies", sa.Column("postal_address", sa.Text(), nullable=True))
    op.add_column("companies", sa.Column("logo_path", sa.String(length=500), nullable=True))
    op.add_column("companies", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_unique_constraint("uq_companies_code", "companies", ["code"])

    op.create_table(
        "branches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("branch_type", sa.String(length=32), nullable=False, server_default="branch"),
        sa.Column("district", sa.String(length=120)),
        sa.Column("address", sa.Text()),
        sa.Column("phone", sa.String(length=64)),
        sa.Column("email", sa.String(length=255)),
        sa.Column("manager_name", sa.String(length=255)),
        sa.Column("manager_email", sa.String(length=255)),
        sa.Column("manager_phone", sa.String(length=64)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "code", name="uq_branch_company_code"),
    )
    op.create_index("ix_branches_company_id", "branches", ["company_id"])

    op.create_table(
        "sites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("site_type", sa.String(length=48), nullable=False, server_default="project_site"),
        sa.Column("district", sa.String(length=120)),
        sa.Column("location", sa.Text()),
        sa.Column("latitude", sa.Numeric(10, 7)),
        sa.Column("longitude", sa.Numeric(10, 7)),
        sa.Column("responsible_officer", sa.String(length=255)),
        sa.Column("responsible_phone", sa.String(length=64)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("branch_id", "code", name="uq_site_branch_code"),
    )
    op.create_index("ix_sites_company_id", "sites", ["company_id"])
    op.create_index("ix_sites_branch_id", "sites", ["branch_id"])

    op.create_table(
        "departments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="CASCADE")),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("manager_name", sa.String(length=255)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "branch_id", "code", name="uq_department_scope_code"),
    )
    op.create_index("ix_departments_company_id", "departments", ["company_id"])
    op.create_index("ix_departments_branch_id", "departments", ["branch_id"])

    op.create_table(
        "cost_centres",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="SET NULL")),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="SET NULL")),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.id", ondelete="SET NULL")),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("cost_centre_type", sa.String(length=48), nullable=False, server_default="operational"),
        sa.Column("description", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "code", name="uq_cost_centre_company_code"),
    )
    op.create_index("ix_cost_centres_company_id", "cost_centres", ["company_id"])
    op.create_index("ix_cost_centres_branch_id", "cost_centres", ["branch_id"])
    op.create_index("ix_cost_centres_site_id", "cost_centres", ["site_id"])

    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("scope_level", sa.String(length=24), nullable=False, server_default="company"),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "code", name="uq_role_company_code"),
    )
    op.create_index("ix_roles_company_id", "roles", ["company_id"])

    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=100), nullable=False, unique=True),
        sa.Column("module", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=48), nullable=False),
        sa.Column("description", sa.Text()),
    )
    op.create_index("ix_permissions_module", "permissions", ["module"])

    op.create_table(
        "role_permissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("permission_id", sa.Integer(), sa.ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
    )
    op.create_index("ix_role_permissions_role_id", "role_permissions", ["role_id"])
    op.create_index("ix_role_permissions_permission_id", "role_permissions", ["permission_id"])

    op.create_table(
        "approval_workflows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="CASCADE")),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("module", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("min_amount", sa.Numeric(18, 2)),
        sa.Column("max_amount", sa.Numeric(18, 2)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "code", name="uq_approval_workflow_code"),
    )
    op.create_index("ix_approval_workflows_company_id", "approval_workflows", ["company_id"])
    op.create_index("ix_approval_workflows_branch_id", "approval_workflows", ["branch_id"])
    op.create_index("ix_approval_workflows_module", "approval_workflows", ["module"])

    op.create_table(
        "approval_steps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workflow_id", sa.Integer(), sa.ForeignKey("approval_workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("required_approvals", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("escalation_hours", sa.Integer()),
        sa.UniqueConstraint("workflow_id", "step_order", name="uq_approval_step_order"),
    )
    op.create_index("ix_approval_steps_workflow_id", "approval_steps", ["workflow_id"])

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workflow_id", sa.Integer(), sa.ForeignKey("approval_workflows.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="SET NULL")),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="SET NULL")),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=False),
        sa.Column("reference", sa.String(length=100), nullable=False, unique=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2)),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("current_step_order", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("requested_by", sa.String(length=255), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_approval_requests_company_id", "approval_requests", ["company_id"])
    op.create_index("ix_approval_requests_workflow_id", "approval_requests", ["workflow_id"])
    op.create_index("ix_approval_requests_branch_id", "approval_requests", ["branch_id"])
    op.create_index("ix_approval_requests_site_id", "approval_requests", ["site_id"])

    op.create_table(
        "approval_actions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.Integer(), sa.ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("actor_name", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=24), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("acted_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_approval_actions_request_id", "approval_actions", ["request_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="SET NULL")),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="SET NULL")),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="SET NULL")),
        sa.Column("actor", sa.String(length=255), nullable=False, server_default="system"),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.String(length=100)),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_logs_company_id", "audit_logs", ["company_id"])
    op.create_index("ix_audit_logs_branch_id", "audit_logs", ["branch_id"])
    op.create_index("ix_audit_logs_site_id", "audit_logs", ["site_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_entity_type", "audit_logs", ["entity_type"])
    op.create_index("ix_audit_logs_occurred_at", "audit_logs", ["occurred_at"])

    op.create_table(
        "company_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "key", name="uq_company_setting_key"),
    )
    op.create_index("ix_company_settings_company_id", "company_settings", ["company_id"])

    op.create_table(
        "number_sequences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(length=48), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("prefix", sa.String(length=24), nullable=False),
        sa.Column("next_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("padding", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("reset_period", sa.String(length=24), nullable=False, server_default="never"),
        sa.Column("last_reset_key", sa.String(length=20)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("company_id", "code", name="uq_number_sequence_code"),
    )
    op.create_index("ix_number_sequences_company_id", "number_sequences", ["company_id"])

    op.create_table(
        "master_data_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("company_id", "code", name="uq_master_category_code"),
    )
    op.create_index("ix_master_data_categories_company_id", "master_data_categories", ["company_id"])

    op.create_table(
        "master_data_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("master_data_categories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("category_id", "code", name="uq_master_item_code"),
    )
    op.create_index("ix_master_data_items_category_id", "master_data_items", ["category_id"])

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="SET NULL")),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="SET NULL")),
        sa.Column("document_number", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=80)),
        sa.Column("entity_id", sa.String(length=100)),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("confidentiality", sa.String(length=32), nullable=False, server_default="internal"),
        sa.Column("retention_until", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(length=255), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "document_number", name="uq_document_number"),
    )
    op.create_index("ix_documents_company_id", "documents", ["company_id"])
    op.create_index("ix_documents_branch_id", "documents", ["branch_id"])
    op.create_index("ix_documents_site_id", "documents", ["site_id"])
    op.create_index("ix_documents_entity_type", "documents", ["entity_type"])
    op.create_index("ix_documents_entity_id", "documents", ["entity_id"])

    op.create_table(
        "document_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_path", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=160)),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("uploaded_by", sa.String(length=255), nullable=False, server_default="system"),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("document_id", "version_number", name="uq_document_version"),
    )
    op.create_index("ix_document_versions_document_id", "document_versions", ["document_id"])


def downgrade() -> None:
    for table in (
        "document_versions",
        "documents",
        "master_data_items",
        "master_data_categories",
        "number_sequences",
        "company_settings",
        "audit_logs",
        "approval_actions",
        "approval_requests",
        "approval_steps",
        "approval_workflows",
        "role_permissions",
        "permissions",
        "roles",
        "cost_centres",
        "departments",
        "sites",
        "branches",
    ):
        op.drop_table(table)

    op.drop_constraint("uq_companies_code", "companies", type_="unique")
    for column in (
        "is_active",
        "logo_path",
        "postal_address",
        "physical_address",
        "email",
        "phone",
        "fiscal_year_start_month",
        "timezone",
        "currency_symbol",
        "tax_number",
        "registration_number",
        "legal_name",
        "code",
    ):
        op.drop_column("companies", column)
