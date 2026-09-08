"""phase 7 site operations

Revision ID: 0009_phase7_site_ops
Revises: 0008_phase6_projects
Create Date: 2026-08-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0009_phase7_site_ops"
down_revision = "0008_phase6_projects"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "site_operations_activations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_readiness_snapshot_id", sa.Integer(), sa.ForeignKey("project_readiness_snapshots.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("cost_centre_id", sa.Integer(), sa.ForeignKey("cost_centres.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("activated_by", sa.String(255), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.Text()),
        sa.UniqueConstraint("project_id", "site_id", name="uq_site_ops_project_site"),
    )
    for name in ("company_id", "project_id", "project_readiness_snapshot_id", "branch_id", "site_id", "cost_centre_id", "status"):
        op.create_index(f"ix_site_operations_activations_{name}", "site_operations_activations", [name])

    op.create_table(
        "site_daily_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("activation_id", sa.Integer(), sa.ForeignKey("site_operations_activations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("shift", sa.String(24), nullable=False, server_default="day"),
        sa.Column("weather_summary", sa.String(240)),
        sa.Column("rain_hours", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("work_summary", sa.Text()),
        sa.Column("planned_work", sa.Text()),
        sa.Column("blockers", sa.Text()),
        sa.Column("safety_summary", sa.Text()),
        sa.Column("visitor_summary", sa.Text()),
        sa.Column("no_work_reason", sa.Text()),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("approval_request_id", sa.Integer(), sa.ForeignKey("approval_requests.id", ondelete="SET NULL")),
        sa.Column("approved_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("submitted_by", sa.String(255)),
        sa.Column("approved_by", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "site_id", "report_date", "shift", name="uq_site_daily_report_shift"),
    )
    for name in ("company_id", "activation_id", "project_id", "branch_id", "site_id", "report_date", "status", "approval_request_id"):
        op.create_index(f"ix_site_daily_reports_{name}", "site_daily_reports", [name])

    op.create_table(
        "site_labour_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("daily_report_id", sa.Integer(), sa.ForeignKey("site_daily_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="SET NULL")),
        sa.Column("crew_name", sa.String(160)),
        sa.Column("worker_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("regular_hours", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("overtime_hours", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("activity", sa.String(300), nullable=False),
        sa.Column("work_area", sa.String(200)),
        sa.Column("cost_centre_id", sa.Integer(), sa.ForeignKey("cost_centres.id", ondelete="SET NULL")),
        sa.Column("timesheet_entry_id", sa.Integer(), sa.ForeignKey("timesheet_entries.id", ondelete="SET NULL")),
        sa.Column("notes", sa.Text()),
        sa.Column("recorded_by", sa.String(255), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    for name in ("company_id", "daily_report_id", "project_id", "site_id", "employee_id", "cost_centre_id", "timesheet_entry_id"):
        op.create_index(f"ix_site_labour_entries_{name}", "site_labour_entries", [name])

    op.create_table(
        "site_plant_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("daily_report_id", sa.Integer(), sa.ForeignKey("site_daily_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("fleet_assets.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("operator_employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="SET NULL")),
        sa.Column("usage_hours", sa.Numeric(7, 2), nullable=False, server_default="0"),
        sa.Column("idle_hours", sa.Numeric(7, 2), nullable=False, server_default="0"),
        sa.Column("start_odometer_km", sa.Numeric(14, 2)),
        sa.Column("end_odometer_km", sa.Numeric(14, 2)),
        sa.Column("start_engine_hours", sa.Numeric(14, 2)),
        sa.Column("end_engine_hours", sa.Numeric(14, 2)),
        sa.Column("activity", sa.String(300), nullable=False),
        sa.Column("breakdown", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.Text()),
        sa.Column("recorded_by", sa.String(255), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    for name in ("company_id", "daily_report_id", "project_id", "site_id", "asset_id", "operator_employee_id"):
        op.create_index(f"ix_site_plant_usage_{name}", "site_plant_usage", [name])

    op.create_table(
        "site_material_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("daily_report_id", sa.Integer(), sa.ForeignKey("site_daily_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("movement_type", sa.String(24), nullable=False),
        sa.Column("material_code", sa.String(80)),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("unit", sa.String(40), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("total_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("supplier_or_source", sa.String(240)),
        sa.Column("source_reference", sa.String(160)),
        sa.Column("work_area", sa.String(200)),
        sa.Column("waste_reason", sa.Text()),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("notes", sa.Text()),
        sa.Column("recorded_by", sa.String(255), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    for name in ("company_id", "daily_report_id", "project_id", "site_id", "movement_type", "material_code", "document_id"):
        op.create_index(f"ix_site_material_entries_{name}", "site_material_entries", [name])

    op.create_table(
        "site_progress_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("daily_report_id", sa.Integer(), sa.ForeignKey("site_daily_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("milestone_id", sa.Integer(), sa.ForeignKey("project_milestones.id", ondelete="SET NULL")),
        sa.Column("work_item", sa.String(300), nullable=False),
        sa.Column("unit", sa.String(40)),
        sa.Column("planned_quantity", sa.Numeric(18, 4)),
        sa.Column("period_quantity", sa.Numeric(18, 4)),
        sa.Column("cumulative_quantity", sa.Numeric(18, 4)),
        sa.Column("progress_pct", sa.Numeric(7, 3), nullable=False, server_default="0"),
        sa.Column("measurement_date", sa.Date(), nullable=False),
        sa.Column("narrative", sa.Text()),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("recorded_by", sa.String(255), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    for name in ("company_id", "daily_report_id", "project_id", "site_id", "milestone_id", "measurement_date", "document_id"):
        op.create_index(f"ix_site_progress_entries_{name}", "site_progress_entries", [name])

    op.create_table(
        "site_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("daily_report_id", sa.Integer(), sa.ForeignKey("site_daily_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("evidence_type", sa.String(40), nullable=False),
        sa.Column("caption", sa.String(300)),
        sa.Column("work_area", sa.String(200)),
        sa.Column("captured_at", sa.DateTime(timezone=True)),
        sa.Column("added_by", sa.String(255), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("daily_report_id", "document_id", "evidence_type", name="uq_site_report_evidence"),
    )
    for name in ("company_id", "daily_report_id", "project_id", "site_id", "document_id", "evidence_type"):
        op.create_index(f"ix_site_evidence_{name}", "site_evidence", [name])

    op.create_table(
        "site_incidents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("activation_id", sa.Integer(), sa.ForeignKey("site_operations_activations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("daily_report_id", sa.Integer(), sa.ForeignKey("site_daily_reports.id", ondelete="SET NULL")),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("incident_number", sa.String(80), nullable=False),
        sa.Column("incident_type", sa.String(48), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("severity", sa.String(24), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="SET NULL")),
        sa.Column("persons_involved", sa.Text()),
        sa.Column("lost_time", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("immediate_action", sa.Text()),
        sa.Column("root_cause", sa.Text()),
        sa.Column("corrective_action", sa.Text()),
        sa.Column("owner_employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="SET NULL")),
        sa.Column("due_date", sa.Date()),
        sa.Column("status", sa.String(24), nullable=False, server_default="open"),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("recorded_by", sa.String(255), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "incident_number", name="uq_site_incident_number"),
    )
    for name in ("company_id", "activation_id", "daily_report_id", "project_id", "branch_id", "site_id", "incident_number", "incident_type", "occurred_at", "severity", "employee_id", "owner_employee_id", "due_date", "status", "document_id"):
        op.create_index(f"ix_site_incidents_{name}", "site_incidents", [name])

    op.create_table(
        "site_quality_checks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("activation_id", sa.Integer(), sa.ForeignKey("site_operations_activations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("daily_report_id", sa.Integer(), sa.ForeignKey("site_daily_reports.id", ondelete="SET NULL")),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("inspection_number", sa.String(80), nullable=False),
        sa.Column("check_type", sa.String(48), nullable=False),
        sa.Column("work_item", sa.String(300), nullable=False),
        sa.Column("specification_reference", sa.String(200)),
        sa.Column("inspected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("inspector_employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="SET NULL")),
        sa.Column("result", sa.String(24), nullable=False),
        sa.Column("nonconformance_number", sa.String(100)),
        sa.Column("corrective_action", sa.Text()),
        sa.Column("owner_employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="SET NULL")),
        sa.Column("due_date", sa.Date()),
        sa.Column("status", sa.String(24), nullable=False, server_default="open"),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("notes", sa.Text()),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "inspection_number", name="uq_site_quality_number"),
    )
    for name in ("company_id", "activation_id", "daily_report_id", "project_id", "branch_id", "site_id", "inspection_number", "check_type", "inspected_at", "inspector_employee_id", "result", "nonconformance_number", "owner_employee_id", "due_date", "status", "document_id"):
        op.create_index(f"ix_site_quality_checks_{name}", "site_quality_checks", [name])

    op.create_table(
        "site_operations_audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="SET NULL")),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="SET NULL")),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.String(100)),
        sa.Column("detail", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    for name in ("company_id", "project_id", "site_id", "action", "entity_type", "entity_id", "occurred_at"):
        op.create_index(f"ix_site_operations_audit_events_{name}", "site_operations_audit_events", [name])


def downgrade() -> None:
    for table in (
        "site_operations_audit_events",
        "site_quality_checks",
        "site_incidents",
        "site_evidence",
        "site_progress_entries",
        "site_material_entries",
        "site_plant_usage",
        "site_labour_entries",
        "site_daily_reports",
        "site_operations_activations",
    ):
        op.drop_table(table)
