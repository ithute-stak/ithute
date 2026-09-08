from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import (
    ApprovalAction,
    ApprovalRequest,
    ApprovalStep,
    ApprovalWorkflow,
    Branch,
    CompanySetting,
    CostCentre,
    Document,
    Employee,
    NumberSequence,
    Permission,
    Role,
    RolePermission,
    Site,
    Tender,
    TenderAuditEvent,
    TenderChecklistItem,
    TenderClarification,
    TenderEstimateItem,
    TenderOutcome,
    TenderSecurity,
    TenderSubmission,
    TenderTeamMember,
    UserRoleAssignment,
)
from app.security.access import Principal, current_principal

router = APIRouter(prefix="/tenders", tags=["Phase 5 - Tender Management"])
MONEY = Decimal("0.01")
RATE = Decimal("0.0001")

EXTRA_PERMISSIONS: dict[str, tuple[str, str, str]] = {
    "tenders.estimate": ("tenders", "estimate", "Build and maintain tender estimates and pricing"),
    "tenders.submit": ("tenders", "submit", "Record controlled tender submissions"),
    "tenders.export": ("tenders", "export", "Export tender pipeline and commercial evidence"),
}
ROLE_REQUIREMENTS: dict[str, set[str]] = {
    "SYSTEM_ADMIN": {"tenders.view", "tenders.manage", "tenders.approve", *EXTRA_PERMISSIONS},
    "HQ_EXECUTIVE": {"tenders.view", "tenders.approve", "tenders.export"},
    "BRANCH_MANAGER": {"tenders.view", "tenders.manage", "tenders.estimate", "tenders.submit", "tenders.export"},
    "SITE_MANAGER": {"tenders.view"},
    "APPROVER": {"tenders.view", "tenders.approve"},
    "AUDITOR": {"tenders.view", "tenders.export"},
    "TENDER_MANAGER": {"tenders.view", "tenders.manage", "tenders.estimate", "tenders.submit", "tenders.export"},
    "ESTIMATOR": {"tenders.view", "tenders.estimate"},
    "TENDER_COORDINATOR": {"tenders.view", "tenders.manage", "tenders.submit", "tenders.export"},
}
STANDARD_CHECKLIST = (
    ("administrative", "Tender invitation / instructions"),
    ("administrative", "Signed form of tender"),
    ("company", "Company registration documents"),
    ("company", "Tax compliance / clearance evidence"),
    ("company", "Relevant licences / certificates"),
    ("technical", "Method statement / technical proposal"),
    ("technical", "Programme / construction schedule"),
    ("technical", "Key personnel and experience evidence"),
    ("commercial", "Completed BOQ / pricing schedule"),
    ("commercial", "Tender security / bid bond where required"),
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def rate(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(RATE, rounding=ROUND_HALF_UP)


def json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def row_dict(row: Any) -> dict[str, Any]:
    return {column.name: json_value(getattr(row, column.name)) for column in row.__table__.columns}


def commit(db: Session, detail: str = "Tender record conflicts with existing data") -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=detail) from error


def require_anywhere(principal: Principal, permission: str) -> None:
    if not principal.has_permission_anywhere(permission):
        raise HTTPException(status_code=403, detail=f"Permission required: {permission}")


def require_scope(principal: Principal, permission: str, branch_id: int, site_id: int | None = None) -> None:
    if not principal.can(permission, branch_id=branch_id, site_id=site_id):
        raise HTTPException(status_code=403, detail=f"Permission required in this branch/site: {permission}")


def ensure_scope(db: Session, principal: Principal, branch_id: int, site_id: int | None = None, cost_centre_id: int | None = None) -> None:
    branch = db.get(Branch, branch_id)
    if not branch or branch.company_id != principal.user.company_id:
        raise HTTPException(status_code=422, detail="Branch does not belong to the active company")
    if site_id is not None:
        site = db.get(Site, site_id)
        if not site or site.company_id != principal.user.company_id or site.branch_id != branch_id:
            raise HTTPException(status_code=422, detail="Site does not belong to the selected branch")
    if cost_centre_id is not None:
        centre = db.get(CostCentre, cost_centre_id)
        if not centre or centre.company_id != principal.user.company_id:
            raise HTTPException(status_code=422, detail="Cost centre does not belong to the active company")
        if centre.branch_id is not None and centre.branch_id != branch_id:
            raise HTTPException(status_code=422, detail="Cost centre is outside the selected branch")
        if site_id is not None and centre.site_id is not None and centre.site_id != site_id:
            raise HTTPException(status_code=422, detail="Cost centre is outside the selected site")


def employee_in_scope(db: Session, principal: Principal, employee_id: int | None, branch_id: int) -> Employee | None:
    if employee_id is None:
        return None
    employee = db.get(Employee, employee_id)
    if not employee or employee.company_id != principal.user.company_id or employee.employment_status not in {"active", "on_leave"}:
        raise HTTPException(status_code=422, detail="Tender team member is not an active employee")
    if employee.branch_id != branch_id:
        raise HTTPException(status_code=422, detail="Tender team member must belong to the tender branch")
    return employee


def tender_or_404(db: Session, principal: Principal, tender_id: int, permission: str = "tenders.view") -> Tender:
    tender = db.get(Tender, tender_id)
    if not tender or tender.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Tender not found")
    require_scope(principal, permission, tender.branch_id, tender.site_id)
    return tender


def audit(db: Session, principal: Principal, action: str, entity_type: str, entity_id: str | int | None, *, tender: Tender | None = None, detail: dict[str, Any] | None = None) -> None:
    db.add(TenderAuditEvent(
        company_id=principal.user.company_id,
        tender_id=tender.id if tender else None,
        branch_id=tender.branch_id if tender else None,
        actor=principal.user.full_name,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        detail=detail or {},
    ))


def issue_reference(db: Session, company_id: int, code: str, fallback_prefix: str) -> str:
    sequence = db.scalar(select(NumberSequence).where(NumberSequence.company_id == company_id, NumberSequence.code == code).with_for_update())
    if not sequence:
        sequence = NumberSequence(company_id=company_id, code=code, name=code.replace("_", " ").title(), prefix=fallback_prefix, next_number=1, padding=5, reset_period="yearly")
        db.add(sequence)
        db.flush()
    now = utcnow()
    reset_key = str(now.year) if sequence.reset_period == "yearly" else (now.strftime("%Y%m") if sequence.reset_period == "monthly" else None)
    if reset_key and sequence.last_reset_key != reset_key:
        sequence.next_number = 1
        sequence.last_reset_key = reset_key
    number = sequence.next_number
    sequence.next_number += 1
    period = f"-{reset_key}" if reset_key else ""
    return f"{sequence.prefix}{period}-{number:0{sequence.padding}d}"


def ensure_document(db: Session, company_id: int, document_id: int | None) -> None:
    if document_id is None:
        return
    document = db.get(Document, document_id)
    if not document or document.company_id != company_id:
        raise HTTPException(status_code=422, detail="Document does not belong to the active company")


def approval_setting(db: Session, company_id: int) -> dict[str, Any]:
    row = db.scalar(select(CompanySetting).where(CompanySetting.company_id == company_id, CompanySetting.key == "approval_control"))
    return row.value if row and isinstance(row.value, dict) else {"enabled": True, "allow_self_approval": False}


def reconcile_phase5(db: Session, company_id: int) -> None:
    permissions = {row.code: row for row in db.scalars(select(Permission)).all()}
    for code, (module, action, description) in EXTRA_PERMISSIONS.items():
        if code not in permissions:
            row = Permission(code=code, module=module, action=action, description=description)
            db.add(row)
            db.flush()
            permissions[code] = row

    roles = {row.code: row for row in db.scalars(select(Role).where(Role.company_id == company_id)).all()}
    for code, name, scope in (
        ("TENDER_MANAGER", "Tender Manager", "company"),
        ("ESTIMATOR", "Estimator / Quantity Surveyor", "branch"),
        ("TENDER_COORDINATOR", "Tender Coordinator", "branch"),
    ):
        if code not in roles:
            row = Role(company_id=company_id, code=code, name=name, description=f"Phase 5 {name.lower()} role", scope_level=scope, is_system=True, is_active=True)
            db.add(row)
            db.flush()
            roles[code] = row

    all_permissions = {row.code: row for row in db.scalars(select(Permission)).all()}
    for role_code, codes in ROLE_REQUIREMENTS.items():
        role = roles.get(role_code)
        if not role:
            continue
        existing = set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id == role.id)).all())
        for code in codes:
            permission = all_permissions.get(code)
            if permission and permission.id not in existing:
                db.add(RolePermission(role_id=role.id, permission_id=permission.id))
                existing.add(permission.id)

    for code, prefix, name in (
        ("TENDER", "TND", "Tender numbers"),
        ("TENDER_CLARIFICATION", "TCL", "Tender clarification numbers"),
    ):
        if not db.scalar(select(NumberSequence).where(NumberSequence.company_id == company_id, NumberSequence.code == code)):
            db.add(NumberSequence(company_id=company_id, code=code, name=name, prefix=prefix, next_number=1, padding=5, reset_period="yearly"))

    approver = roles.get("APPROVER") or roles.get("HQ_EXECUTIVE")
    executive = roles.get("HQ_EXECUTIVE") or approver
    if approver and executive:
        for code, name in (("TENDER_COMMERCIAL", "Tender Commercial Approval"), ("TENDER_SUBMISSION", "Tender Submission Approval")):
            workflow = db.scalar(select(ApprovalWorkflow).where(ApprovalWorkflow.company_id == company_id, ApprovalWorkflow.code == code))
            if not workflow:
                workflow = ApprovalWorkflow(company_id=company_id, code=code, name=name, module="tenders", description=f"Phase 5 controlled {name.lower()}", min_amount=Decimal("0"), is_active=True)
                db.add(workflow)
                db.flush()
                db.add(ApprovalStep(workflow_id=workflow.id, step_order=1, name="Tender Review", role_id=approver.id, required_approvals=1, escalation_hours=24))
                if executive.id != approver.id:
                    db.add(ApprovalStep(workflow_id=workflow.id, step_order=2, name="Executive Approval", role_id=executive.id, required_approvals=1, escalation_hours=24))

    if not db.scalar(select(CompanySetting).where(CompanySetting.company_id == company_id, CompanySetting.key == "tender_policy")):
        db.add(CompanySetting(company_id=company_id, key="tender_policy", value={"deadline_warning_days": 7, "minimum_margin_pct": 0, "require_commercial_approval": True, "require_submission_approval": True}, description="Phase 5 tender governance policy"))


