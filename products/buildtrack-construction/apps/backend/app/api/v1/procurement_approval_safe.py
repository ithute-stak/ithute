from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.procurement import ApprovalDecisionInput, allow_self_approval, assignment_authorised, audit, commit, require_scope, utcnow
from app.db.session import get_db
from app.models import ApprovalAction, ApprovalRequest, ApprovalStep, ProcurementRequisition, PurchaseOrder, Supplier, SupplierQuotation
from app.security.access import Principal, current_principal

router = APIRouter(prefix="/procurement", tags=["Phase 8 - Procurement Approval Control"])


@router.post("/approvals/{request_id:int}/decision")
def decide_procurement_approval_safe(request_id: int, payload: ApprovalDecisionInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, object]:
    request = db.get(ApprovalRequest, request_id)
    if not request or request.company_id != principal.user.company_id or request.entity_type not in {"procurement_requisition", "purchase_order"}:
        raise HTTPException(status_code=404, detail="Procurement approval request not found")
    if request.entity_type == "procurement_requisition":
        entity = db.get(ProcurementRequisition, int(request.entity_id))
    else:
        entity = db.get(PurchaseOrder, int(request.entity_id))
    if not entity:
        raise HTTPException(status_code=404, detail="Procurement approval entity not found")
    require_scope(principal, "procurement.approve", entity.branch_id, entity.site_id)
    if request.status != "pending":
        raise HTTPException(status_code=409, detail=f"Approval request is already {request.status}")
    step = db.scalar(select(ApprovalStep).where(ApprovalStep.workflow_id == request.workflow_id, ApprovalStep.step_order == request.current_step_order))
    if not step or not assignment_authorised(db, principal, step.role_id, entity.branch_id, entity.site_id):
        raise HTTPException(status_code=403, detail="Your active role assignment is not authorised for this approval step")
    if request.requested_by == principal.user.full_name and not allow_self_approval(db, principal.user.company_id):
        raise HTTPException(status_code=422, detail="Self-approval is disabled by company approval policy")
    if payload.decision == "approve" and isinstance(entity, PurchaseOrder):
        supplier = db.get(Supplier, entity.supplier_id)
        quote = db.get(SupplierQuotation, entity.quotation_id)
        if not supplier or supplier.status != "active":
            raise HTTPException(status_code=409, detail="Purchase order supplier is no longer active")
        if not quote or quote.requisition_id != entity.requisition_id or quote.status != "selected":
            raise HTTPException(status_code=409, detail="Purchase order no longer references the selected requisition quotation")

    db.add(ApprovalAction(request_id=request.id, step_order=step.step_order, role_id=step.role_id, actor_name=principal.user.full_name, action=payload.decision, comment=payload.comment))
    if payload.decision == "reject":
        request.status = "rejected"; request.completed_at = utcnow()
    else:
        approved_count = (db.scalar(select(func.count()).select_from(ApprovalAction).where(ApprovalAction.request_id == request.id, ApprovalAction.step_order == step.step_order, ApprovalAction.action == "approve")) or 0) + 1
        if approved_count >= step.required_approvals:
            next_step = db.scalar(select(ApprovalStep).where(ApprovalStep.workflow_id == request.workflow_id, ApprovalStep.step_order > step.step_order).order_by(ApprovalStep.step_order).limit(1))
            if next_step:
                request.current_step_order = next_step.step_order
            else:
                request.status = "approved"; request.completed_at = utcnow()

    if isinstance(entity, ProcurementRequisition):
        if request.status == "approved": entity.status = "approved"
        elif request.status == "rejected": entity.status = "rejected"
    else:
        if request.status == "approved":
            entity.status = "approved"; entity.approved_at = utcnow()
            req = db.get(ProcurementRequisition, entity.requisition_id)
            if req: req.status = "ordered"
        elif request.status == "rejected":
            entity.status = "rejected"

    audit(db, principal, f"procurement.approval.{payload.decision}", "approval_request", request.id, branch_id=entity.branch_id, site_id=entity.site_id, detail={"entity_type": request.entity_type, "status": request.status, "step": step.step_order})
    commit(db)
    return {column.name: getattr(request, column.name) for column in request.__table__.columns}
