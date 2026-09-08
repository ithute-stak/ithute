from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.tenders import (
    BidDecisionInput,
    ChecklistInput,
    EstimateInput,
    SecurityInput,
    SubmissionInput,
    TenderInput,
    audit,
    calculate_item,
    commit,
    create_approval,
    employee_in_scope,
    ensure_document,
    ensure_scope,
    issue_reference,
    recalculate_tender,
    reconcile_phase5,
    require_anywhere,
    require_scope,
    row_dict,
    tender_or_404,
    utcnow,
)
from app.db.session import get_db
from app.models import ApprovalRequest, CompanySetting, Tender, TenderChecklistItem, TenderEstimateItem, TenderSecurity, TenderSubmission, TenderTeamMember
from app.security.access import Principal, current_principal

router = APIRouter(prefix="/tenders", tags=["Phase 5 - Tender Control"])
DEFAULT_CHECKLIST = (
    ("administrative", "Tender invitation / instructions", True),
    ("administrative", "Signed form of tender", True),
    ("company", "Company registration documents", True),
    ("company", "Tax compliance / clearance evidence", True),
    ("company", "Relevant licences / certificates", True),
    ("technical", "Method statement / technical proposal", True),
    ("technical", "Programme / construction schedule", True),
    ("technical", "Key personnel and experience evidence", True),
    ("commercial", "Completed BOQ / pricing schedule", True),
    ("commercial", "Tender security / bid bond where required", False),
)


def aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def pricing_locked(db: Session, tender: Tender) -> bool:
    if not tender.commercial_approval_request_id:
        return False
    request = db.get(ApprovalRequest, tender.commercial_approval_request_id)
    return bool(request and request.status in {"pending", "approved"})


def submission_evidence_locked(db: Session, tender: Tender) -> bool:
    if tender.status in {"submitted", "awarded", "lost", "cancelled", "withdrawn"}:
        return True
    if not tender.submission_approval_request_id:
        return False
    request = db.get(ApprovalRequest, tender.submission_approval_request_id)
    return bool(request and request.status in {"pending", "approved"})


class TenderPolicyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    deadline_warning_days: int = Field(default=7, ge=1, le=90)
    minimum_margin_pct: Decimal = Field(default=0, ge=-100, le=100)
    require_commercial_approval: bool = True
    require_submission_approval: bool = True


