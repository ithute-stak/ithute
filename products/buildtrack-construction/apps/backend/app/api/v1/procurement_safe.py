from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.procurement import (
    POInput,
    ReceiptInput,
    StockIssueInput,
    StockItemInput,
    StockReturnInput,
    apply_stock,
    audit,
    commit,
    create_item as base_create_item,
    create_purchase_order as base_create_purchase_order,
    ensure_document,
    issue_reference,
    location_or_404,
    money,
    policy,
    qty,
    select_quotation as base_select_quotation,
    unit_cost,
)
from app.db.session import get_db
from app.models import (
    CostCentre,
    GoodsReceipt,
    GoodsReceiptLine,
    Project,
    ProjectSiteLink,
    PurchaseOrder,
    PurchaseOrderLine,
    Site,
    SiteMaterialEntry,
    StockItem,
    StoreLocation,
    SupplierQuotation,
)
from app.security.access import Principal, current_principal

router = APIRouter(prefix="/procurement", tags=["Phase 8 - Procurement & Stores Control"])


def validate_operational_scope(db: Session, principal: Principal, location: StoreLocation, *, site_id: int | None, project_id: int | None, cost_centre_id: int | None) -> None:
    company_id = principal.user.company_id
    if location.site_id is not None and site_id != location.site_id:
        raise HTTPException(status_code=422, detail="A site store may only transact for its own site")
    if site_id is not None:
        site = db.get(Site, site_id)
        if not site or site.company_id != company_id or site.branch_id != location.branch_id:
            raise HTTPException(status_code=422, detail="Transaction site is outside the store branch")
    if project_id is not None:
        project = db.get(Project, project_id)
        if not project or project.company_id != company_id or project.branch_id != location.branch_id:
            raise HTTPException(status_code=422, detail="Transaction project is outside the store branch")
        if site_id is not None:
            linked = db.scalar(select(ProjectSiteLink.id).where(ProjectSiteLink.project_id == project.id, ProjectSiteLink.site_id == site_id))
            if not linked:
                raise HTTPException(status_code=422, detail="Transaction site is not linked to the selected project")
    if cost_centre_id is not None:
        centre = db.get(CostCentre, cost_centre_id)
        if not centre or centre.company_id != company_id:
            raise HTTPException(status_code=422, detail="Cost centre is invalid")
        if centre.branch_id is not None and centre.branch_id != location.branch_id:
            raise HTTPException(status_code=422, detail="Cost centre is outside the store branch")
        if site_id is not None and centre.site_id is not None and centre.site_id != site_id:
            raise HTTPException(status_code=422, detail="Cost centre is outside the selected site")


