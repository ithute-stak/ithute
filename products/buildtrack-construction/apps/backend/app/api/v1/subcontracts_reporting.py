from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.procurement import row_dict
from app.api.v1.subcontracts import contract_or_404, require_anywhere
from app.db.session import get_db
from app.models import (
    SubcontractCertificate, SubcontractContract, SubcontractPackage,
    SubcontractPayment, SubcontractPerformanceReview, SubcontractVariation,
    Subcontractor,
)
from app.security.access import Principal, current_principal

router = APIRouter(prefix="/subcontracts", tags=["Phase 9 - Subcontract Reporting"])


@router.get("/contracts/{contract_id:int}/commercial-position")
def commercial_position(contract_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    contract = contract_or_404(db, principal, contract_id)
    from app.api.v1.subcontracts import contract_ceiling, payment_total
    certificates = db.scalars(select(SubcontractCertificate).where(SubcontractCertificate.contract_id == contract.id).order_by(SubcontractCertificate.id)).all()
    paid = sum((payment_total(db, certificate.id) for certificate in certificates), 0)
    return {
        "contract": row_dict(contract),
        "current_contract_sum": str(contract_ceiling(db, contract)),
        "certificate_gross": str(sum((certificate.gross_value for certificate in certificates if certificate.status in {"approved", "part_paid", "paid"}), 0)),
        "certificate_net_payable": str(sum((certificate.net_payable for certificate in certificates if certificate.status in {"approved", "part_paid", "paid"}), 0)),
        "paid": str(paid),
        "retention_held": str(contract.retention_held),
        "unpaid_approved": str(sum((certificate.net_payable - payment_total(db, certificate.id) for certificate in certificates if certificate.status in {"approved", "part_paid"}), 0)),
    }


@router.get("/certificates")
def list_certificates(status: str | None = None, limit: int = Query(default=250, ge=1, le=1000), db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    require_anywhere(principal, "subcontracts.view")
    query = select(SubcontractCertificate).where(SubcontractCertificate.company_id == principal.user.company_id).order_by(SubcontractCertificate.period_end.desc(), SubcontractCertificate.id.desc()).limit(limit)
    if status:
        query = query.where(SubcontractCertificate.status == status)
    result = []
    for certificate in db.scalars(query).all():
        contract = db.get(SubcontractContract, certificate.contract_id)
        if contract and principal.can("subcontracts.view", branch_id=contract.branch_id, site_id=contract.site_id):
            vendor = db.get(Subcontractor, contract.subcontractor_id)
            package = db.get(SubcontractPackage, contract.package_id)
            result.append({**row_dict(certificate), "contract_number": contract.contract_number, "subcontractor": vendor.legal_name if vendor else "", "package_number": package.package_number if package else ""})
    return result


@router.get("/contracts/{contract_id:int}/history")
def contract_history(contract_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    contract = contract_or_404(db, principal, contract_id)
    return {
        "variations": [row_dict(row) for row in db.scalars(select(SubcontractVariation).where(SubcontractVariation.contract_id == contract.id).order_by(SubcontractVariation.id)).all()],
        "certificates": [row_dict(row) for row in db.scalars(select(SubcontractCertificate).where(SubcontractCertificate.contract_id == contract.id).order_by(SubcontractCertificate.id)).all()],
        "payments": [row_dict(row) for row in db.scalars(select(SubcontractPayment).join(SubcontractCertificate).where(SubcontractCertificate.contract_id == contract.id).order_by(SubcontractPayment.id)).all()],
        "performance_reviews": [row_dict(row) for row in db.scalars(select(SubcontractPerformanceReview).where(SubcontractPerformanceReview.contract_id == contract.id).order_by(SubcontractPerformanceReview.review_date)).all()],
    }
