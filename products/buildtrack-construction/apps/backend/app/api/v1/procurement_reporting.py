from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.procurement import location_or_404, po_or_404, require_anywhere, row_dict
from app.db.session import get_db
from app.models import GoodsReceipt, GoodsReceiptLine, PurchaseOrderLine, StockMovement, StockTransfer, StockTransferLine, StoreLocation
from app.security.access import Principal, current_principal

router = APIRouter(prefix="/procurement", tags=["Phase 8 - Procurement & Stores Reporting"])


@router.get("/purchase-orders/{purchase_order_id:int}")
def purchase_order_detail(purchase_order_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    po = po_or_404(db, principal, purchase_order_id)
    lines = db.scalars(select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == po.id).order_by(PurchaseOrderLine.id)).all()
    receipts = db.scalars(select(GoodsReceipt).where(GoodsReceipt.purchase_order_id == po.id).order_by(GoodsReceipt.receipt_date.desc(), GoodsReceipt.id.desc())).all()
    return {
        "purchase_order": row_dict(po),
        "lines": [row_dict(r) for r in lines],
        "receipts": [{**row_dict(r), "lines": [row_dict(x) for x in db.scalars(select(GoodsReceiptLine).where(GoodsReceiptLine.goods_receipt_id == r.id).order_by(GoodsReceiptLine.id)).all()]} for r in receipts],
    }


@router.get("/transfers/{transfer_id:int}")
def transfer_detail(transfer_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    transfer = db.get(StockTransfer, transfer_id)
    if not transfer or transfer.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Stock transfer not found")
    src = location_or_404(db, principal, transfer.from_location_id)
    dst = db.get(StoreLocation, transfer.to_location_id)
    if not dst or not (principal.can("stores.view", branch_id=src.branch_id, site_id=src.site_id) or principal.can("stores.view", branch_id=dst.branch_id, site_id=dst.site_id)):
        raise HTTPException(status_code=403, detail="Stock transfer is outside your stores scope")
    lines = db.scalars(select(StockTransferLine).where(StockTransferLine.transfer_id == transfer.id).order_by(StockTransferLine.id)).all()
    return {"transfer": row_dict(transfer), "lines": [row_dict(r) for r in lines]}


@router.get("/stock/movements")
def stock_movements(location_id: int | None = None, stock_item_id: int | None = None, limit: int = Query(default=250, ge=1, le=1000), db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    require_anywhere(principal, "stores.view")
    query = select(StockMovement).where(StockMovement.company_id == principal.user.company_id)
    if location_id is not None: query = query.where(StockMovement.location_id == location_id)
    if stock_item_id is not None: query = query.where(StockMovement.stock_item_id == stock_item_id)
    rows = db.scalars(query.order_by(StockMovement.recorded_at.desc(), StockMovement.id.desc()).limit(limit)).all()
    result = []
    for row in rows:
        location = db.get(StoreLocation, row.location_id)
        if location and principal.can("stores.view", branch_id=location.branch_id, site_id=location.site_id): result.append(row_dict(row))
    return result
