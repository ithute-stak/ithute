"""phase 8 procurement and stores

Revision ID: 0010_phase8_procurement
Revises: 0009_phase7_site_ops
Create Date: 2026-08-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0010_phase8_procurement"
down_revision = "0009_phase7_site_ops"
branch_labels = None
depends_on = None


def _indexes(table: str, names: tuple[str, ...]) -> None:
    for name in names:
        op.create_index(f"ix_{table}_{name}", table, [name])


def upgrade() -> None:
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("supplier_code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("registration_number", sa.String(120)),
        sa.Column("tax_number", sa.String(120)),
        sa.Column("contact_name", sa.String(180)),
        sa.Column("email", sa.String(255)),
        sa.Column("phone", sa.String(64)),
        sa.Column("address", sa.Text()),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.Column("payment_terms_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("compliance_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("approved_by", sa.String(255)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "supplier_code", name="uq_supplier_company_code"),
    )
    _indexes("suppliers", ("company_id", "supplier_code", "name", "status"))

    op.create_table(
        "store_locations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="SET NULL")),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("location_type", sa.String(32), nullable=False, server_default="branch_store"),
        sa.Column("responsible_employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="SET NULL")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "code", name="uq_store_location_company_code"),
    )
    _indexes("store_locations", ("company_id", "branch_id", "site_id", "responsible_employee_id"))

    op.create_table(
        "stock_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sku", sa.String(80), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("category", sa.String(100)),
        sa.Column("unit", sa.String(40), nullable=False, server_default="each"),
        sa.Column("reorder_level", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("max_level", sa.Numeric(18, 3)),
        sa.Column("default_unit_cost", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("stock_controlled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "sku", name="uq_stock_item_company_sku"),
    )
    _indexes("stock_items", ("company_id", "sku", "description", "category"))

    op.create_table(
        "stock_balances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("store_locations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stock_item_id", sa.Integer(), sa.ForeignKey("stock_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quantity_on_hand", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("quantity_reserved", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("average_unit_cost", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("location_id", "stock_item_id", name="uq_stock_balance_location_item"),
    )
    _indexes("stock_balances", ("company_id", "location_id", "stock_item_id"))

    op.create_table(
        "procurement_requisitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="SET NULL")),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="SET NULL")),
        sa.Column("cost_centre_id", sa.Integer(), sa.ForeignKey("cost_centres.id", ondelete="SET NULL")),
        sa.Column("requisition_number", sa.String(80), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("required_by", sa.Date(), nullable=False),
        sa.Column("priority", sa.String(24), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("estimated_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("approval_request_id", sa.Integer(), sa.ForeignKey("approval_requests.id", ondelete="SET NULL")),
        sa.Column("requested_by", sa.String(255), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "requisition_number", name="uq_procurement_requisition_number"),
    )
    _indexes("procurement_requisitions", ("company_id", "branch_id", "site_id", "project_id", "cost_centre_id", "requisition_number", "required_by", "status", "approval_request_id"))

    op.create_table(
        "procurement_requisition_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requisition_id", sa.Integer(), sa.ForeignKey("procurement_requisitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stock_item_id", sa.Integer(), sa.ForeignKey("stock_items.id", ondelete="SET NULL")),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("specification", sa.Text()),
        sa.Column("quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("unit", sa.String(40), nullable=False),
        sa.Column("estimated_unit_cost", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("estimated_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text()),
    )
    _indexes("procurement_requisition_lines", ("company_id", "requisition_id", "stock_item_id"))

    op.create_table(
        "supplier_quotations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requisition_id", sa.Integer(), sa.ForeignKey("procurement_requisitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quote_reference", sa.String(120), nullable=False),
        sa.Column("quote_date", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date()),
        sa.Column("delivery_days", sa.Integer()),
        sa.Column("subtotal", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(24), nullable=False, server_default="received"),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("notes", sa.Text()),
        sa.Column("recorded_by", sa.String(255), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("requisition_id", "supplier_id", "quote_reference", name="uq_quote_requisition_supplier_reference"),
    )
    _indexes("supplier_quotations", ("company_id", "requisition_id", "supplier_id", "status"))

    op.create_table(
        "supplier_quotation_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quotation_id", sa.Integer(), sa.ForeignKey("supplier_quotations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requisition_line_id", sa.Integer(), sa.ForeignKey("procurement_requisition_lines.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("stock_item_id", sa.Integer(), sa.ForeignKey("stock_items.id", ondelete="SET NULL")),
        sa.Column("quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("line_total", sa.Numeric(18, 2), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.UniqueConstraint("quotation_id", "requisition_line_id", name="uq_quote_line_requisition_line"),
    )
    _indexes("supplier_quotation_lines", ("company_id", "quotation_id", "requisition_line_id", "stock_item_id"))

    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="SET NULL")),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="SET NULL")),
        sa.Column("cost_centre_id", sa.Integer(), sa.ForeignKey("cost_centres.id", ondelete="SET NULL")),
        sa.Column("requisition_id", sa.Integer(), sa.ForeignKey("procurement_requisitions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quotation_id", sa.Integer(), sa.ForeignKey("supplier_quotations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("delivery_location_id", sa.Integer(), sa.ForeignKey("store_locations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("purchase_order_number", sa.String(80), nullable=False),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("expected_delivery_date", sa.Date()),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("subtotal", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("approval_request_id", sa.Integer(), sa.ForeignKey("approval_requests.id", ondelete="SET NULL")),
        sa.Column("terms", sa.Text()),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("company_id", "purchase_order_number", name="uq_purchase_order_number"),
    )
    _indexes("purchase_orders", ("company_id", "branch_id", "site_id", "project_id", "cost_centre_id", "requisition_id", "quotation_id", "supplier_id", "delivery_location_id", "purchase_order_number", "expected_delivery_date", "status", "approval_request_id"))

    op.create_table(
        "purchase_order_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purchase_order_id", sa.Integer(), sa.ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requisition_line_id", sa.Integer(), sa.ForeignKey("procurement_requisition_lines.id", ondelete="SET NULL")),
        sa.Column("stock_item_id", sa.Integer(), sa.ForeignKey("stock_items.id", ondelete="SET NULL")),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("quantity_ordered", sa.Numeric(18, 3), nullable=False),
        sa.Column("quantity_received", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("unit", sa.String(40), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("line_total", sa.Numeric(18, 2), nullable=False),
    )
    _indexes("purchase_order_lines", ("company_id", "purchase_order_id", "requisition_line_id", "stock_item_id"))

    op.create_table(
        "goods_receipts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purchase_order_id", sa.Integer(), sa.ForeignKey("purchase_orders.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("store_locations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("goods_receipt_number", sa.String(80), nullable=False),
        sa.Column("receipt_date", sa.Date(), nullable=False),
        sa.Column("delivery_reference", sa.String(160)),
        sa.Column("status", sa.String(24), nullable=False, server_default="posted"),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("received_by", sa.String(255), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "goods_receipt_number", name="uq_goods_receipt_number"),
    )
    _indexes("goods_receipts", ("company_id", "purchase_order_id", "location_id", "goods_receipt_number", "receipt_date", "status"))

    op.create_table(
        "goods_receipt_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("goods_receipt_id", sa.Integer(), sa.ForeignKey("goods_receipts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purchase_order_line_id", sa.Integer(), sa.ForeignKey("purchase_order_lines.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("stock_item_id", sa.Integer(), sa.ForeignKey("stock_items.id", ondelete="SET NULL")),
        sa.Column("quantity_received", sa.Numeric(18, 3), nullable=False),
        sa.Column("quantity_accepted", sa.Numeric(18, 3), nullable=False),
        sa.Column("quantity_rejected", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=False),
        sa.Column("notes", sa.Text()),
    )
    _indexes("goods_receipt_lines", ("company_id", "goods_receipt_id", "purchase_order_line_id", "stock_item_id"))

    op.create_table(
        "stock_movements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("store_locations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("stock_item_id", sa.Integer(), sa.ForeignKey("stock_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="SET NULL")),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="SET NULL")),
        sa.Column("cost_centre_id", sa.Integer(), sa.ForeignKey("cost_centres.id", ondelete="SET NULL")),
        sa.Column("site_material_entry_id", sa.Integer(), sa.ForeignKey("site_material_entries.id", ondelete="SET NULL")),
        sa.Column("movement_type", sa.String(32), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("total_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("reference_type", sa.String(64)),
        sa.Column("reference_id", sa.String(100)),
        sa.Column("reason", sa.Text()),
        sa.Column("recorded_by", sa.String(255), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    _indexes("stock_movements", ("company_id", "location_id", "stock_item_id", "project_id", "site_id", "cost_centre_id", "site_material_entry_id", "movement_type", "reference_type", "reference_id", "recorded_at"))

    op.create_table(
        "stock_transfers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_location_id", sa.Integer(), sa.ForeignKey("store_locations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("to_location_id", sa.Integer(), sa.ForeignKey("store_locations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("transfer_number", sa.String(80), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("requested_by", sa.String(255), nullable=False),
        sa.Column("shipped_by", sa.String(255)),
        sa.Column("received_by", sa.String(255)),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("shipped_at", sa.DateTime(timezone=True)),
        sa.Column("received_at", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.Text()),
        sa.UniqueConstraint("company_id", "transfer_number", name="uq_stock_transfer_number"),
    )
    _indexes("stock_transfers", ("company_id", "from_location_id", "to_location_id", "transfer_number", "status"))

    op.create_table(
        "stock_transfer_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("transfer_id", sa.Integer(), sa.ForeignKey("stock_transfers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stock_item_id", sa.Integer(), sa.ForeignKey("stock_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quantity_requested", sa.Numeric(18, 3), nullable=False),
        sa.Column("quantity_shipped", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("quantity_received", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.UniqueConstraint("transfer_id", "stock_item_id", name="uq_stock_transfer_item"),
    )
    _indexes("stock_transfer_lines", ("company_id", "transfer_id", "stock_item_id"))

    op.create_table(
        "procurement_audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="SET NULL")),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="SET NULL")),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.String(100)),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    _indexes("procurement_audit_events", ("company_id", "branch_id", "site_id", "action", "entity_type", "entity_id", "occurred_at"))


def downgrade() -> None:
    for table in (
        "procurement_audit_events", "stock_transfer_lines", "stock_transfers", "stock_movements",
        "goods_receipt_lines", "goods_receipts", "purchase_order_lines", "purchase_orders",
        "supplier_quotation_lines", "supplier_quotations", "procurement_requisition_lines",
        "procurement_requisitions", "stock_balances", "stock_items", "store_locations", "suppliers",
    ):
        op.drop_table(table)
