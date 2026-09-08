"""phase 3 workforce and payroll preparation

Revision ID: 0004_phase3_workforce_payroll
Revises: 0003_phase2_access_security
Create Date: 2026-08-23
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_phase3_workforce_payroll"
down_revision = "0003_phase2_access_security"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "employees",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("employee_number", sa.String(64), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="SET NULL")),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.id", ondelete="SET NULL")),
        sa.Column("cost_centre_id", sa.Integer(), sa.ForeignKey("cost_centres.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(32)), sa.Column("first_name", sa.String(120), nullable=False),
        sa.Column("middle_names", sa.String(180)), sa.Column("last_name", sa.String(120), nullable=False),
        sa.Column("preferred_name", sa.String(120)), sa.Column("national_id", sa.String(100)),
        sa.Column("passport_number", sa.String(100)), sa.Column("date_of_birth", sa.Date()),
        sa.Column("gender", sa.String(32)), sa.Column("nationality", sa.String(80), nullable=False, server_default="Lesotho"),
        sa.Column("phone", sa.String(64)), sa.Column("alternate_phone", sa.String(64)),
        sa.Column("personal_email", sa.String(255)), sa.Column("work_email", sa.String(255)),
        sa.Column("physical_address", sa.Text()), sa.Column("postal_address", sa.Text()),
        sa.Column("job_title", sa.String(160), nullable=False),
        sa.Column("employment_type", sa.String(40), nullable=False, server_default="permanent"),
        sa.Column("employment_status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("hire_date", sa.Date(), nullable=False), sa.Column("termination_date", sa.Date()),
        sa.Column("probation_end_date", sa.Date()), sa.Column("pay_basis", sa.String(24), nullable=False, server_default="monthly"),
        sa.Column("basic_rate", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("standard_hours_per_week", sa.Numeric(8,2), nullable=False, server_default="45"),
        sa.Column("overtime_eligible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("bank_name", sa.String(160)), sa.Column("bank_account_name", sa.String(200)),
        sa.Column("bank_account_number", sa.String(120)), sa.Column("bank_branch_code", sa.String(64)),
        sa.Column("emergency_contact_name", sa.String(200)), sa.Column("emergency_contact_relationship", sa.String(80)),
        sa.Column("emergency_contact_phone", sa.String(64)), sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.String(255), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "employee_number", name="uq_employee_company_number"),
        sa.UniqueConstraint("company_id", "user_id", name="uq_employee_company_user"),
    )
    for name, cols in (("ix_employees_company_id",["company_id"]),("ix_employees_user_id",["user_id"]),("ix_employees_branch_id",["branch_id"]),("ix_employees_site_id",["site_id"]),("ix_employees_department_id",["department_id"]),("ix_employees_cost_centre_id",["cost_centre_id"]),("ix_employees_employment_status",["employment_status"]),("ix_employees_national_id",["national_id"])): op.create_index(name,"employees",cols)

    op.create_table("employment_contracts",
        sa.Column("id",sa.Integer(),primary_key=True), sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),
        sa.Column("employee_id",sa.Integer(),sa.ForeignKey("employees.id",ondelete="CASCADE"),nullable=False), sa.Column("contract_number",sa.String(80),nullable=False),
        sa.Column("contract_type",sa.String(40),nullable=False), sa.Column("start_date",sa.Date(),nullable=False), sa.Column("end_date",sa.Date()),
        sa.Column("job_title",sa.String(160),nullable=False), sa.Column("branch_id",sa.Integer(),sa.ForeignKey("branches.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("site_id",sa.Integer(),sa.ForeignKey("sites.id",ondelete="SET NULL")), sa.Column("department_id",sa.Integer(),sa.ForeignKey("departments.id",ondelete="SET NULL")),
        sa.Column("cost_centre_id",sa.Integer(),sa.ForeignKey("cost_centres.id",ondelete="SET NULL")), sa.Column("pay_basis",sa.String(24),nullable=False),
        sa.Column("basic_rate",sa.Numeric(18,2),nullable=False), sa.Column("hours_per_week",sa.Numeric(8,2),nullable=False), sa.Column("probation_end_date",sa.Date()),
        sa.Column("notice_period_days",sa.Integer()), sa.Column("status",sa.String(24),nullable=False), sa.Column("signed_employee_at",sa.DateTime(timezone=True)),
        sa.Column("signed_company_at",sa.DateTime(timezone=True)), sa.Column("notes",sa.Text()), sa.Column("created_by",sa.String(255),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False), sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint("company_id","contract_number",name="uq_contract_company_number"))
    op.create_index("ix_employment_contracts_employee_id","employment_contracts",["employee_id"])

    op.create_table("leave_types", sa.Column("id",sa.Integer(),primary_key=True), sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),
        sa.Column("code",sa.String(40),nullable=False),sa.Column("name",sa.String(120),nullable=False),sa.Column("paid",sa.Boolean(),nullable=False),sa.Column("annual_entitlement_days",sa.Numeric(8,2),nullable=False),
        sa.Column("accrual_method",sa.String(32),nullable=False),sa.Column("carry_forward_limit_days",sa.Numeric(8,2)),sa.Column("requires_attachment",sa.Boolean(),nullable=False),sa.Column("is_active",sa.Boolean(),nullable=False),
        sa.UniqueConstraint("company_id","code",name="uq_leave_type_company_code"))
    op.create_table("leave_balances", sa.Column("id",sa.Integer(),primary_key=True),sa.Column("employee_id",sa.Integer(),sa.ForeignKey("employees.id",ondelete="CASCADE"),nullable=False),
        sa.Column("leave_type_id",sa.Integer(),sa.ForeignKey("leave_types.id",ondelete="RESTRICT"),nullable=False),sa.Column("year",sa.Integer(),nullable=False),sa.Column("opening_days",sa.Numeric(8,2),nullable=False),
        sa.Column("accrued_days",sa.Numeric(8,2),nullable=False),sa.Column("taken_days",sa.Numeric(8,2),nullable=False),sa.Column("adjusted_days",sa.Numeric(8,2),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint("employee_id","leave_type_id","year",name="uq_leave_balance_employee_type_year"))
    op.create_table("leave_requests",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),
        sa.Column("employee_id",sa.Integer(),sa.ForeignKey("employees.id",ondelete="CASCADE"),nullable=False),sa.Column("leave_type_id",sa.Integer(),sa.ForeignKey("leave_types.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("start_date",sa.Date(),nullable=False),sa.Column("end_date",sa.Date(),nullable=False),sa.Column("days_requested",sa.Numeric(8,2),nullable=False),sa.Column("reason",sa.Text()),sa.Column("status",sa.String(24),nullable=False),
        sa.Column("requested_by",sa.String(255),nullable=False),sa.Column("requested_at",sa.DateTime(timezone=True),nullable=False),sa.Column("decided_by",sa.String(255)),sa.Column("decided_at",sa.DateTime(timezone=True)),sa.Column("decision_comment",sa.Text()))

    op.create_table("shifts",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),sa.Column("code",sa.String(40),nullable=False),
        sa.Column("name",sa.String(120),nullable=False),sa.Column("start_time",sa.Time(),nullable=False),sa.Column("end_time",sa.Time(),nullable=False),sa.Column("break_minutes",sa.Integer(),nullable=False),sa.Column("work_days",sa.JSON(),nullable=False),sa.Column("is_active",sa.Boolean(),nullable=False),
        sa.UniqueConstraint("company_id","code",name="uq_shift_company_code"))
    op.create_table("employee_shift_assignments",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("employee_id",sa.Integer(),sa.ForeignKey("employees.id",ondelete="CASCADE"),nullable=False),sa.Column("shift_id",sa.Integer(),sa.ForeignKey("shifts.id",ondelete="RESTRICT"),nullable=False),sa.Column("effective_from",sa.Date(),nullable=False),sa.Column("effective_to",sa.Date()))
    op.create_table("attendance_records",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),sa.Column("employee_id",sa.Integer(),sa.ForeignKey("employees.id",ondelete="CASCADE"),nullable=False),
        sa.Column("branch_id",sa.Integer(),sa.ForeignKey("branches.id",ondelete="RESTRICT"),nullable=False),sa.Column("site_id",sa.Integer(),sa.ForeignKey("sites.id",ondelete="SET NULL")),sa.Column("shift_id",sa.Integer(),sa.ForeignKey("shifts.id",ondelete="SET NULL")),
        sa.Column("work_date",sa.Date(),nullable=False),sa.Column("clock_in",sa.DateTime(timezone=True)),sa.Column("clock_out",sa.DateTime(timezone=True)),sa.Column("status",sa.String(32),nullable=False),sa.Column("regular_hours",sa.Numeric(8,2),nullable=False),sa.Column("overtime_hours",sa.Numeric(8,2),nullable=False),
        sa.Column("source",sa.String(32),nullable=False),sa.Column("notes",sa.Text()),sa.Column("recorded_by",sa.String(255),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint("employee_id","work_date",name="uq_attendance_employee_date"))
    op.create_table("timesheet_entries",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),sa.Column("employee_id",sa.Integer(),sa.ForeignKey("employees.id",ondelete="CASCADE"),nullable=False),
        sa.Column("branch_id",sa.Integer(),sa.ForeignKey("branches.id",ondelete="RESTRICT"),nullable=False),sa.Column("site_id",sa.Integer(),sa.ForeignKey("sites.id",ondelete="SET NULL")),sa.Column("cost_centre_id",sa.Integer(),sa.ForeignKey("cost_centres.id",ondelete="SET NULL")),sa.Column("work_date",sa.Date(),nullable=False),
        sa.Column("regular_hours",sa.Numeric(8,2),nullable=False),sa.Column("overtime_hours",sa.Numeric(8,2),nullable=False),sa.Column("task_description",sa.Text()),sa.Column("status",sa.String(24),nullable=False),sa.Column("submitted_at",sa.DateTime(timezone=True)),sa.Column("approved_by",sa.String(255)),sa.Column("approved_at",sa.DateTime(timezone=True)),sa.Column("created_by",sa.String(255),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))

    op.create_table("pay_components",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),sa.Column("code",sa.String(48),nullable=False),sa.Column("name",sa.String(160),nullable=False),
        sa.Column("component_type",sa.String(24),nullable=False),sa.Column("calculation_type",sa.String(32),nullable=False),sa.Column("default_value",sa.Numeric(18,4),nullable=False),sa.Column("taxable",sa.Boolean(),nullable=False),sa.Column("pensionable",sa.Boolean(),nullable=False),sa.Column("affects_net_pay",sa.Boolean(),nullable=False),sa.Column("is_active",sa.Boolean(),nullable=False),sa.UniqueConstraint("company_id","code",name="uq_pay_component_company_code"))
    op.create_table("employee_pay_components",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("employee_id",sa.Integer(),sa.ForeignKey("employees.id",ondelete="CASCADE"),nullable=False),sa.Column("component_id",sa.Integer(),sa.ForeignKey("pay_components.id",ondelete="RESTRICT"),nullable=False),sa.Column("value",sa.Numeric(18,4),nullable=False),sa.Column("effective_from",sa.Date(),nullable=False),sa.Column("effective_to",sa.Date()),sa.Column("notes",sa.Text()),sa.UniqueConstraint("employee_id","component_id",name="uq_employee_pay_component"))
    op.create_table("payroll_periods",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),sa.Column("code",sa.String(40),nullable=False),sa.Column("name",sa.String(120),nullable=False),sa.Column("start_date",sa.Date(),nullable=False),sa.Column("end_date",sa.Date(),nullable=False),sa.Column("pay_date",sa.Date(),nullable=False),sa.Column("status",sa.String(24),nullable=False),sa.UniqueConstraint("company_id","code",name="uq_payroll_period_company_code"))
    op.create_table("payroll_runs",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),sa.Column("period_id",sa.Integer(),sa.ForeignKey("payroll_periods.id",ondelete="RESTRICT"),nullable=False),sa.Column("branch_id",sa.Integer(),sa.ForeignKey("branches.id",ondelete="RESTRICT")),sa.Column("status",sa.String(24),nullable=False),sa.Column("employee_count",sa.Integer(),nullable=False),sa.Column("total_gross",sa.Numeric(18,2),nullable=False),sa.Column("total_deductions",sa.Numeric(18,2),nullable=False),sa.Column("total_net",sa.Numeric(18,2),nullable=False),sa.Column("prepared_by",sa.String(255),nullable=False),sa.Column("prepared_at",sa.DateTime(timezone=True),nullable=False),sa.Column("reviewed_by",sa.String(255)),sa.Column("reviewed_at",sa.DateTime(timezone=True)),sa.Column("approved_by",sa.String(255)),sa.Column("approved_at",sa.DateTime(timezone=True)),sa.UniqueConstraint("company_id","period_id","branch_id",name="uq_payroll_run_period_branch"))
    op.create_table("payroll_lines",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("run_id",sa.Integer(),sa.ForeignKey("payroll_runs.id",ondelete="CASCADE"),nullable=False),sa.Column("employee_id",sa.Integer(),sa.ForeignKey("employees.id",ondelete="RESTRICT"),nullable=False),sa.Column("branch_id",sa.Integer(),sa.ForeignKey("branches.id",ondelete="RESTRICT"),nullable=False),sa.Column("site_id",sa.Integer(),sa.ForeignKey("sites.id",ondelete="SET NULL")),sa.Column("cost_centre_id",sa.Integer(),sa.ForeignKey("cost_centres.id",ondelete="SET NULL")),sa.Column("regular_hours",sa.Numeric(8,2),nullable=False),sa.Column("overtime_hours",sa.Numeric(8,2),nullable=False),sa.Column("basic_pay",sa.Numeric(18,2),nullable=False),sa.Column("earnings",sa.Numeric(18,2),nullable=False),sa.Column("deductions",sa.Numeric(18,2),nullable=False),sa.Column("gross_pay",sa.Numeric(18,2),nullable=False),sa.Column("net_pay",sa.Numeric(18,2),nullable=False),sa.Column("component_breakdown",sa.JSON(),nullable=False),sa.Column("warnings",sa.JSON(),nullable=False),sa.UniqueConstraint("run_id","employee_id",name="uq_payroll_line_run_employee"))
    op.create_table("workforce_audit_events",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),sa.Column("employee_id",sa.Integer(),sa.ForeignKey("employees.id",ondelete="SET NULL")),sa.Column("branch_id",sa.Integer(),sa.ForeignKey("branches.id",ondelete="SET NULL")),sa.Column("actor",sa.String(255),nullable=False),sa.Column("action",sa.String(80),nullable=False),sa.Column("entity_type",sa.String(80),nullable=False),sa.Column("entity_id",sa.String(100)),sa.Column("detail",sa.JSON(),nullable=False),sa.Column("occurred_at",sa.DateTime(timezone=True),nullable=False))

    for table, columns in {"leave_requests":["company_id","employee_id","status"],"attendance_records":["company_id","employee_id","branch_id","work_date"],"timesheet_entries":["company_id","employee_id","branch_id","work_date","status"],"payroll_runs":["company_id","period_id","branch_id","status"],"payroll_lines":["run_id","employee_id"],"workforce_audit_events":["company_id","employee_id","branch_id","action","occurred_at"]}.items():
        for column in columns: op.create_index(f"ix_{table}_{column}",table,[column])


def downgrade() -> None:
    for table in ["workforce_audit_events","payroll_lines","payroll_runs","payroll_periods","employee_pay_components","pay_components","timesheet_entries","attendance_records","employee_shift_assignments","shifts","leave_requests","leave_balances","leave_types","employment_contracts","employees"]:
        op.drop_table(table)
