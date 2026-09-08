from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.subcontracts import (
    ApprovalDecisionInput, decide_approval as base_decide_approval,
)
from app.db.session import get_db
from app.models import (
    ApprovalRequest, SubcontractBid, SubcontractCertificate,
    SubcontractContract, SubcontractPackage, SubcontractVariation,
    Subcontractor,
)
from app.security.access import Principal, current_principal

router = APIRouter(prefix="/subcontracts", tags=["Phase 9 - Subcontract Approval Hardening"])


@router.post("/approvals/{request_id:int}/decision")
def decide_subcontract_approval_safe(request_id: int, payload: ApprovalDecisionInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)):
    request = db.get(ApprovalRequest, request_id)
    if request and request.company_id == principal.user.company_id and payload.decision == "approve":
        if request.entity_type == "subcontract_award":
            package = db.get(SubcontractPackage, int(request.entity_id))
            bid = db.get(SubcontractBid, package.selected_bid_id) if package and package.selected_bid_id else None
            vendor = db.get(Subcontractor, bid.subcontractor_id) if bid else None
            if not package or package.status != "award_submitted" or not bid or not vendor or vendor.status != "active":
                raise HTTPException(status_code=409, detail="The award package, selected bid and subcontractor must remain valid until final approval")
        elif request.entity_type == "subcontract_contract":
            contract = db.get(SubcontractContract, int(request.entity_id))
            if not contract or contract.status != "submitted" or not contract.contract_document_id:
                raise HTTPException(status_code=409, detail="A submitted subcontract contract needs controlled contract evidence before approval")
        elif request.entity_type == "subcontract_variation":
            variation = db.get(SubcontractVariation, int(request.entity_id))
            if not variation or variation.status != "submitted" or not variation.document_id:
                raise HTTPException(status_code=409, detail="A submitted subcontract variation needs controlled supporting evidence before approval")
        elif request.entity_type == "subcontract_certificate":
            certificate = db.get(SubcontractCertificate, int(request.entity_id))
            if not certificate or certificate.status != "submitted" or not certificate.evidence_document_id:
                raise HTTPException(status_code=409, detail="A submitted subcontract certificate needs controlled measurement evidence before approval")
    return base_decide_approval(request_id=request_id, payload=payload, db=db, principal=principal)
