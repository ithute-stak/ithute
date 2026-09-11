"""Fleet management module and company-branch scoping.

Revision ID: 0002_fleet_management
Revises: 0001_foundation
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_fleet_management"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "branches",
        sa.Column("id", UUID, nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("location", sa.String(255)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_branches_code", "branches", ["code"])

    op.create_table(
        "branch_modules",
        sa.Column("id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("module_key", sa.String(80), nullable=False, server_default="fleet"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("branch_id", "module_key", name="uq_branch_module"),
    )
    op.create_index("ix_branch_modules_branch_id", "branch_modules", ["branch_id"])

    op.create_table(
        "profile_branch_access",
        sa.Column("id", UUID, nullable=False),
        sa.Column("profile_id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("role", sa.String(64), nullable=False, server_default="viewer"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_id", "branch_id", name="uq_profile_branch_access"),
    )
    op.create_index("ix_profile_branch_access_profile_id", "profile_branch_access", ["profile_id"])
    op.create_index("ix_profile_branch_access_branch_id", "profile_branch_access", ["branch_id"])

    op.create_table(
        "fleet_settings",
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("document_warning_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("document_critical_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("service_warning_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("service_mileage_warning", sa.Integer(), nullable=False, server_default="1000"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("branch_id"),
    )

    op.create_table(
        "document_requirements",
        sa.Column("id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("document_type", sa.String(100), nullable=False),
        sa.Column("vehicle_type", sa.String(100)),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("warning_days", sa.Integer()),
        sa.Column("critical_days", sa.Integer()),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("branch_id", "document_type", "vehicle_type", name="uq_document_requirement"),
    )
    op.create_index("ix_document_requirements_branch_id", "document_requirements", ["branch_id"])

    op.create_table(
        "vehicle_type_license_rules",
        sa.Column("id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("vehicle_type", sa.String(100), nullable=False),
        sa.Column("license_category", sa.String(80), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("branch_id", "vehicle_type", "license_category", name="uq_vehicle_type_license"),
    )
    op.create_index("ix_vehicle_type_license_rules_branch_id", "vehicle_type_license_rules", ["branch_id"])

    op.create_table(
        "service_kit_rules",
        sa.Column("id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("make", sa.String(100), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("service_type", sa.String(100), nullable=False),
        sa.Column("kit_name", sa.String(160), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("branch_id", "make", "model", "service_type", name="uq_service_kit_rule"),
    )
    op.create_index("ix_service_kit_rules_branch_id", "service_kit_rules", ["branch_id"])

    op.create_table(
        "vehicles",
        sa.Column("id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("registration_plate", sa.String(50), nullable=False),
        sa.Column("make", sa.String(100), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("vehicle_type", sa.String(100), nullable=False),
        sa.Column("year", sa.Integer()),
        sa.Column("vin", sa.String(100)),
        sa.Column("engine_number", sa.String(100)),
        sa.Column("fuel_type", sa.String(40)),
        sa.Column("current_mileage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("purchase_date", sa.Date()),
        sa.Column("purchase_price", sa.Numeric(14, 2)),
        sa.Column("purchase_supplier", sa.String(160)),
        sa.Column("mechanical_condition", sa.String(32), nullable=False, server_default="operational"),
        sa.Column("notes", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("registration_plate"),
        sa.UniqueConstraint("vin"),
    )
    op.create_index("ix_vehicles_branch_id", "vehicles", ["branch_id"])
    op.create_index("ix_vehicles_registration_plate", "vehicles", ["registration_plate"])
    op.create_index("ix_vehicles_vehicle_type", "vehicles", ["vehicle_type"])

    op.create_table(
        "vehicle_documents",
        sa.Column("id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("vehicle_id", UUID, nullable=False),
        sa.Column("document_type", sa.String(100), nullable=False),
        sa.Column("document_number", sa.String(160)),
        sa.Column("issue_date", sa.Date()),
        sa.Column("expiry_date", sa.Date()),
        sa.Column("file_url", sa.String(1024)),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vehicle_documents_branch_id", "vehicle_documents", ["branch_id"])
    op.create_index("ix_vehicle_documents_vehicle_id", "vehicle_documents", ["vehicle_id"])
    op.create_index("ix_vehicle_documents_document_type", "vehicle_documents", ["document_type"])

    op.create_table(
        "service_records",
        sa.Column("id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("vehicle_id", UUID, nullable=False),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("mileage", sa.Integer(), nullable=False),
        sa.Column("service_type", sa.String(100), nullable=False),
        sa.Column("parts_used", sa.Text()),
        sa.Column("service_kit", sa.String(160)),
        sa.Column("mechanic", sa.String(160)),
        sa.Column("cost", sa.Numeric(14, 2)),
        sa.Column("next_service_date", sa.Date()),
        sa.Column("next_service_mileage", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_service_records_branch_id", "service_records", ["branch_id"])
    op.create_index("ix_service_records_vehicle_id", "service_records", ["vehicle_id"])

    op.create_table(
        "mechanical_faults",
        sa.Column("id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("vehicle_id", UUID, nullable=False),
        sa.Column("severity", sa.String(32), nullable=False, server_default="attention"),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mechanical_faults_branch_id", "mechanical_faults", ["branch_id"])
    op.create_index("ix_mechanical_faults_vehicle_id", "mechanical_faults", ["vehicle_id"])

    op.create_table(
        "inspections",
        sa.Column("id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("vehicle_id", UUID, nullable=False),
        sa.Column("inspection_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("inspector", sa.String(160)),
        sa.Column("notes", sa.Text()),
        sa.Column("next_inspection_date", sa.Date()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inspections_branch_id", "inspections", ["branch_id"])
    op.create_index("ix_inspections_vehicle_id", "inspections", ["vehicle_id"])

    op.create_table(
        "drivers",
        sa.Column("id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("auth_user_id", UUID),
        sa.Column("employee_number", sa.String(80)),
        sa.Column("full_name", sa.String(160), nullable=False),
        sa.Column("license_number", sa.String(100), nullable=False),
        sa.Column("license_category", sa.String(80), nullable=False),
        sa.Column("license_expiry", sa.Date(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("branch_id", "license_number", name="uq_branch_driver_license"),
    )
    op.create_index("ix_drivers_branch_id", "drivers", ["branch_id"])
    op.create_index("ix_drivers_auth_user_id", "drivers", ["auth_user_id"])
    op.create_index("ix_drivers_employee_number", "drivers", ["employee_number"])

    op.create_table(
        "maintenance_work_orders",
        sa.Column("id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("vehicle_id", UUID, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("expected_release_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_maintenance_work_orders_branch_id", "maintenance_work_orders", ["branch_id"])
    op.create_index("ix_maintenance_work_orders_vehicle_id", "maintenance_work_orders", ["vehicle_id"])

    op.create_table(
        "vehicle_assignments",
        sa.Column("id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("vehicle_id", UUID, nullable=False),
        sa.Column("driver_id", UUID, nullable=False),
        sa.Column("purpose", sa.String(255)),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["driver_id"], ["drivers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vehicle_assignments_branch_id", "vehicle_assignments", ["branch_id"])
    op.create_index("ix_vehicle_assignments_vehicle_id", "vehicle_assignments", ["vehicle_id"])
    op.create_index("ix_vehicle_assignments_driver_id", "vehicle_assignments", ["driver_id"])

    op.create_table(
        "trips",
        sa.Column("id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("vehicle_id", UUID, nullable=False),
        sa.Column("driver_id", UUID, nullable=False),
        sa.Column("destination", sa.String(255), nullable=False),
        sa.Column("purpose", sa.String(255)),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expected_return_at", sa.DateTime(timezone=True)),
        sa.Column("actual_return_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["driver_id"], ["drivers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trips_branch_id", "trips", ["branch_id"])
    op.create_index("ix_trips_vehicle_id", "trips", ["vehicle_id"])
    op.create_index("ix_trips_driver_id", "trips", ["driver_id"])

    op.create_table(
        "vehicle_reservations",
        sa.Column("id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("vehicle_id", UUID, nullable=False),
        sa.Column("driver_id", UUID),
        sa.Column("purpose", sa.String(255)),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["driver_id"], ["drivers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vehicle_reservations_branch_id", "vehicle_reservations", ["branch_id"])
    op.create_index("ix_vehicle_reservations_vehicle_id", "vehicle_reservations", ["vehicle_id"])
    op.create_index("ix_vehicle_reservations_driver_id", "vehicle_reservations", ["driver_id"])

    op.create_table(
        "fuel_records",
        sa.Column("id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("vehicle_id", UUID, nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("mileage", sa.Integer(), nullable=False),
        sa.Column("litres", sa.Numeric(10, 2), nullable=False),
        sa.Column("cost", sa.Numeric(14, 2)),
        sa.Column("station", sa.String(160)),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fuel_records_branch_id", "fuel_records", ["branch_id"])
    op.create_index("ix_fuel_records_vehicle_id", "fuel_records", ["vehicle_id"])

    op.create_table(
        "accident_records",
        sa.Column("id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("vehicle_id", UUID, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location", sa.String(255)),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("driver_id", UUID),
        sa.Column("reference_number", sa.String(160)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["driver_id"], ["drivers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_accident_records_branch_id", "accident_records", ["branch_id"])
    op.create_index("ix_accident_records_vehicle_id", "accident_records", ["vehicle_id"])
    op.create_index("ix_accident_records_driver_id", "accident_records", ["driver_id"])


def downgrade() -> None:
    for table in [
        "accident_records",
        "fuel_records",
        "vehicle_reservations",
        "trips",
        "vehicle_assignments",
        "maintenance_work_orders",
        "drivers",
        "inspections",
        "mechanical_faults",
        "service_records",
        "vehicle_documents",
        "vehicles",
        "service_kit_rules",
        "vehicle_type_license_rules",
        "document_requirements",
        "fleet_settings",
        "profile_branch_access",
        "branch_modules",
        "branches",
    ]:
        op.drop_table(table)