@router.post("/bootstrap")
def bootstrap_safe(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if not principal.has_company_permission("company.manage") and not principal.has_company_permission("tenders.manage"):
        raise HTTPException(status_code=403, detail="Company-level administration is required to initialise Phase 5")
    reconcile_phase5(db, principal.user.company_id)
    audit(db, principal, "tender.bootstrap", "phase", "5", detail={"status": "operational"})
    commit(db)
    return {"phase": 5, "status": "operational", "permissions": ["tenders.view", "tenders.manage", "tenders.approve", "tenders.estimate", "tenders.submit", "tenders.export"]}


@router.get("/status")
def status_safe(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    from app.models import Permission
    initialized = bool(db.scalar(select(Permission.id).where(Permission.code == "tenders.estimate")))
    can_initialize = principal.has_company_permission("company.manage") or principal.has_company_permission("tenders.manage")
    return {"phase": 5, "initialized": initialized, "status": "operational" if initialized else "not_initialized", "can_initialize": can_initialize}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_tender_safe(payload: TenderInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_scope(principal, "tenders.manage", payload.branch_id, payload.site_id)
    ensure_scope(db, principal, payload.branch_id, payload.site_id, payload.cost_centre_id)
    employee_in_scope(db, principal, payload.lead_employee_id, payload.branch_id)
    deadline = aware(payload.submission_deadline)
    if deadline is None or deadline <= utcnow():
        raise HTTPException(status_code=422, detail="Submission deadline must be in the future when registering a tender")
    if payload.site_visit_required and payload.site_visit_date is None:
        raise HTTPException(status_code=422, detail="A required site visit must have a date/time")
    values = payload.model_dump()
    for key in ("briefing_date", "site_visit_date", "clarification_deadline", "submission_deadline", "opening_date"):
        values[key] = aware(values.get(key))
    tender = Tender(company_id=principal.user.company_id, tender_number=issue_reference(db, principal.user.company_id, "TENDER", "TND"), created_by=principal.user.full_name, **values)
    db.add(tender); db.flush()
    for category, name, required in DEFAULT_CHECKLIST:
        db.add(TenderChecklistItem(company_id=tender.company_id, tender_id=tender.id, category=category, name=name, required=required, status="missing", due_date=tender.submission_deadline, updated_by=principal.user.full_name))
    if payload.lead_employee_id:
        db.add(TenderTeamMember(company_id=tender.company_id, tender_id=tender.id, employee_id=payload.lead_employee_id, role="lead", added_by=principal.user.full_name))
    audit(db, principal, "tender.created", "tender", tender.id, tender=tender, detail={"tender_number": tender.tender_number, "client": tender.client_name, "deadline": tender.submission_deadline.isoformat()})
    commit(db, "Tender reference already exists")
    return row_dict(tender)


@router.put("/{tender_id}")
def update_tender(tender_id: int, payload: TenderInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    tender = tender_or_404(db, principal, tender_id, "tenders.manage")
    if tender.status in {"submitted", "awarded", "lost", "cancelled", "withdrawn"} or pricing_locked(db, tender):
        raise HTTPException(status_code=409, detail="Tender master data is locked after commercial approval begins")
    ensure_scope(db, principal, payload.branch_id, payload.site_id, payload.cost_centre_id)
    employee_in_scope(db, principal, payload.lead_employee_id, payload.branch_id)
    if payload.site_visit_required and payload.site_visit_date is None:
        raise HTTPException(status_code=422, detail="A required site visit must have a date/time")
    old_scope = {"branch_id": tender.branch_id, "site_id": tender.site_id}
    values = payload.model_dump()
    for key in ("briefing_date", "site_visit_date", "clarification_deadline", "submission_deadline", "opening_date"):
        values[key] = aware(values.get(key))
    for key, value in values.items(): setattr(tender, key, value)
    audit(db, principal, "tender.updated", "tender", tender.id, tender=tender, detail={"old_scope": old_scope, "deadline": tender.submission_deadline.isoformat()})
    commit(db, "Tender reference already exists")
    return row_dict(tender)


@router.post("/{tender_id}/bid-decision")
def bid_decision_safe(tender_id: int, payload: BidDecisionInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    tender = tender_or_404(db, principal, tender_id, "tenders.approve")
    if pricing_locked(db, tender) or tender.submission_approval_request_id or tender.status in {"submitted", "awarded", "lost", "cancelled", "withdrawn"}:
        raise HTTPException(status_code=409, detail="Bid decision is locked after commercial approval begins")
    tender.bid_decision = payload.decision
    tender.bid_decision_reason = payload.reason
    tender.bid_decided_by = principal.user.full_name
    tender.bid_decided_at = utcnow()
    tender.status = "preparing" if payload.decision == "bid" else "no_bid"
    audit(db, principal, f"tender.bid_decision.{payload.decision}", "tender", tender.id, tender=tender, detail={"reason": payload.reason})
    commit(db)
    return row_dict(tender)


@router.put("/checklist/{item_id}")
def update_checklist_safe(item_id: int, payload: ChecklistInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = db.get(TenderChecklistItem, item_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Checklist item not found")
    tender = tender_or_404(db, principal, row.tender_id, "tenders.manage")
    if submission_evidence_locked(db, tender):
        raise HTTPException(status_code=409, detail="Checklist evidence is frozen while submission approval is active or after submission")
    employee_in_scope(db, principal, payload.owner_employee_id, tender.branch_id)
    ensure_document(db, tender.company_id, payload.document_id)
    for key, value in payload.model_dump().items(): setattr(row, key, value)
    row.updated_by = principal.user.full_name
    audit(db, principal, "tender.checklist.updated", "tender_checklist_item", row.id, tender=tender, detail={"status": row.status, "document_id": row.document_id})
    commit(db)
    return row_dict(row)


@router.post("/{tender_id}/estimate-items", status_code=status.HTTP_201_CREATED)
def add_estimate_item_safe(tender_id: int, payload: EstimateInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    tender = tender_or_404(db, principal, tender_id, "tenders.estimate")
    if tender.bid_decision != "bid": raise HTTPException(status_code=409, detail="Tender must have an approved Bid decision before estimating")
    if pricing_locked(db, tender): raise HTTPException(status_code=409, detail="Pricing is frozen while commercial approval is pending or approved")
    values = payload.model_dump(); values.update(calculate_item(payload))
    row = TenderEstimateItem(company_id=tender.company_id, tender_id=tender.id, created_by=principal.user.full_name, **values)
    db.add(row); db.flush(); recalculate_tender(db, tender)
    audit(db, principal, "tender.estimate_item.created", "tender_estimate_item", row.id, tender=tender, detail={"selling_total": str(row.selling_total)})
    commit(db); return row_dict(row)


@router.put("/estimate-items/{item_id}")
def update_estimate_item_safe(item_id: int, payload: EstimateInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = db.get(TenderEstimateItem, item_id)
    if not row or row.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Estimate item not found")
    tender = tender_or_404(db, principal, row.tender_id, "tenders.estimate")
    if pricing_locked(db, tender): raise HTTPException(status_code=409, detail="Pricing is frozen while commercial approval is pending or approved")
    values = payload.model_dump(); values.update(calculate_item(payload))
    for key, value in values.items(): setattr(row, key, value)
    recalculate_tender(db, tender)
    audit(db, principal, "tender.estimate_item.updated", "tender_estimate_item", row.id, tender=tender, detail={"selling_total": str(row.selling_total)})
    commit(db); return row_dict(row)


@router.delete("/estimate-items/{item_id}", status_code=204)
def delete_estimate_item_safe(item_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> None:
    row = db.get(TenderEstimateItem, item_id)
    if not row or row.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Estimate item not found")
    tender = tender_or_404(db, principal, row.tender_id, "tenders.estimate")
    if pricing_locked(db, tender): raise HTTPException(status_code=409, detail="Pricing is frozen while commercial approval is pending or approved")
    db.delete(row); db.flush(); recalculate_tender(db, tender)
    audit(db, principal, "tender.estimate_item.deleted", "tender_estimate_item", item_id, tender=tender)
    commit(db)


@router.post("/{tender_id}/securities", status_code=status.HTTP_201_CREATED)
def add_security_safe(tender_id: int, payload: SecurityInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    tender = tender_or_404(db, principal, tender_id, "tenders.manage")
    if submission_evidence_locked(db, tender):
        raise HTTPException(status_code=409, detail="Security evidence is frozen while submission approval is active or after submission")
    if payload.expiry_date and payload.issue_date and payload.expiry_date < payload.issue_date:
        raise HTTPException(status_code=422, detail="Security expiry cannot precede issue date")
    ensure_document(db, tender.company_id, payload.document_id)
    row = TenderSecurity(company_id=tender.company_id, tender_id=tender.id, created_by=principal.user.full_name, **payload.model_dump())
    db.add(row); db.flush()
    audit(db, principal, "tender.security.created", "tender_security", row.id, tender=tender, detail={"type": row.security_type, "amount": str(row.amount), "status": row.status})
    commit(db); return row_dict(row)


@router.post("/{tender_id}/commercial-approval")
def request_commercial_approval_safe(tender_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    tender = tender_or_404(db, principal, tender_id, "tenders.manage")
    if tender.bid_decision != "bid" or tender.tender_price <= 0: raise HTTPException(status_code=409, detail="Approved Bid decision and priced estimate are required")
    policy_row = db.scalar(select(CompanySetting).where(CompanySetting.company_id == tender.company_id, CompanySetting.key == "tender_policy"))
    policy = policy_row.value if policy_row and isinstance(policy_row.value, dict) else {}
    minimum_margin = Decimal(str(policy.get("minimum_margin_pct", 0)))
    if Decimal(tender.gross_margin_pct or 0) < minimum_margin:
        raise HTTPException(status_code=409, detail=f"Tender margin {tender.gross_margin_pct}% is below the configured minimum {minimum_margin}%")
    if tender.commercial_approval_request_id:
        existing = db.get(ApprovalRequest, tender.commercial_approval_request_id)
        if existing and existing.status in {"pending", "approved"}: return row_dict(existing)
    request = create_approval(db, principal, tender, "TENDER_COMMERCIAL", f"Commercial approval: {tender.tender_number} - {tender.title}")
    tender.commercial_approval_request_id = request.id; tender.status = "review"
    audit(db, principal, "tender.commercial_approval.requested", "approval_request", request.id, tender=tender, detail={"reference": request.reference, "amount": str(request.amount), "margin_pct": str(tender.gross_margin_pct)})
    commit(db); return row_dict(request)


@router.post("/{tender_id}/submission-approval")
def request_submission_approval_safe(tender_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    tender = tender_or_404(db, principal, tender_id, "tenders.manage")
    commercial = db.get(ApprovalRequest, tender.commercial_approval_request_id) if tender.commercial_approval_request_id else None
    if not commercial or commercial.status != "approved": raise HTTPException(status_code=409, detail="Commercial approval must be complete before submission approval")
    missing = db.scalar(select(func.count()).select_from(TenderChecklistItem).where(TenderChecklistItem.tender_id == tender.id, TenderChecklistItem.required.is_(True), TenderChecklistItem.status != "ready")) or 0
    if missing: raise HTTPException(status_code=409, detail=f"{missing} required checklist item(s) are not ready")
    if tender.submission_approval_request_id:
        existing = db.get(ApprovalRequest, tender.submission_approval_request_id)
        if existing and existing.status in {"pending", "approved"}: return row_dict(existing)
    request = create_approval(db, principal, tender, "TENDER_SUBMISSION", f"Submission approval: {tender.tender_number} - {tender.title}")
    tender.submission_approval_request_id = request.id
    audit(db, principal, "tender.submission_approval.requested", "approval_request", request.id, tender=tender, detail={"reference": request.reference})
    commit(db); return row_dict(request)


@router.post("/{tender_id}/submit", status_code=status.HTTP_201_CREATED)
def record_submission_safe(tender_id: int, payload: SubmissionInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    tender = tender_or_404(db, principal, tender_id, "tenders.submit")
    approval = db.get(ApprovalRequest, tender.submission_approval_request_id) if tender.submission_approval_request_id else None
    if not approval or approval.status != "approved": raise HTTPException(status_code=409, detail="A fresh approved submission request is required for each submission version")
    missing = db.scalar(select(func.count()).select_from(TenderChecklistItem).where(TenderChecklistItem.tender_id == tender.id, TenderChecklistItem.required.is_(True), TenderChecklistItem.status != "ready")) or 0
    if missing: raise HTTPException(status_code=409, detail="Required tender checklist is incomplete")
    unresolved_security = db.scalars(select(TenderSecurity).where(TenderSecurity.tender_id == tender.id, TenderSecurity.status.not_in(["issued", "not_required", "released"]))).all()
    if unresolved_security: raise HTTPException(status_code=409, detail="Tender security requirements are not complete")
    ensure_document(db, tender.company_id, payload.acknowledgement_document_id)
    version = (db.scalar(select(func.max(TenderSubmission.version)).where(TenderSubmission.tender_id == tender.id)) or 0) + 1
    row = TenderSubmission(company_id=tender.company_id, tender_id=tender.id, approval_request_id=approval.id, version=version, submission_method=payload.submission_method, submission_location=payload.submission_location, submitted_at=aware(payload.submitted_at) or utcnow(), submitted_by=principal.user.full_name, acknowledgement_reference=payload.acknowledgement_reference, acknowledgement_document_id=payload.acknowledgement_document_id, tender_price=tender.tender_price, notes=payload.notes)
    db.add(row); db.flush()
    tender.status = "submitted"
    tender.submission_approval_request_id = None
    audit(db, principal, "tender.submitted", "tender_submission", row.id, tender=tender, detail={"version": version, "approval_request_id": approval.id, "method": row.submission_method, "price": str(row.tender_price)})
    commit(db); return row_dict(row)


@router.get("/policy/current")
def get_policy(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_anywhere(principal, "tenders.view")
    row = db.scalar(select(CompanySetting).where(CompanySetting.company_id == principal.user.company_id, CompanySetting.key == "tender_policy"))
    value = row.value if row and isinstance(row.value, dict) else {}
    return {"deadline_warning_days": int(value.get("deadline_warning_days", 7)), "minimum_margin_pct": str(value.get("minimum_margin_pct", 0)), "require_commercial_approval": True, "require_submission_approval": True, "can_edit": principal.has_company_permission("tenders.manage") or principal.has_company_permission("company.manage")}


@router.put("/policy/current")
def set_policy(payload: TenderPolicyInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if not principal.has_company_permission("tenders.manage") and not principal.has_company_permission("company.manage"):
        raise HTTPException(status_code=403, detail="Company-level tender administration is required")
    row = db.scalar(select(CompanySetting).where(CompanySetting.company_id == principal.user.company_id, CompanySetting.key == "tender_policy"))
    value = {**payload.model_dump(mode="json"), "require_commercial_approval": True, "require_submission_approval": True}
    if row: row.value = value
    else: row = CompanySetting(company_id=principal.user.company_id, key="tender_policy", value=value, description="Phase 5 tender governance policy"); db.add(row)
    commit(db); return {**value, "can_edit": True}


@router.get("/exports/pipeline.csv")
def export_pipeline(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> StreamingResponse:
    require_anywhere(principal, "tenders.export")
    output = io.StringIO(); writer = csv.writer(output)
    writer.writerow(["Tender Number", "Reference", "Title", "Client", "Branch ID", "Deadline", "Status", "Bid Decision", "Probability %", "Direct Cost", "Tender Price", "Gross Margin", "Margin %"])
    rows = db.scalars(select(Tender).where(Tender.company_id == principal.user.company_id).order_by(Tender.submission_deadline)).all()
    for tender in rows:
        if principal.can("tenders.export", branch_id=tender.branch_id, site_id=tender.site_id):
            writer.writerow([tender.tender_number, tender.external_reference or "", tender.title, tender.client_name, tender.branch_id, tender.submission_deadline.isoformat(), tender.status, tender.bid_decision, tender.win_probability, tender.direct_cost_total, tender.tender_price, tender.gross_margin, tender.gross_margin_pct])
    return StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=buildtrack-tender-pipeline.csv"})