def recalculate_tender(db: Session, tender: Tender) -> None:
    items = db.scalars(select(TenderEstimateItem).where(TenderEstimateItem.tender_id == tender.id)).all()
    direct = sum((Decimal(item.direct_total or 0) for item in items), Decimal("0"))
    selling = sum((Decimal(item.selling_total or 0) for item in items), Decimal("0"))
    tender.direct_cost_total = money(direct)
    tender.tender_price = money(selling)
    tender.gross_margin = money(selling - direct)
    tender.gross_margin_pct = (Decimal("0") if selling <= 0 else ((selling - direct) / selling * Decimal("100")).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))


class TenderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch_id: int
    site_id: int | None = None
    cost_centre_id: int | None = None
    lead_employee_id: int | None = None
    external_reference: str | None = Field(default=None, max_length=160)
    title: str = Field(min_length=3, max_length=300)
    client_name: str = Field(min_length=2, max_length=240)
    client_contact: str | None = Field(default=None, max_length=240)
    procurement_method: str | None = Field(default=None, max_length=100)
    source: str | None = Field(default=None, max_length=120)
    category: str | None = Field(default=None, max_length=120)
    location: str | None = Field(default=None, max_length=240)
    issue_date: date | None = None
    briefing_date: datetime | None = None
    site_visit_required: bool = False
    site_visit_date: datetime | None = None
    clarification_deadline: datetime | None = None
    submission_deadline: datetime
    opening_date: datetime | None = None
    validity_days: int | None = Field(default=None, ge=1, le=730)
    estimated_contract_value: Decimal | None = Field(default=None, ge=0)
    win_probability: int = Field(default=25, ge=0, le=100)
    priority: Literal["low", "normal", "high", "critical"] = "normal"
    notes: str | None = None


