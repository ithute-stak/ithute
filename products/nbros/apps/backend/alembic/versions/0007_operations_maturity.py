"""Deepen enterprise operations workflows.

Revision ID: 0007_operations_maturity
Revises: 0006_enterprise_operations
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_operations_maturity"
down_revision = "0006_enterprise_operations"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "approval_policies",
        sa.Column("id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("workflow_key", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("min_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("required_role", sa.String(64), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("branch_id", "workflow_key", "min_amount", name="uq_approval_policy_tier"),
    )
    op.create_table(
        "approval_routing",
        sa.Column("id", UUID, nullable=False),
        sa.Column("approval_request_id", UUID, nullable=False),
        sa.Column("policy_id", UUID, nullable=True),
        sa.Column("required_role", sa.String(64), nullable=False),
        sa.Column("stage", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["approval_request_id"], ["approval_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_id"], ["approval_policies.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("approval_request_id", name="uq_approval_routing_request"),
    )
    op.create_table(
        "goods_receipt_lines",
        sa.Column("id", UUID, nullable=False),
        sa.Column("goods_receipt_id", UUID, nullable=False),
        sa.Column("purchase_order_item_id", UUID, nullable=False),
        sa.Column("inventory_item_id", UUID, nullable=True),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False),
        sa.Column("unit_cost", sa.Numeric(14, 2), nullable=False),
        sa.ForeignKeyConstraint(["goods_receipt_id"], ["goods_receipts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["purchase_order_item_id"], ["purchase_order_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["inventory_item_id"], ["fleet_inventory_items.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "tyre_events",
        sa.Column("id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("tyre_id", UUID, nullable=False),
        sa.Column("vehicle_id", UUID, nullable=True),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("wheel_position", sa.String(80), nullable=True),
        sa.Column("odometer_km", sa.Integer(), nullable=True),
        sa.Column("tread_mm", sa.Numeric(6, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_by_profile_id", UUID, nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tyre_id"], ["tyre_assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recorded_by_profile_id"], ["profiles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "driver_training",
        sa.Column("id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("driver_id", UUID, nullable=False),
        sa.Column("course_name", sa.String(180), nullable=False),
        sa.Column("provider", sa.String(160), nullable=True),
        sa.Column("completed_date", sa.Date(), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("certificate_reference", sa.String(180), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["driver_id"], ["drivers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "fuel_analytics_settings",
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("anomaly_l_per_100km", sa.Numeric(8, 2), nullable=False),
        sa.Column("price_deviation_percent", sa.Numeric(6, 2), nullable=False),
        sa.Column("minimum_distance_km", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("branch_id"),
    )


def downgrade() -> None:
    op.drop_table("fuel_analytics_settings")
    op.drop_table("driver_training")
    op.drop_table("tyre_events")
    op.drop_table("goods_receipt_lines")
    op.drop_table("approval_routing")
    op.drop_table("approval_policies")
