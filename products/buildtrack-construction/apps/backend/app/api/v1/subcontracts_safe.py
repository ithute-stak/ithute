from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.subcontracts import (
    AwardInput, CertificateInput, ContractInput, PaymentInput, VariationInput,
    create_certificate as base_create_certificate,
    create_contract as base_create_contract,
    create_variation as base_create_variation,
    policy, record_payment as base_record_payment,
    submit_award as base_submit_award,
)
from app.db.session import get_db
from app.models import (
    SubcontractBid, SubcontractCertificate, SubcontractContract,
    SubcontractInvitation, SubcontractPackage, SubcontractVariation,
    Subcontractor,
)
from app.security.access import Principal, current_principal

router = APIRouter(prefix="/subcontracts", tags=["Phase 9 - Subcontract Control"])


@router.post("/packages/{package_id:int}/award")
def submit_award_safe(package_id: int, payload: AwardInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)):
    package = db.get(SubcontractPackage, package_id)
    bid = db.get(SubcontractBid, payload.bid_id)
    if not package or package.company_id != principal.user.company_id or not bid or bid.package_id != package.id:
        return base_submit_award(package_id=package_id, payload=payload, db=db, principal=principal)
    vendor = db.get(Subcontractor, bid.subcontractor_id)
    if not vendor or vendor.status != "active":
        raise HTTPException(status_code=409, detail="The selected subcontractor must remain active at award")
    invitation = db.scalar(select(SubcontractInvitation.id).where(
        SubcontractInvitation.package_id == package.id,
        SubcontractInvitation.subcontractor_id == vendor.id,
    ))
    if not invitation:
        raise HTTPException(status_code=409, detail="An award requires a controlled invitation to the selected subcontractor")
    received = db.scalar(select(func.count()).select_from(SubcontractBid).where(
        SubcontractBid.package_id == package.id, SubcontractBid.status == "received",
    )) or 0
    cfg = policy(db, package.company_id)
    if received < int(cfg["minimum_bids"]) and Decimal(package.budget_amount) > Decimal(str(cfg["low_value_bid_waiver"])):
        raise HTTPException(status_code=409, detail="Minimum subcontract bid count has not been met; use a documented low-value exception only where policy permits")
    return base_submit_award(package_id=package_id, payload=payload, db=db, principal=principal)


@router.post("/contracts", status_code=201)
def create_contract_safe(payload: ContractInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)):
    package = db.get(SubcontractPackage, payload.package_id)
    if package and package.company_id == principal.user.company_id:
        if not package.award_document_id:
            raise HTTPException(status_code=409, detail="An approved award evidence document is required before contract drafting")
        if payload.advance_amount > 0 and not payload.contract_document_id:
            raise HTTPException(status_code=409, detail="An advance amount requires a controlled contract document")
    return base_create_contract(payload=payload, db=db, principal=principal)


@router.post("/contracts/{contract_id:int}/variations", status_code=201)
def create_variation_safe(contract_id: int, payload: VariationInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)):
    if payload.value != 0 and not payload.document_id:
        raise HTTPException(status_code=409, detail="A priced subcontract variation requires controlled supporting evidence")
    return base_create_variation(contract_id=contract_id, payload=payload, db=db, principal=principal)


@router.post("/contracts/{contract_id:int}/certificates", status_code=201)
def create_certificate_safe(contract_id: int, payload: CertificateInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)):
    contract = db.get(SubcontractContract, contract_id)
    if contract and contract.company_id == principal.user.company_id:
        pending = db.scalar(select(SubcontractCertificate.id).where(
            SubcontractCertificate.contract_id == contract.id,
            SubcontractCertificate.status.in_(["draft", "submitted"]),
        ))
        if pending:
            raise HTTPException(status_code=409, detail="Resolve the existing draft/submitted certificate before preparing another")
        if payload.certificate_type == "retention_release" and payload.gross_value > Decimal(contract.retention_held):
            raise HTTPException(status_code=409, detail="Retention release cannot exceed retention held on the contract")
    return base_create_certificate(contract_id=contract_id, payload=payload, db=db, principal=principal)


@router.post("/certificates/{certificate_id:int}/payments", status_code=201)
def record_payment_safe(certificate_id: int, payload: PaymentInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)):
    if not payload.payment_document_id:
        raise HTTPException(status_code=409, detail="A controlled payment proof document is required to record a subcontract payment")
    return base_record_payment(certificate_id=certificate_id, payload=payload, db=db, principal=principal)