class BidDecisionInput(BaseModel):
    decision: Literal["bid", "no_bid"]
    reason: str = Field(min_length=3)


class TeamInput(BaseModel):
    employee_id: int
    role: Literal["lead", "estimator", "technical", "commercial", "document_control", "reviewer"]
    notes: str | None = None


class ChecklistInput(BaseModel):
    category: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=2, max_length=240)
    required: bool = True
    owner_employee_id: int | None = None
    document_id: int | None = None
    due_date: datetime | None = None
    status: Literal["missing", "in_progress", "ready", "not_applicable"] = "missing"
    notes: str | None = None


class EstimateInput(BaseModel):
    section: str | None = Field(default=None, max_length=160)
    item_code: str | None = Field(default=None, max_length=80)
    description: str = Field(min_length=2)
    unit: str = Field(default="item", min_length=1, max_length=32)
    quantity: Decimal = Field(default=1, gt=0)
    material_unit_cost: Decimal = Field(default=0, ge=0)
    labour_unit_cost: Decimal = Field(default=0, ge=0)
    plant_unit_cost: Decimal = Field(default=0, ge=0)
    subcontract_unit_cost: Decimal = Field(default=0, ge=0)
    other_unit_cost: Decimal = Field(default=0, ge=0)
    markup_pct: Decimal = Field(default=0, ge=-100, le=1000)
    sort_order: int = 0
    notes: str | None = None


class SecurityInput(BaseModel):
    security_type: Literal["bid_bond", "tender_security", "bank_guarantee", "insurance_bond", "other"]
    provider: str | None = Field(default=None, max_length=200)
    reference_number: str | None = Field(default=None, max_length=160)
    amount: Decimal = Field(default=0, ge=0)
    issue_date: date | None = None
    expiry_date: date | None = None
    status: Literal["required", "requested", "issued", "released", "expired", "not_required"] = "required"
    document_id: int | None = None
    notes: str | None = None


class ClarificationInput(BaseModel):
    question: str = Field(min_length=3)
    sent_to: str | None = Field(default=None, max_length=240)
    due_at: datetime | None = None
    document_id: int | None = None


class ClarificationResponseInput(BaseModel):
    response: str = Field(min_length=2)
    document_id: int | None = None


class ApprovalDecisionInput(BaseModel):
    decision: Literal["approve", "reject"]
    comment: str | None = None


class SubmissionInput(BaseModel):
    submission_method: Literal["physical", "portal", "email", "courier", "other"]
    submission_location: str | None = Field(default=None, max_length=300)
    submitted_at: datetime | None = None
    acknowledgement_reference: str | None = Field(default=None, max_length=200)
    acknowledgement_document_id: int | None = None
    notes: str | None = None


class OutcomeInput(BaseModel):
    outcome: Literal["awarded", "lost", "cancelled", "withdrawn"]
    decision_date: date | None = None
    awarded_amount: Decimal | None = Field(default=None, ge=0)
    winning_bidder: str | None = Field(default=None, max_length=240)
    winning_amount: Decimal | None = Field(default=None, ge=0)
    loss_reason: str | None = None
    lessons_learned: str | None = None
    award_document_id: int | None = None


