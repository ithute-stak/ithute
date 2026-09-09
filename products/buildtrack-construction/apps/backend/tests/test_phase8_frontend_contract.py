from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
BACKEND = ROOT / "backend"


def test_phase8_routes_models_and_migration_are_registered() -> None:
    router = (BACKEND / "app/api/v1/router.py").read_text()
    models = (BACKEND / "app/models/__init__.py").read_text()
    domain = (BACKEND / "app/models/procurement.py").read_text()
    api = (BACKEND / "app/api/v1/procurement.py").read_text()
    safe = (BACKEND / "app/api/v1/procurement_safe.py").read_text()
    reporting = (BACKEND / "app/api/v1/procurement_reporting.py").read_text()
    migration = (BACKEND / "alembic/versions/0010_phase8_procurement_stores.py").read_text()

    assert "procurement_reporting_router" in router and "procurement_safe_router" in router and "procurement_router" in router
    assert router.index("include_router(procurement_reporting_router") < router.index("include_router(procurement_safe_router") < router.index("include_router(procurement_router")
    assert '"phase_8"' in router and "weighted_average_stock_balances" in router
    assert 'revision = "0010_phase8_procurement"' in migration
    assert 'down_revision = "0009_phase7_site_ops"' in migration
    assert len("0010_phase8_procurement") <= 32

    for table in (
        "suppliers", "store_locations", "stock_items", "stock_balances", "procurement_requisitions",
        "procurement_requisition_lines", "supplier_quotations", "supplier_quotation_lines", "purchase_orders",
        "purchase_order_lines", "goods_receipts", "goods_receipt_lines", "stock_movements",
        "stock_transfers", "stock_transfer_lines", "procurement_audit_events",
    ):
        assert f'"{table}"' in migration

    for model in (
        "Supplier", "StoreLocation", "StockItem", "StockBalance", "ProcurementRequisition",
        "ProcurementRequisitionLine", "SupplierQuotation", "SupplierQuotationLine", "PurchaseOrder",
        "PurchaseOrderLine", "GoodsReceipt", "GoodsReceiptLine", "StockMovement", "StockTransfer",
        "StockTransferLine", "ProcurementAuditEvent",
    ):
        assert model in models and f"class {model}" in domain

    for contract in (
        '"PROCUREMENT_REQUISITION"', '"PURCHASE_ORDER"', '"REQUISITION"', '"GOODS_RECEIPT"',
        '"STOCK_TRANSFER"', '"/requisitions/{requisition_id:int}/submit"', '"/quotations/{quotation_id:int}/select"',
        '"/purchase-orders/{purchase_order_id:int}/receipts"', '"/stock/issues"', '"/stock/returns"',
        '"/stock/adjustments"', '"/transfers/{transfer_id:int}/ship"', '"/transfers/{transfer_id:int}/receive"',
        '"/exports/stock.csv"', '"/exports/purchase-orders.csv"',
    ):
        assert contract in api
    assert "Insufficient stock" in api and "average_unit_cost" in api
    assert "minimum_quotes" in api and "low_value_quote_waiver" in api and "po_overrun_tolerance_pct" in safe
    assert "Company-level stores.manage permission is required to create global stock items" in safe
    assert "A site store may only transact for its own site" in safe
    assert "Received quantity exceeds the outstanding PO quantity" in safe
    assert "ProjectSiteLink" in safe and "Phase 7 material evidence" in safe
    assert '"/stock/movements"' in reporting and '"/purchase-orders/{purchase_order_id:int}"' in reporting


def test_phase8_browser_workspaces_cover_operational_and_control_contracts() -> None:
    page = (FRONTEND / "app/procurement/page.tsx").read_text()
    control = (FRONTEND / "app/procurement/control/page.tsx").read_text()
    navigation = (FRONTEND / "app/components/buildtrack-navigation.tsx").read_text()
    readme = (ROOT.parent / "README.md").read_text() if (ROOT.parent / "README.md").exists() else (ROOT / "../README.md").resolve().read_text()

    for text in (
        "Procurement & Stores", "Suppliers", "Stores & items", "Stock", "Requisitions", "Quotations",
        "Purchase orders", "Receiving", "Transfers", "Issue stock to site / project", "Supplier quote comparison",
        "Create PO from selected quote", "Goods receiving", "/procurement/requisitions/", "/procurement/purchase-orders/",
        "/procurement/stock/issues", "/procurement/transfers",
    ):
        assert text in page
    for text in (
        "Procurement Control", "Requisition approval queue", "Purchase order approval queue",
        "Procurement governance policy", "Controlled stock adjustment", "Low-stock watch",
        "/procurement/approvals/", "/procurement/policy/current", "/procurement/stock/adjustments",
    ):
        assert text in control
    assert 'href: "/procurement"' in navigation and 'href: "/procurement/control"' in navigation
    assert "Phase 8 — Procurement & Stores: complete" in readme
    assert "does **not** fabricate quotations" in readme
