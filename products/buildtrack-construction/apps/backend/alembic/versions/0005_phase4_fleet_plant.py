"""phase 4 fleet and plant

Revision ID: 0005_phase4_fleet_plant
Revises: 0004_phase3_workforce_payroll
Create Date: 2026-08-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_phase4_fleet_plant"
down_revision = "0004_phase3_workforce_payroll"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fleet_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="SET NULL")),
        sa.Column("cost_centre_id", sa.Integer(), sa.ForeignKey("cost_centres.id", ondelete="SET NULL")),
        sa.Column("asset_number", sa.String(64), nullable=False),
        sa.Column("asset_type", sa.String(40), nullable=False),
        sa.Column("category", sa.String(80)),
        sa.Column("registration_number", sa.String(80)),
        sa.Column("make", sa.String(120), nullable=False), sa.Column("model", sa.String(120), nullable=False),
        sa.Column("manufacture_year", sa.Integer()), sa.Column("vin_serial_number", sa.String(160)), sa.Column("engine_number", sa.String(120)),
        sa.Column("fuel_type", sa.String(40)), sa.Column("ownership_type", sa.String(32), nullable=False, server_default="owned"),
        sa.Column("supplier_owner", sa.String(200)), sa.Column("acquisition_date", sa.Date()), sa.Column("acquisition_cost", sa.Numeric(18,2)),
        sa.Column("meter_type", sa.String(24), nullable=False, server_default="odometer"),
        sa.Column("current_odometer_km", sa.Numeric(14,2), nullable=False, server_default="0"),
        sa.Column("current_engine_hours", sa.Numeric(14,2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("serviceability", sa.String(32), nullable=False, server_default="serviceable"),
        sa.Column("colour", sa.String(60)), sa.Column("capacity_description", sa.String(160)), sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.String(255), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "asset_number", name="uq_fleet_asset_company_number"),
        sa.UniqueConstraint("company_id", "registration_number", name="uq_fleet_asset_company_registration"),
    )
    for name, cols in (
        ("ix_fleet_assets_company_id", ["company_id"]), ("ix_fleet_assets_branch_id", ["branch_id"]),
        ("ix_fleet_assets_site_id", ["site_id"]), ("ix_fleet_assets_cost_centre_id", ["cost_centre_id"]),
        ("ix_fleet_assets_asset_type", ["asset_type"]), ("ix_fleet_assets_vin_serial_number", ["vin_serial_number"]),
        ("ix_fleet_assets_status", ["status"]), ("ix_fleet_assets_serviceability", ["serviceability"]),
    ): op.create_index(name, "fleet_assets", cols)

    op.create_table("fleet_assignments",
        sa.Column("id",sa.Integer(),primary_key=True), sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),
        sa.Column("asset_id",sa.Integer(),sa.ForeignKey("fleet_assets.id",ondelete="CASCADE"),nullable=False), sa.Column("employee_id",sa.Integer(),sa.ForeignKey("employees.id",ondelete="SET NULL")),
        sa.Column("branch_id",sa.Integer(),sa.ForeignKey("branches.id",ondelete="RESTRICT"),nullable=False), sa.Column("site_id",sa.Integer(),sa.ForeignKey("sites.id",ondelete="SET NULL")),
        sa.Column("assigned_from",sa.DateTime(timezone=True),nullable=False), sa.Column("assigned_to",sa.DateTime(timezone=True)), sa.Column("purpose",sa.Text()),
        sa.Column("status",sa.String(24),nullable=False), sa.Column("assigned_by",sa.String(255),nullable=False), sa.Column("completed_by",sa.String(255)))
    for c in ("company_id","asset_id","employee_id","branch_id","site_id","status"): op.create_index(f"ix_fleet_assignments_{c}","fleet_assignments",[c])

    op.create_table("fleet_meter_readings",
        sa.Column("id",sa.Integer(),primary_key=True), sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),
        sa.Column("asset_id",sa.Integer(),sa.ForeignKey("fleet_assets.id",ondelete="CASCADE"),nullable=False), sa.Column("reading_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("odometer_km",sa.Numeric(14,2)), sa.Column("engine_hours",sa.Numeric(14,2)), sa.Column("source",sa.String(32),nullable=False), sa.Column("source_id",sa.String(80)),
        sa.Column("notes",sa.Text()), sa.Column("recorded_by",sa.String(255),nullable=False))
    op.create_index("ix_fleet_meter_readings_asset_id","fleet_meter_readings",["asset_id"]); op.create_index("ix_fleet_meter_readings_company_id","fleet_meter_readings",["company_id"]); op.create_index("ix_fleet_meter_readings_reading_at","fleet_meter_readings",["reading_at"])

    op.create_table("fleet_compliance",
        sa.Column("id",sa.Integer(),primary_key=True), sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),
        sa.Column("asset_id",sa.Integer(),sa.ForeignKey("fleet_assets.id",ondelete="CASCADE"),nullable=False), sa.Column("compliance_type",sa.String(40),nullable=False),
        sa.Column("reference_number",sa.String(120)), sa.Column("provider",sa.String(200)), sa.Column("issue_date",sa.Date()), sa.Column("expiry_date",sa.Date()),
        sa.Column("reminder_days",sa.Integer(),nullable=False), sa.Column("cost",sa.Numeric(18,2),nullable=False), sa.Column("document_id",sa.Integer(),sa.ForeignKey("documents.id",ondelete="SET NULL")),
        sa.Column("notes",sa.Text()), sa.Column("created_by",sa.String(255),nullable=False), sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    op.create_index("ix_fleet_compliance_company_id","fleet_compliance",["company_id"]); op.create_index("ix_fleet_compliance_asset_id","fleet_compliance",["asset_id"]); op.create_index("ix_fleet_compliance_compliance_type","fleet_compliance",["compliance_type"]); op.create_index("ix_fleet_compliance_expiry_date","fleet_compliance",["expiry_date"])

    op.create_table("fleet_inspections",
        sa.Column("id",sa.Integer(),primary_key=True), sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),
        sa.Column("asset_id",sa.Integer(),sa.ForeignKey("fleet_assets.id",ondelete="CASCADE"),nullable=False), sa.Column("branch_id",sa.Integer(),sa.ForeignKey("branches.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("site_id",sa.Integer(),sa.ForeignKey("sites.id",ondelete="SET NULL")), sa.Column("inspector_employee_id",sa.Integer(),sa.ForeignKey("employees.id",ondelete="SET NULL")),
        sa.Column("inspection_date",sa.Date(),nullable=False), sa.Column("inspection_type",sa.String(32),nullable=False), sa.Column("odometer_km",sa.Numeric(14,2)), sa.Column("engine_hours",sa.Numeric(14,2)),
        sa.Column("checklist",sa.JSON(),nullable=False), sa.Column("defects_found",sa.Boolean(),nullable=False), sa.Column("safe_to_operate",sa.Boolean(),nullable=False), sa.Column("status",sa.String(24),nullable=False),
        sa.Column("notes",sa.Text()), sa.Column("inspected_by",sa.String(255),nullable=False), sa.Column("approved_by",sa.String(255)), sa.Column("approved_at",sa.DateTime(timezone=True)), sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    for c in ("company_id","asset_id","branch_id","site_id","inspection_date","safe_to_operate","status"): op.create_index(f"ix_fleet_inspections_{c}","fleet_inspections",[c])

    op.create_table("fleet_defects",
        sa.Column("id",sa.Integer(),primary_key=True), sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),
        sa.Column("asset_id",sa.Integer(),sa.ForeignKey("fleet_assets.id",ondelete="CASCADE"),nullable=False), sa.Column("inspection_id",sa.Integer(),sa.ForeignKey("fleet_inspections.id",ondelete="SET NULL")),
        sa.Column("defect_number",sa.String(80),nullable=False), sa.Column("severity",sa.String(24),nullable=False), sa.Column("description",sa.Text(),nullable=False), sa.Column("status",sa.String(24),nullable=False),
        sa.Column("reported_at",sa.DateTime(timezone=True),nullable=False), sa.Column("reported_by",sa.String(255),nullable=False), sa.Column("resolved_at",sa.DateTime(timezone=True)), sa.Column("resolved_by",sa.String(255)), sa.Column("resolution_notes",sa.Text()))
    for c in ("company_id","asset_id","inspection_id","defect_number","severity","status"): op.create_index(f"ix_fleet_defects_{c}","fleet_defects",[c])

    op.create_table("fleet_fuel_transactions",
        sa.Column("id",sa.Integer(),primary_key=True), sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),
        sa.Column("asset_id",sa.Integer(),sa.ForeignKey("fleet_assets.id",ondelete="CASCADE"),nullable=False), sa.Column("branch_id",sa.Integer(),sa.ForeignKey("branches.id",ondelete="RESTRICT"),nullable=False), sa.Column("site_id",sa.Integer(),sa.ForeignKey("sites.id",ondelete="SET NULL")),
        sa.Column("employee_id",sa.Integer(),sa.ForeignKey("employees.id",ondelete="SET NULL")), sa.Column("transaction_date",sa.DateTime(timezone=True),nullable=False), sa.Column("fuel_type",sa.String(40),nullable=False),
        sa.Column("litres",sa.Numeric(14,3),nullable=False), sa.Column("unit_cost",sa.Numeric(18,4),nullable=False), sa.Column("total_cost",sa.Numeric(18,2),nullable=False), sa.Column("vendor",sa.String(200)),
        sa.Column("receipt_reference",sa.String(120)), sa.Column("odometer_km",sa.Numeric(14,2)), sa.Column("engine_hours",sa.Numeric(14,2)), sa.Column("full_tank",sa.Boolean(),nullable=False), sa.Column("notes",sa.Text()), sa.Column("recorded_by",sa.String(255),nullable=False))
    for c in ("company_id","asset_id","branch_id","site_id","transaction_date"): op.create_index(f"ix_fleet_fuel_transactions_{c}","fleet_fuel_transactions",[c])

    op.create_table("fleet_maintenance_plans",
        sa.Column("id",sa.Integer(),primary_key=True), sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False), sa.Column("asset_id",sa.Integer(),sa.ForeignKey("fleet_assets.id",ondelete="CASCADE"),nullable=False),
        sa.Column("name",sa.String(160),nullable=False), sa.Column("interval_km",sa.Numeric(14,2)), sa.Column("interval_hours",sa.Numeric(14,2)), sa.Column("interval_days",sa.Integer()), sa.Column("last_service_date",sa.Date()),
        sa.Column("last_odometer_km",sa.Numeric(14,2)), sa.Column("last_engine_hours",sa.Numeric(14,2)), sa.Column("next_due_date",sa.Date()), sa.Column("next_due_odometer_km",sa.Numeric(14,2)), sa.Column("next_due_engine_hours",sa.Numeric(14,2)),
        sa.Column("is_active",sa.Boolean(),nullable=False), sa.Column("notes",sa.Text()), sa.Column("created_by",sa.String(255),nullable=False))
    for c in ("company_id","asset_id","next_due_date"): op.create_index(f"ix_fleet_maintenance_plans_{c}","fleet_maintenance_plans",[c])

    op.create_table("fleet_maintenance_jobs",
        sa.Column("id",sa.Integer(),primary_key=True), sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False), sa.Column("asset_id",sa.Integer(),sa.ForeignKey("fleet_assets.id",ondelete="CASCADE"),nullable=False),
        sa.Column("plan_id",sa.Integer(),sa.ForeignKey("fleet_maintenance_plans.id",ondelete="SET NULL")), sa.Column("defect_id",sa.Integer(),sa.ForeignKey("fleet_defects.id",ondelete="SET NULL")), sa.Column("job_number",sa.String(80),nullable=False),
        sa.Column("maintenance_type",sa.String(32),nullable=False), sa.Column("description",sa.Text(),nullable=False), sa.Column("vendor",sa.String(200)), sa.Column("status",sa.String(24),nullable=False),
        sa.Column("requested_at",sa.DateTime(timezone=True),nullable=False), sa.Column("approved_by",sa.String(255)), sa.Column("approved_at",sa.DateTime(timezone=True)), sa.Column("started_at",sa.DateTime(timezone=True)), sa.Column("completed_at",sa.DateTime(timezone=True)),
        sa.Column("downtime_started_at",sa.DateTime(timezone=True)), sa.Column("downtime_ended_at",sa.DateTime(timezone=True)), sa.Column("odometer_km",sa.Numeric(14,2)), sa.Column("engine_hours",sa.Numeric(14,2)),
        sa.Column("labour_cost",sa.Numeric(18,2),nullable=False), sa.Column("parts_cost",sa.Numeric(18,2),nullable=False), sa.Column("other_cost",sa.Numeric(18,2),nullable=False), sa.Column("total_cost",sa.Numeric(18,2),nullable=False),
        sa.Column("invoice_reference",sa.String(120)), sa.Column("notes",sa.Text()), sa.Column("requested_by",sa.String(255),nullable=False), sa.UniqueConstraint("company_id","job_number",name="uq_fleet_job_company_number"))
    for c in ("company_id","asset_id","status"): op.create_index(f"ix_fleet_maintenance_jobs_{c}","fleet_maintenance_jobs",[c])

    op.create_table("fleet_audit_events",
        sa.Column("id",sa.Integer(),primary_key=True), sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False), sa.Column("asset_id",sa.Integer(),sa.ForeignKey("fleet_assets.id",ondelete="SET NULL")), sa.Column("branch_id",sa.Integer(),sa.ForeignKey("branches.id",ondelete="SET NULL")),
        sa.Column("actor",sa.String(255),nullable=False), sa.Column("action",sa.String(120),nullable=False), sa.Column("entity_type",sa.String(80),nullable=False), sa.Column("entity_id",sa.String(80)), sa.Column("detail",sa.JSON(),nullable=False), sa.Column("occurred_at",sa.DateTime(timezone=True),nullable=False))
    for c in ("company_id","asset_id","branch_id","action","occurred_at"): op.create_index(f"ix_fleet_audit_events_{c}","fleet_audit_events",[c])


def downgrade() -> None:
    for table in ["fleet_audit_events","fleet_maintenance_jobs","fleet_maintenance_plans","fleet_fuel_transactions","fleet_defects","fleet_inspections","fleet_compliance","fleet_meter_readings","fleet_assignments","fleet_assets"]:
        op.drop_table(table)