@router.post("/bootstrap")
def bootstrap(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if not principal.has_company_permission("company.manage") and not principal.has_permission_anywhere("tenders.manage"):
        raise HTTPException(status_code=403, detail="Company administration or tenders.manage is required to initialise Phase 5")
    reconcile_phase5(db, principal.user.company_id)
    audit(db, principal, "tender.bootstrap", "phase", "5", detail={"status": "operational"})
    commit(db)
    return {"phase": 5, "status": "operational", "permissions": ["tenders.view", "tenders.manage", "tenders.approve", *EXTRA_PERMISSIONS]}


@router.get("/status")
def phase_status(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    initialized = bool(db.scalar(select(Permission.id).where(Permission.code == "tenders.estimate")))
    return {"phase": 5, "initialized": initialized, "status": "operational" if initialized else "not_initialized", "can_initialize": principal.has_company_permission("company.manage") or principal.has_permission_anywhere("tenders.manage")}


@router.get("/catalog")
def catalog(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_anywhere(principal, "tenders.view")
    company_id = principal.user.company_id
    branches = [row_dict(row) for row in db.scalars(select(Branch).where(Branch.company_id == company_id, Branch.is_active.is_(True)).order_by(Branch.name)).all() if principal.can("tenders.view", branch_id=row.id)]
    branch_ids = {int(row["id"]) for row in branches}
    sites = [row_dict(row) for row in db.scalars(select(Site).where(Site.company_id == company_id, Site.is_active.is_(True)).order_by(Site.name)).all() if row.branch_id in branch_ids and principal.can("tenders.view", branch_id=row.branch_id, site_id=row.id)]
    employees = []
    for employee in db.scalars(select(Employee).where(Employee.company_id == company_id, Employee.employment_status.in_(["active", "on_leave"])).order_by(Employee.first_name, Employee.last_name)).all():
        if employee.branch_id in branch_ids:
            employees.append({"id": employee.id, "employee_number": employee.employee_number, "full_name": " ".join(filter(None, [employee.first_name, employee.middle_names, employee.last_name])), "branch_id": employee.branch_id, "site_id": employee.site_id, "job_title": employee.job_title})
    centres = [row_dict(row) for row in db.scalars(select(CostCentre).where(CostCentre.company_id == company_id, CostCentre.is_active.is_(True)).order_by(CostCentre.code)).all() if row.branch_id is None or row.branch_id in branch_ids]
    workflows = [row_dict(row) for row in db.scalars(select(ApprovalWorkflow).where(ApprovalWorkflow.company_id == company_id, ApprovalWorkflow.module == "tenders", ApprovalWorkflow.is_active.is_(True))).all()]
    return {"branches": branches, "sites": sites, "employees": employees, "cost_centres": centres, "workflows": workflows, "permissions": sorted(code for code in principal.permission_codes if code.startswith("tenders."))}


@router.get("")
def list_tenders(db: Session = Depends(get_db), principal: Principal = Depends(current_principal), tender_status: str | None = Query(default=None, alias="status")) -> list[dict[str, Any]]:
    require_anywhere(principal, "tenders.view")
    rows = db.scalars(select(Tender).where(Tender.company_id == principal.user.company_id).order_by(Tender.submission_deadline, Tender.id.desc())).all()
    return [row_dict(row) for row in rows if principal.can("tenders.view", branch_id=row.branch_id, site_id=row.site_id) and (not tender_status or row.status == tender_status)]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_tender(payload: TenderInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_scope(principal, "tenders.manage", payload.branch_id, payload.site_id)
    ensure_scope(db, principal, payload.branch_id, payload.site_id, payload.cost_centre_id)
    employee_in_scope(db, principal, payload.lead_employee_id, payload.branch_id)
    if payload.submission_deadline <= utcnow():
        raise HTTPException(status_code=422, detail="Submission deadline must be in the future when registering a tender")
    if payload.site_visit_required and payload.site_visit_date is None:
        raise HTTPException(status_code=422, detail="A required site visit must have a date/time")
    tender = Tender(company_id=principal.user.company_id, tender_number=issue_reference(db, principal.user.company_id, "TENDER", "TND"), created_by=principal.user.full_name, **payload.model_dump())
    db.add(tender)
    db.flush()
    for category, name in STANDARD_CHECKLIST:
        db.add(TenderChecklistItem(company_id=tender.company_id, tender_id=tender.id, category=category, name=name, required=True, status="missing", due_date=tender.submission_deadline, updated_by=principal.user.full_name))
    if payload.lead_employee_id:
        db.add(TenderTeamMember(company_id=tender.company_id, tender_id=tender.id, employee_id=payload.lead_employee_id, role="lead", added_by=principal.user.full_name))
    audit(db, principal, "tender.created", "tender", tender.id, tender=tender, detail={"tender_number": tender.tender_number, "client": tender.client_name, "deadline": tender.submission_deadline.isoformat()})
    commit(db, "Tender reference already exists")
    db.refresh(tender)
    return row_dict(tender)


@router.get("/{tender_id}")
def tender_detail(tender_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    tender = tender_or_404(db, principal, tender_id)
    result = row_dict(tender)
    result["team"] = [row_dict(row) for row in db.scalars(select(TenderTeamMember).where(TenderTeamMember.tender_id == tender.id).order_by(TenderTeamMember.id)).all()]
    result["checklist"] = [row_dict(row) for row in db.scalars(select(TenderChecklistItem).where(TenderChecklistItem.tender_id == tender.id).order_by(TenderChecklistItem.category, TenderChecklistItem.id)).all()]
    result["estimate_items"] = [row_dict(row) for row in db.scalars(select(TenderEstimateItem).where(TenderEstimateItem.tender_id == tender.id).order_by(TenderEstimateItem.sort_order, TenderEstimateItem.id)).all()]
    result["securities"] = [row_dict(row) for row in db.scalars(select(TenderSecurity).where(TenderSecurity.tender_id == tender.id).order_by(TenderSecurity.id)).all()]
    result["clarifications"] = [row_dict(row) for row in db.scalars(select(TenderClarification).where(TenderClarification.tender_id == tender.id).order_by(TenderClarification.id.desc())).all()]
    result["submissions"] = [row_dict(row) for row in db.scalars(select(TenderSubmission).where(TenderSubmission.tender_id == tender.id).order_by(TenderSubmission.version.desc())).all()]
    outcome = db.scalar(select(TenderOutcome).where(TenderOutcome.tender_id == tender.id))
    result["outcome"] = row_dict(outcome) if outcome else None
    for key, request_id in (("commercial_approval", tender.commercial_approval_request_id), ("submission_approval", tender.submission_approval_request_id)):
        request = db.get(ApprovalRequest, request_id) if request_id else None
        result[key] = row_dict(request) if request else None
    return result


@router.post("/{tender_id}/bid-decision")
def bid_decision(tender_id: int, payload: BidDecisionInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    tender = tender_or_404(db, principal, tender_id, "tenders.approve")
    if tender.status in {"submitted", "awarded", "lost", "cancelled"}:
        raise HTTPException(status_code=409, detail="Bid decision cannot change after submission/outcome")
    tender.bid_decision = payload.decision
    tender.bid_decision_reason = payload.reason
    tender.bid_decided_by = principal.user.full_name
    tender.bid_decided_at = utcnow()
    tender.status = "preparing" if payload.decision == "bid" else "no_bid"
    audit(db, principal, f"tender.bid_decision.{payload.decision}", "tender", tender.id, tender=tender, detail={"reason": payload.reason})
    commit(db)
    return row_dict(tender)


@router.post("/{tender_id}/team", status_code=201)
def add_team_member(tender_id: int, payload: TeamInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    tender = tender_or_404(db, principal, tender_id, "tenders.manage")
    employee_in_scope(db, principal, payload.employee_id, tender.branch_id)
    row = TenderTeamMember(company_id=tender.company_id, tender_id=tender.id, employee_id=payload.employee_id, role=payload.role, notes=payload.notes, added_by=principal.user.full_name)
    db.add(row)
    db.flush()
    audit(db, principal, "tender.team.added", "tender_team_member", row.id, tender=tender, detail={"employee_id": payload.employee_id, "role": payload.role})
    commit(db, "Employee already has this tender role")
    return row_dict(row)


@router.post("/{tender_id}/checklist", status_code=201)
def add_checklist(tender_id: int, payload: ChecklistInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    tender = tender_or_404(db, principal, tender_id, "tenders.manage")
    employee_in_scope(db, principal, payload.owner_employee_id, tender.branch_id)
    ensure_document(db, tender.company_id, payload.document_id)
    row = TenderChecklistItem(company_id=tender.company_id, tender_id=tender.id, updated_by=principal.user.full_name, **payload.model_dump())
    db.add(row)
    db.flush()
    audit(db, principal, "tender.checklist.created", "tender_checklist_item", row.id, tender=tender, detail={"name": row.name, "status": row.status})
    commit(db)
    return row_dict(row)


@router.put("/checklist/{item_id}")
def update_checklist(item_id: int, payload: ChecklistInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = db.get(TenderChecklistItem, item_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Checklist item not found")
    tender = tender_or_404(db, principal, row.tender_id, "tenders.manage")
    employee_in_scope(db, principal, payload.owner_employee_id, tender.branch_id)
    ensure_document(db, tender.company_id, payload.document_id)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    row.updated_by = principal.user.full_name
    audit(db, principal, "tender.checklist.updated", "tender_checklist_item", row.id, tender=tender, detail={"status": row.status, "document_id": row.document_id})
    commit(db)
    return row_dict(row)


def calculate_item(payload: EstimateInput) -> dict[str, Decimal]:
    direct_unit = rate(payload.material_unit_cost + payload.labour_unit_cost + payload.plant_unit_cost + payload.subcontract_unit_cost + payload.other_unit_cost)
    direct_total = money(direct_unit * payload.quantity)
    selling_rate = rate(direct_unit * (Decimal("1") + payload.markup_pct / Decimal("100")))
    selling_total = money(selling_rate * payload.quantity)
    return {"direct_unit_cost": direct_unit, "direct_total": direct_total, "selling_rate": selling_rate, "selling_total": selling_total}


@router.post("/{tender_id}/estimate-items", status_code=201)
def add_estimate_item(tender_id: int, payload: EstimateInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    tender = tender_or_404(db, principal, tender_id, "tenders.estimate")
    if tender.bid_decision != "bid":
        raise HTTPException(status_code=409, detail="Tender must have an approved Bid decision before estimating")
    values = payload.model_dump()
    values.update(calculate_item(payload))
    row = TenderEstimateItem(company_id=tender.company_id, tender_id=tender.id, created_by=principal.user.full_name, **values)
    db.add(row)
    db.flush()
    recalculate_tender(db, tender)
    audit(db, principal, "tender.estimate_item.created", "tender_estimate_item", row.id, tender=tender, detail={"description": row.description, "selling_total": str(row.selling_total)})
    commit(db)
    return row_dict(row)


@router.put("/estimate-items/{item_id}")
def update_estimate_item(item_id: int, payload: EstimateInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = db.get(TenderEstimateItem, item_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Estimate item not found")
    tender = tender_or_404(db, principal, row.tender_id, "tenders.estimate")
    values = payload.model_dump()
    values.update(calculate_item(payload))
    for key, value in values.items():
        setattr(row, key, value)
    recalculate_tender(db, tender)
    audit(db, principal, "tender.estimate_item.updated", "tender_estimate_item", row.id, tender=tender, detail={"selling_total": str(row.selling_total)})
    commit(db)
    return row_dict(row)


@router.delete("/estimate-items/{item_id}", status_code=204)
def delete_estimate_item(item_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> None:
    row = db.get(TenderEstimateItem, item_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Estimate item not found")
    tender = tender_or_404(db, principal, row.tender_id, "tenders.estimate")
    if tender.status in {"submitted", "awarded", "lost"}:
        raise HTTPException(status_code=409, detail="Submitted tender pricing cannot be altered")
    db.delete(row)
    db.flush()
    recalculate_tender(db, tender)
    audit(db, principal, "tender.estimate_item.deleted", "tender_estimate_item", item_id, tender=tender)
    commit(db)


@router.post("/{tender_id}/securities", status_code=201)
def add_security(tender_id: int, payload: SecurityInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    tender = tender_or_404(db, principal, tender_id, "tenders.manage")
    if payload.expiry_date and payload.issue_date and payload.expiry_date < payload.issue_date:
        raise HTTPException(status_code=422, detail="Security expiry cannot precede issue date")
    ensure_document(db, tender.company_id, payload.document_id)
    row = TenderSecurity(company_id=tender.company_id, tender_id=tender.id, created_by=principal.user.full_name, **payload.model_dump())
    db.add(row)
    db.flush()
    audit(db, principal, "tender.security.created", "tender_security", row.id, tender=tender, detail={"type": row.security_type, "amount": str(row.amount), "status": row.status})
    commit(db)
    return row_dict(row)


@router.post("/{tender_id}/clarifications", status_code=201)
def add_clarification(tender_id: int, payload: ClarificationInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    tender = tender_or_404(db, principal, tender_id, "tenders.manage")
    ensure_document(db, tender.company_id, payload.document_id)
    row = TenderClarification(company_id=tender.company_id, tender_id=tender.id, clarification_number=issue_reference(db, tender.company_id, "TENDER_CLARIFICATION", "TCL"), question=payload.question, sent_to=payload.sent_to, due_at=payload.due_at, document_id=payload.document_id, raised_by=principal.user.full_name)
    db.add(row)
    db.flush()
    audit(db, principal, "tender.clarification.raised", "tender_clarification", row.id, tender=tender, detail={"number": row.clarification_number})
    commit(db)
    return row_dict(row)


@router.post("/clarifications/{clarification_id}/respond")
def respond_clarification(clarification_id: int, payload: ClarificationResponseInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = db.get(TenderClarification, clarification_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Clarification not found")
    tender = tender_or_404(db, principal, row.tender_id, "tenders.manage")
    ensure_document(db, tender.company_id, payload.document_id)
    row.response = payload.response
    row.document_id = payload.document_id or row.document_id
    row.status = "answered"
    row.responded_at = utcnow()
    audit(db, principal, "tender.clarification.answered", "tender_clarification", row.id, tender=tender)
    commit(db)
    return row_dict(row)


def create_approval(db: Session, principal: Principal, tender: Tender, workflow_code: str, title: str) -> ApprovalRequest:
    workflow = db.scalar(select(ApprovalWorkflow).where(ApprovalWorkflow.company_id == tender.company_id, ApprovalWorkflow.code == workflow_code, ApprovalWorkflow.is_active.is_(True)))
    if not workflow:
        raise HTTPException(status_code=409, detail=f"Approval workflow {workflow_code} is not configured")
    if not db.scalar(select(ApprovalStep.id).where(ApprovalStep.workflow_id == workflow.id)):
        raise HTTPException(status_code=409, detail="Approval workflow has no steps")
    request = ApprovalRequest(company_id=tender.company_id, workflow_id=workflow.id, branch_id=tender.branch_id, site_id=tender.site_id, entity_type="tender", entity_id=str(tender.id), reference=issue_reference(db, tender.company_id, "APPROVAL", "APR"), title=title, amount=tender.tender_price, status="pending", current_step_order=1, requested_by=principal.user.full_name)
    db.add(request)
    db.flush()
    return request


@router.post("/{tender_id}/commercial-approval")
def request_commercial_approval(tender_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    tender = tender_or_404(db, principal, tender_id, "tenders.manage")
    if tender.bid_decision != "bid" or tender.tender_price <= 0:
        raise HTTPException(status_code=409, detail="Approved Bid decision and priced estimate are required")
    if tender.commercial_approval_request_id:
        existing = db.get(ApprovalRequest, tender.commercial_approval_request_id)
        if existing and existing.status == "pending":
            return row_dict(existing)
    request = create_approval(db, principal, tender, "TENDER_COMMERCIAL", f"Commercial approval: {tender.tender_number} - {tender.title}")
    tender.commercial_approval_request_id = request.id
    tender.status = "review"
    audit(db, principal, "tender.commercial_approval.requested", "approval_request", request.id, tender=tender, detail={"reference": request.reference, "amount": str(request.amount)})
    commit(db)
    return row_dict(request)


@router.post("/{tender_id}/submission-approval")
def request_submission_approval(tender_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    tender = tender_or_404(db, principal, tender_id, "tenders.manage")
    commercial = db.get(ApprovalRequest, tender.commercial_approval_request_id) if tender.commercial_approval_request_id else None
    if not commercial or commercial.status != "approved":
        raise HTTPException(status_code=409, detail="Commercial approval must be complete before submission approval")
    missing = db.scalar(select(func.count()).select_from(TenderChecklistItem).where(TenderChecklistItem.tender_id == tender.id, TenderChecklistItem.required.is_(True), TenderChecklistItem.status != "ready")) or 0
    if missing:
        raise HTTPException(status_code=409, detail=f"{missing} required checklist item(s) are not ready")
    request = create_approval(db, principal, tender, "TENDER_SUBMISSION", f"Submission approval: {tender.tender_number} - {tender.title}")
    tender.submission_approval_request_id = request.id
    audit(db, principal, "tender.submission_approval.requested", "approval_request", request.id, tender=tender, detail={"reference": request.reference})
    commit(db)
    return row_dict(request)


def assignment_authorised(db: Session, principal: Principal, role_id: int, tender: Tender) -> bool:
    now = utcnow()
    rows = db.scalars(select(UserRoleAssignment).where(UserRoleAssignment.user_id == principal.user.id, UserRoleAssignment.role_id == role_id)).all()
    role = db.get(Role, role_id)
    if not role:
        return False
    for assignment in rows:
        if assignment.valid_from and assignment.valid_from > now:
            continue
        if assignment.valid_until and assignment.valid_until < now:
            continue
        if role.scope_level == "company":
            return True
        if role.scope_level == "branch" and assignment.branch_id == tender.branch_id:
            return True
        if role.scope_level == "site" and tender.site_id is not None and assignment.site_id == tender.site_id:
            return True
    return False


@router.post("/approvals/{request_id}/decision")
def decide_tender_approval(request_id: int, payload: ApprovalDecisionInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    request = db.get(ApprovalRequest, request_id)
    if not request or request.company_id != principal.user.company_id or request.entity_type != "tender":
        raise HTTPException(status_code=404, detail="Tender approval request not found")
    tender = tender_or_404(db, principal, int(request.entity_id), "tenders.approve")
    if request.status != "pending":
        raise HTTPException(status_code=409, detail=f"Approval request is already {request.status}")
    step = db.scalar(select(ApprovalStep).where(ApprovalStep.workflow_id == request.workflow_id, ApprovalStep.step_order == request.current_step_order))
    if not step:
        raise HTTPException(status_code=409, detail="Current approval step is not configured")
    if not assignment_authorised(db, principal, step.role_id, tender):
        raise HTTPException(status_code=403, detail="Your active role assignment is not authorised for the current approval step")
    if request.requested_by == principal.user.full_name and not bool(approval_setting(db, tender.company_id).get("allow_self_approval", False)):
        raise HTTPException(status_code=422, detail="Self-approval is disabled by company approval policy")
    db.add(ApprovalAction(request_id=request.id, step_order=step.step_order, role_id=step.role_id, actor_name=principal.user.full_name, action=payload.decision, comment=payload.comment))
    if payload.decision == "reject":
        request.status = "rejected"
        request.completed_at = utcnow()
    else:
        approved_count = (db.scalar(select(func.count()).select_from(ApprovalAction).where(ApprovalAction.request_id == request.id, ApprovalAction.step_order == step.step_order, ApprovalAction.action == "approve")) or 0) + 1
        if approved_count >= step.required_approvals:
            next_step = db.scalar(select(ApprovalStep).where(ApprovalStep.workflow_id == request.workflow_id, ApprovalStep.step_order > step.step_order).order_by(ApprovalStep.step_order).limit(1))
            if next_step:
                request.current_step_order = next_step.step_order
            else:
                request.status = "approved"
                request.completed_at = utcnow()
    if request.id == tender.commercial_approval_request_id and request.status == "approved":
        tender.status = "approved"
    audit(db, principal, f"tender.approval.{payload.decision}", "approval_request", request.id, tender=tender, detail={"step": step.step_order, "status": request.status})
    commit(db)
    return row_dict(request)


@router.post("/{tender_id}/submit", status_code=201)
def record_submission(tender_id: int, payload: SubmissionInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    tender = tender_or_404(db, principal, tender_id, "tenders.submit")
    approval = db.get(ApprovalRequest, tender.submission_approval_request_id) if tender.submission_approval_request_id else None
    if not approval or approval.status != "approved":
        raise HTTPException(status_code=409, detail="Submission approval must be complete")
    missing = db.scalar(select(func.count()).select_from(TenderChecklistItem).where(TenderChecklistItem.tender_id == tender.id, TenderChecklistItem.required.is_(True), TenderChecklistItem.status != "ready")) or 0
    if missing:
        raise HTTPException(status_code=409, detail="Required tender checklist is incomplete")
    required_security = db.scalars(select(TenderSecurity).where(TenderSecurity.tender_id == tender.id, TenderSecurity.status.not_in(["issued", "not_required", "released"]))).all()
    if required_security:
        raise HTTPException(status_code=409, detail="Tender security requirements are not complete")
    ensure_document(db, tender.company_id, payload.acknowledgement_document_id)
    version = (db.scalar(select(func.max(TenderSubmission.version)).where(TenderSubmission.tender_id == tender.id)) or 0) + 1
    row = TenderSubmission(company_id=tender.company_id, tender_id=tender.id, version=version, submission_method=payload.submission_method, submission_location=payload.submission_location, submitted_at=payload.submitted_at or utcnow(), submitted_by=principal.user.full_name, acknowledgement_reference=payload.acknowledgement_reference, acknowledgement_document_id=payload.acknowledgement_document_id, tender_price=tender.tender_price, notes=payload.notes)
    db.add(row)
    db.flush()
    tender.status = "submitted"
    audit(db, principal, "tender.submitted", "tender_submission", row.id, tender=tender, detail={"version": version, "method": row.submission_method, "price": str(row.tender_price)})
    commit(db)
    return row_dict(row)


@router.post("/{tender_id}/outcome")
def record_outcome(tender_id: int, payload: OutcomeInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    tender = tender_or_404(db, principal, tender_id, "tenders.manage")
    if tender.status != "submitted" and payload.outcome in {"awarded", "lost"}:
        raise HTTPException(status_code=409, detail="Award/loss can only be recorded after submission")
    ensure_document(db, tender.company_id, payload.award_document_id)
    row = db.scalar(select(TenderOutcome).where(TenderOutcome.tender_id == tender.id))
    values = payload.model_dump()
    if row:
        for key, value in values.items():
            setattr(row, key, value)
        row.recorded_by = principal.user.full_name
        row.recorded_at = utcnow()
    else:
        row = TenderOutcome(company_id=tender.company_id, tender_id=tender.id, recorded_by=principal.user.full_name, **values)
        db.add(row)
        db.flush()
    tender.status = payload.outcome
    audit(db, principal, f"tender.outcome.{payload.outcome}", "tender_outcome", row.id, tender=tender, detail={"awarded_amount": str(payload.awarded_amount) if payload.awarded_amount is not None else None, "winning_bidder": payload.winning_bidder})
    commit(db)
    return row_dict(row)


@router.get("/{tender_id}/mobilisation-handoff")
def mobilisation_handoff(tender_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    tender = tender_or_404(db, principal, tender_id)
    outcome = db.scalar(select(TenderOutcome).where(TenderOutcome.tender_id == tender.id))
    if tender.status != "awarded" or not outcome or outcome.outcome != "awarded":
        raise HTTPException(status_code=409, detail="Only an awarded tender is ready for Phase 6 mobilisation")
    submission = db.scalar(select(TenderSubmission).where(TenderSubmission.tender_id == tender.id).order_by(TenderSubmission.version.desc()).limit(1))
    if not submission:
        raise HTTPException(status_code=409, detail="Awarded tender has no controlled submission evidence")
    return {
        "handoff_version": 1,
        "source_phase": 5,
        "target_phase": 6,
        "tender": row_dict(tender),
        "outcome": row_dict(outcome),
        "submission": row_dict(submission),
        "estimate_items": [row_dict(row) for row in db.scalars(select(TenderEstimateItem).where(TenderEstimateItem.tender_id == tender.id).order_by(TenderEstimateItem.sort_order, TenderEstimateItem.id)).all()],
        "team": [row_dict(row) for row in db.scalars(select(TenderTeamMember).where(TenderTeamMember.tender_id == tender.id)).all()],
        "commercial_totals": {"direct_cost_total": str(tender.direct_cost_total), "tender_price": str(tender.tender_price), "gross_margin": str(tender.gross_margin), "gross_margin_pct": str(tender.gross_margin_pct), "awarded_amount": str(outcome.awarded_amount or tender.tender_price)},
        "ready": True,
    }


@router.get("/dashboard/summary")
def dashboard(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_anywhere(principal, "tenders.view")
    tenders = [row for row in db.scalars(select(Tender).where(Tender.company_id == principal.user.company_id)).all() if principal.can("tenders.view", branch_id=row.branch_id, site_id=row.site_id)]
    active = [row for row in tenders if row.status not in {"no_bid", "submitted", "awarded", "lost", "cancelled", "withdrawn"}]
    weighted = sum((Decimal(row.tender_price or row.estimated_contract_value or 0) * Decimal(row.win_probability) / Decimal("100") for row in active), Decimal("0"))
    pipeline = sum((Decimal(row.tender_price or row.estimated_contract_value or 0) for row in active), Decimal("0"))
    outcomes = [db.scalar(select(TenderOutcome).where(TenderOutcome.tender_id == row.id)) for row in tenders]
    awarded = [row for row in outcomes if row and row.outcome == "awarded"]
    lost = [row for row in outcomes if row and row.outcome == "lost"]
    return {"total": len(tenders), "active": len(active), "submitted": sum(row.status == "submitted" for row in tenders), "awarded": len(awarded), "lost": len(lost), "pipeline_value": str(money(pipeline)), "weighted_pipeline_value": str(money(weighted)), "win_rate_pct": round((len(awarded) / (len(awarded) + len(lost)) * 100), 2) if awarded or lost else 0}


@router.get("/dashboard/alerts")
def alerts(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    require_anywhere(principal, "tenders.view")
    policy = db.scalar(select(CompanySetting).where(CompanySetting.company_id == principal.user.company_id, CompanySetting.key == "tender_policy"))
    warning_days = int(policy.value.get("deadline_warning_days", 7)) if policy and isinstance(policy.value, dict) else 7
    now = utcnow()
    result: list[dict[str, Any]] = []
    tenders = [row for row in db.scalars(select(Tender).where(Tender.company_id == principal.user.company_id)).all() if principal.can("tenders.view", branch_id=row.branch_id, site_id=row.site_id)]
    for tender in tenders:
        if tender.status in {"no_bid", "awarded", "lost", "cancelled", "withdrawn"}:
            continue
        hours = (tender.submission_deadline - now).total_seconds() / 3600
        if hours <= warning_days * 24:
            result.append({"type": "deadline", "severity": "critical" if hours <= 24 else "warning", "tender_id": tender.id, "tender_number": tender.tender_number, "message": f"Submission deadline {tender.submission_deadline.isoformat()}"})
        missing = db.scalar(select(func.count()).select_from(TenderChecklistItem).where(TenderChecklistItem.tender_id == tender.id, TenderChecklistItem.required.is_(True), TenderChecklistItem.status != "ready")) or 0
        if missing:
            result.append({"type": "checklist", "severity": "warning", "tender_id": tender.id, "tender_number": tender.tender_number, "message": f"{missing} required checklist item(s) not ready"})
    for security_row in db.scalars(select(TenderSecurity).where(TenderSecurity.company_id == principal.user.company_id, TenderSecurity.expiry_date.is_not(None), TenderSecurity.status == "issued")).all():
        tender = next((row for row in tenders if row.id == security_row.tender_id), None)
        if tender and security_row.expiry_date and security_row.expiry_date <= date.today() + timedelta(days=warning_days):
            result.append({"type": "security", "severity": "critical" if security_row.expiry_date < date.today() else "warning", "tender_id": tender.id, "tender_number": tender.tender_number, "message": f"{security_row.security_type} expires {security_row.expiry_date.isoformat()}"})
    for clarification in db.scalars(select(TenderClarification).where(TenderClarification.company_id == principal.user.company_id, TenderClarification.status == "open")).all():
        tender = next((row for row in tenders if row.id == clarification.tender_id), None)
        if tender and clarification.due_at and clarification.due_at <= now + timedelta(days=warning_days):
            result.append({"type": "clarification", "severity": "warning", "tender_id": tender.id, "tender_number": tender.tender_number, "message": f"Clarification {clarification.clarification_number} due {clarification.due_at.isoformat()}"})
    return result


@router.get("/export.csv")
def export_csv(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> StreamingResponse:
    require_anywhere(principal, "tenders.export")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Tender Number", "Reference", "Title", "Client", "Branch ID", "Deadline", "Status", "Bid Decision", "Probability %", "Direct Cost", "Tender Price", "Gross Margin", "Margin %"])
    for tender in db.scalars(select(Tender).where(Tender.company_id == principal.user.company_id).order_by(Tender.submission_deadline)).all():
        if not principal.can("tenders.export", branch_id=tender.branch_id, site_id=tender.site_id):
            continue
        writer.writerow([tender.tender_number, tender.external_reference or "", tender.title, tender.client_name, tender.branch_id, tender.submission_deadline.isoformat(), tender.status, tender.bid_decision, tender.win_probability, tender.direct_cost_total, tender.tender_price, tender.gross_margin, tender.gross_margin_pct])
    return StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=buildtrack-tender-pipeline.csv"})


@router.get("/audit/events")
def audit_events(db: Session = Depends(get_db), principal: Principal = Depends(current_principal), limit: int = Query(default=200, ge=1, le=1000)) -> list[dict[str, Any]]:
    require_anywhere(principal, "tenders.view")
    rows = db.scalars(select(TenderAuditEvent).where(TenderAuditEvent.company_id == principal.user.company_id).order_by(TenderAuditEvent.occurred_at.desc()).limit(limit)).all()
    return [row_dict(row) for row in rows if row.branch_id is None or principal.can("tenders.view", branch_id=row.branch_id)]
