"""Fleet service-kit inventory.

Revision ID: 0004_fleet_inventory
Revises: 0003_fleet_alerts
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_fleet_inventory"
down_revision = "0003_fleet_alerts"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "fleet_inventory_items",
        sa.Column("id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("sku", sa.String(80), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("category", sa.String(80), nullable=False, server_default="service_kit"),
        sa.Column("quantity_on_hand", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("reorder_level", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("unit", sa.String(40), nullable=False, server_default="unit"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("quantity_on_hand >= 0", name="ck_fleet_inventory_nonnegative"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("branch_id", "sku", name="uq_fleet_inventory_branch_sku"),
    )
    op.create_index("ix_fleet_inventory_items_branch_id", "fleet_inventory_items", ["branch_id"])
    op.create_index("ix_fleet_inventory_items_name", "fleet_inventory_items", ["name"])

    op.create_table(
        "fleet_inventory_movements",
        sa.Column("id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("item_id", UUID, nullable=False),
        sa.Column("quantity_delta", sa.Numeric(12, 2), nullable=False),
        sa.Column("movement_type", sa.String(40), nullable=False),
        sa.Column("reference_type", sa.String(80)),
        sa.Column("reference_id", sa.String(120)),
        sa.Column("notes", sa.Text()),
        sa.Column("recorded_by_profile_id", UUID),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("quantity_delta <> 0", name="ck_fleet_inventory_movement_nonzero"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["fleet_inventory_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recorded_by_profile_id"], ["profiles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fleet_inventory_movements_branch_id", "fleet_inventory_movements", ["branch_id"])
    op.create_index("ix_fleet_inventory_movements_item_id", "fleet_inventory_movements", ["item_id"])
    op.create_index("ix_fleet_inventory_movements_recorded_by_profile_id", "fleet_inventory_movements", ["recorded_by_profile_id"])


def downgrade() -> None:
    op.drop_index("ix_fleet_inventory_movements_recorded_by_profile_id", table_name="fleet_inventory_movements")
    op.drop_index("ix_fleet_inventory_movements_item_id", table_name="fleet_inventory_movements")
    op.drop_index("ix_fleet_inventory_movements_branch_id", table_name="fleet_inventory_movements")
    op.drop_table("fleet_inventory_movements")
    op.drop_index("ix_fleet_inventory_items_name", table_name="fleet_inventory_items")
    op.drop_index("ix_fleet_inventory_items_branch_id", table_name="fleet_inventory_items")
    op.drop_table("fleet_inventory_items")
