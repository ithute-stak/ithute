"""phase 6 project mobilisation

Revision ID: 0008_phase6_projects
Revises: 0007_phase5_submission_evidence
Create Date: 2026-08-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0008_phase6_projects"
down_revision = "0007_phase5_submission_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("tender_id", sa.Integer(), nullable=True),
        sa.Column("source_submission_id", sa.Integer(), nullable=True),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("primary_site_id", sa.Integer(), nullable=False),
        sa.Column("cost_centre_id", sa.Integer(), nullable=False),
        sa.Column("project_manager_employee_id", sa.Integer(), nullable=True),
        sa.Column("project_number", sa.String(80), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("client_name", sa.String(240), nullable=False),
        sa.Column("contract_reference", sa.String(180), nullable=True),
        sa.Column("project_type", sa.String(100), nullable=True),
        sa.Column("location", sa.String(300), nullable=True),
        sa.Column("contract_start_date", sa.Date(), nullable=False),
        sa.Column("contract_completion_date", sa.Date(), nullable=False),
        sa.Column("mobilisation_date", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="LSL"),
        sa.Column("contract_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("baseline_budget", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("contingency_budget", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="mobilising"),
        sa.Column("readiness_status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("mobilisation_approval_request_id", sa.Integer(), nullable=True),
        sa.Column("contract_document_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tender_id"], ["tenders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_submission_id"], ["tender_submissions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["primary_site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["cost_centre_id"], ["cost_centres.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_manager_employee_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["mobilisation_approval_request_id"], ["approval_requests.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["contract_document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("company_id", "project_number", name="uq_project_company_number"),
        sa.UniqueConstraint("tender_id", name="uq_project_tender"),
    )
    for name, cols in (
        ("ix_projects_company_id", ["company_id"]), ("ix_projects_tender_id", ["tender_id"]),
        ("ix_projects_branch_id", ["branch_id"]), ("ix_projects_primary_site_id", ["primary_site_id"]),
        ("ix_projects_status", ["status"]), ("ix_projects_readiness_status", ["readiness_status"]),
        ("ix_projects_completion", ["contract_completion_date"]),
    ):
        op.create_index(name, "projects", cols)

    op.create_table(
        "project_sites",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False), sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("site_role", sa.String(40), nullable=False, server_default="work_site"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("linked_by", sa.String(255), nullable=False), sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("project_id", "site_id", name="uq_project_site"),
    )
    op.create_index("ix_project_sites_project_id", "project_sites", ["project_id"])
    op.create_index("ix_project_sites_site_id", "project_sites", ["site_id"])

    op.create_table(
        "project_team_members",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False), sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(80), nullable=False), sa.Column("allocation_pct", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("start_date", sa.Date(), nullable=True), sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="planned"), sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("added_by", sa.String(255), nullable=False), sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("project_id", "employee_id", "role", name="uq_project_team_employee_role"),
    )
    op.create_index("ix_project_team_project_id", "project_team_members", ["project_id"])
    op.create_index("ix_project_team_employee_id", "project_team_members", ["employee_id"])

    op.create_table(
        "project_budget_baselines",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False), sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source", sa.String(48), nullable=False, server_default="tender"),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("total_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("approval_request_id", sa.Integer(), nullable=True), sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approval_request_id"], ["approval_requests.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("project_id", "version", name="uq_project_budget_version"),
    )
    op.create_index("ix_project_budget_project_id", "project_budget_baselines", ["project_id"])
    op.create_index("ix_project_budget_status", "project_budget_baselines", ["status"])

    op.create_table(
        "project_budget_lines",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False), sa.Column("baseline_id", sa.Integer(), nullable=False),
        sa.Column("source_tender_estimate_item_id", sa.Integer(), nullable=True), sa.Column("cost_code", sa.String(80), nullable=True),
        sa.Column("cost_type", sa.String(40), nullable=False), sa.Column("description", sa.String(300), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False, server_default="0"), sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["baseline_id"], ["project_budget_baselines.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_tender_estimate_item_id"], ["tender_estimate_items.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_project_budget_lines_baseline", "project_budget_lines", ["baseline_id"])
    op.create_index("ix_project_budget_lines_type", "project_budget_lines", ["cost_type"])

    op.create_table(
        "project_milestones",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False), sa.Column("code", sa.String(80), nullable=True),
        sa.Column("name", sa.String(240), nullable=False), sa.Column("planned_start", sa.Date(), nullable=False),
        sa.Column("planned_finish", sa.Date(), nullable=False), sa.Column("weight_pct", sa.Numeric(8, 3), nullable=False, server_default="0"),
        sa.Column("status", sa.String(24), nullable=False, server_default="planned"), sa.Column("predecessor_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True), sa.Column("created_by", sa.String(255), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["predecessor_id"], ["project_milestones.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_project_milestones_project", "project_milestones", ["project_id"])
    op.create_index("ix_project_milestones_finish", "project_milestones", ["planned_finish"])

    op.create_table(
        "project_mobilisation_items",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False), sa.Column("category", sa.String(80), nullable=False),
        sa.Column("name", sa.String(240), nullable=False), sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"), sa.Column("owner_employee_id", sa.Integer(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True), sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True), sa.Column("updated_by", sa.String(255), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_employee_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_project_mob_project", "project_mobilisation_items", ["project_id"])
    op.create_index("ix_project_mob_status", "project_mobilisation_items", ["status"])

    op.create_table(
        "project_asset_allocations",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False), sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=False), sa.Column("planned_from", sa.Date(), nullable=False),
        sa.Column("planned_to", sa.Date(), nullable=True), sa.Column("status", sa.String(24), nullable=False, server_default="planned"),
        sa.Column("purpose", sa.Text(), nullable=True), sa.Column("allocated_by", sa.String(255), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True), sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["fleet_assets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_project_assets_project", "project_asset_allocations", ["project_id"])
    op.create_index("ix_project_assets_asset", "project_asset_allocations", ["asset_id"])
    op.create_index("ix_project_assets_status", "project_asset_allocations", ["status"])

    op.create_table(
        "project_risks",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False), sa.Column("risk_number", sa.String(80), nullable=False),
        sa.Column("category", sa.String(80), nullable=False), sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True), sa.Column("likelihood", sa.Integer(), nullable=False),
        sa.Column("impact", sa.Integer(), nullable=False), sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("owner_employee_id", sa.Integer(), nullable=True), sa.Column("mitigation", sa.Text(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="open"), sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_employee_id"], ["employees.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("company_id", "risk_number", name="uq_project_risk_number"),
    )
    op.create_index("ix_project_risks_project", "project_risks", ["project_id"])
    op.create_index("ix_project_risks_rating", "project_risks", ["rating"])

    op.create_table(
        "project_handover_documents",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False), sa.Column("document_type", sa.String(100), nullable=False),
        sa.Column("title", sa.String(240), nullable=False), sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("document_id", sa.Integer(), nullable=True), sa.Column("source_phase", sa.Integer(), nullable=True),
        sa.Column("source_reference", sa.String(160), nullable=True), sa.Column("status", sa.String(24), nullable=False, server_default="missing"),
        sa.Column("notes", sa.Text(), nullable=True), sa.Column("verified_by", sa.String(255), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_project_handover_project", "project_handover_documents", ["project_id"])
    op.create_index("ix_project_handover_status", "project_handover_documents", ["status"])

    op.create_table(
        "project_readiness_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False), sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("approval_request_id", sa.Integer(), nullable=False), sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approval_request_id"], ["approval_requests.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("project_id", "version", name="uq_project_readiness_version"),
    )
    op.create_index("ix_project_readiness_project", "project_readiness_snapshots", ["project_id"])

    op.create_table(
        "project_audit_events",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True), sa.Column("branch_id", sa.Integer(), nullable=True),
        sa.Column("site_id", sa.Integer(), nullable=True), sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_name", sa.String(255), nullable=False), sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False), sa.Column("entity_id", sa.String(100), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=False), sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_project_audit_company", "project_audit_events", ["company_id"])
    op.create_index("ix_project_audit_project", "project_audit_events", ["project_id"])
    op.create_index("ix_project_audit_time", "project_audit_events", ["occurred_at"])


def downgrade() -> None:
    for table in (
        "project_audit_events", "project_readiness_snapshots", "project_handover_documents", "project_risks",
        "project_asset_allocations", "project_mobilisation_items", "project_milestones", "project_budget_lines",
        "project_budget_baselines", "project_team_members", "project_sites", "projects",
    ):
        op.drop_table(table)