@router.post("/items", status_code=201)
def create_stock_item_safe(payload: StockItemInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if not principal.has_company_permission("stores.manage"):
        raise HTTPException(status_code=403, detail="Company-level stores.manage permission is required to create global stock items")
    if payload.max_level is not None and payload.max_level < payload.reorder_level:
        raise HTTPException(status_code=422, detail="Maximum stock level cannot be below the reorder level")
    return base_create_item(payload=payload, db=db, principal=principal)


@router.post("/quotations/{quotation_id:int}/select")
def select_quotation_safe(quotation_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    quote = db.get(SupplierQuotation, quotation_id)
    if quote and quote.company_id == principal.user.company_id and quote.valid_until and quote.valid_until < date.today():
        raise HTTPException(status_code=409, detail="Expired supplier quotation cannot be selected")
    return base_select_quotation(quotation_id=quotation_id, db=db, principal=principal)


@router.post("/purchase-orders", status_code=201)
def create_purchase_order_safe(payload: POInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    from app.models import ProcurementRequisition
    req = db.get(ProcurementRequisition, payload.requisition_id)
    quote = db.get(SupplierQuotation, payload.quotation_id)
    if payload.expected_delivery_date and payload.expected_delivery_date < payload.order_date:
        raise HTTPException(status_code=422, detail="Expected delivery date cannot precede the order date")
    if req and quote and req.company_id == principal.user.company_id and quote.requisition_id == req.id:
        cfg = policy(db, req.company_id)
        tolerance = Decimal(str(cfg.get("po_overrun_tolerance_pct", 0)))
        maximum = Decimal(req.estimated_total) * (Decimal("1") + tolerance / Decimal("100"))
        if Decimal(quote.total_amount) > maximum:
            raise HTTPException(status_code=409, detail=f"Selected quotation exceeds the approved requisition value plus {tolerance}% tolerance")
        if quote.valid_until and quote.valid_until < payload.order_date:
            raise HTTPException(status_code=409, detail="Selected supplier quotation expires before the purchase order date")
    return base_create_purchase_order(payload=payload, db=db, principal=principal)


@router.post("/purchase-orders/{purchase_order_id:int}/receipts", status_code=201)
def post_goods_receipt_safe(purchase_order_id: int, payload: ReceiptInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    po = db.get(PurchaseOrder, purchase_order_id)
    if not po or po.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    if not principal.can("procurement.view", branch_id=po.branch_id, site_id=po.site_id):
        raise HTTPException(status_code=403, detail="Purchase order is outside your procurement scope")
    if po.status not in {"approved", "part_received"}:
        raise HTTPException(status_code=409, detail="Only approved purchase orders may be received")
    location = location_or_404(db, principal, po.delivery_location_id, "stores.manage")
    if location.id != po.delivery_location_id:
        raise HTTPException(status_code=422, detail="Goods must be received into the purchase-order delivery store")
    ensure_document(db, po.company_id, payload.document_id)
    po_lines = {r.id: r for r in db.scalars(select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == po.id)).all()}
    seen: set[int] = set()
    for incoming in payload.lines:
        if incoming.purchase_order_line_id in seen:
            raise HTTPException(status_code=422, detail="A PO line can only appear once per goods receipt")
        seen.add(incoming.purchase_order_line_id)
        line = po_lines.get(incoming.purchase_order_line_id)
        if not line:
            raise HTTPException(status_code=422, detail="Goods receipt line does not belong to this purchase order")
        received = qty(incoming.quantity_received); accepted = qty(incoming.quantity_accepted); rejected = qty(incoming.quantity_rejected)
        if accepted + rejected != received:
            raise HTTPException(status_code=422, detail="Accepted plus rejected quantity must equal received quantity")
        outstanding = qty(Decimal(line.quantity_ordered) - Decimal(line.quantity_received))
        if received > outstanding:
            raise HTTPException(status_code=409, detail=f"Received quantity exceeds the outstanding PO quantity for line {line.id}")
    receipt = GoodsReceipt(
        company_id=po.company_id, purchase_order_id=po.id, location_id=location.id,
        goods_receipt_number=issue_reference(db, po.company_id, "GOODS_RECEIPT", "GRN"), receipt_date=payload.receipt_date,
        delivery_reference=payload.delivery_reference, document_id=payload.document_id, received_by=principal.user.full_name, notes=payload.notes,
    )
    db.add(receipt); db.flush()
    for incoming in payload.lines:
        line = po_lines[incoming.purchase_order_line_id]
        received = qty(incoming.quantity_received); accepted = qty(incoming.quantity_accepted); rejected = qty(incoming.quantity_rejected)
        db.add(GoodsReceiptLine(company_id=po.company_id, goods_receipt_id=receipt.id, purchase_order_line_id=line.id, stock_item_id=line.stock_item_id, quantity_received=received, quantity_accepted=accepted, quantity_rejected=rejected, unit_cost=line.unit_price, notes=incoming.notes))
        line.quantity_received = qty(Decimal(line.quantity_received) + accepted)
        if line.stock_item_id and accepted > 0:
            item = db.get(StockItem, line.stock_item_id)
            if item and item.stock_controlled:
                apply_stock(db, principal, location=location, item=item, delta=accepted, movement_type="receipt", cost=line.unit_price, project_id=po.project_id, site_id=po.site_id, cost_centre_id=po.cost_centre_id, reference_type="goods_receipt", reference_id=receipt.id, reason=f"Accepted against {po.purchase_order_number}")
    refreshed = db.scalars(select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == po.id)).all()
    po.status = "received" if all(Decimal(r.quantity_received) >= Decimal(r.quantity_ordered) for r in refreshed) else "part_received"
    audit(db, principal, "goods_receipt.posted", "goods_receipt", receipt.id, branch_id=po.branch_id, site_id=po.site_id, detail={"number": receipt.goods_receipt_number, "po_status": po.status})
    commit(db)
    return {**{column.name: str(getattr(receipt, column.name)) if isinstance(getattr(receipt, column.name), Decimal) else getattr(receipt, column.name) for column in receipt.__table__.columns}, "purchase_order_status": po.status}


@router.post("/stock/issues", status_code=201)
def issue_stock_safe(payload: StockIssueInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    location = location_or_404(db, principal, payload.location_id, "stores.issue")
    validate_operational_scope(db, principal, location, site_id=payload.site_id, project_id=payload.project_id, cost_centre_id=payload.cost_centre_id)
    if payload.site_material_entry_id:
        material = db.get(SiteMaterialEntry, payload.site_material_entry_id)
        if not material or material.company_id != principal.user.company_id or material.project_id != payload.project_id or material.site_id != payload.site_id:
            raise HTTPException(status_code=422, detail="Phase 7 material evidence does not match this stock issue")
    from app.api.v1.procurement import issue_stock as base_issue
    return base_issue(payload=payload, db=db, principal=principal)


@router.post("/stock/returns", status_code=201)
def return_stock_safe(payload: StockReturnInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    location = location_or_404(db, principal, payload.location_id, "stores.issue")
    validate_operational_scope(db, principal, location, site_id=payload.site_id, project_id=payload.project_id, cost_centre_id=payload.cost_centre_id)
    if payload.site_material_entry_id:
        material = db.get(SiteMaterialEntry, payload.site_material_entry_id)
        if not material or material.company_id != principal.user.company_id or material.project_id != payload.project_id or material.site_id != payload.site_id:
            raise HTTPException(status_code=422, detail="Phase 7 material evidence does not match this stock return")
    from app.api.v1.procurement import return_stock as base_return
    return base_return(payload=payload, db=db, principal=principal)
