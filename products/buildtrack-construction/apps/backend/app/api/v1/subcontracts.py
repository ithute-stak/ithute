from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.procurement import (
    MONEY, allow_self_approval, assignment_authorised, commit, ensure_document,
    issue_reference, json_value, money, row_dict, utcnow,
)
from app.db.session import get_db
from app.models import (
    ApprovalAction, ApprovalRequest, ApprovalStep, ApprovalWorkflow, Branch,
    CompanySetting, CostCentre, Document, NumberSequence, Permission, Project,
    ProjectSiteLink, Role, RolePermission, SubcontractAuditEvent,
    SubcontractBid, SubcontractBidLine, SubcontractCertificate,
    SubcontractContract, SubcontractEvaluation, SubcontractInvitation,
    SubcontractPackage, SubcontractPackageLine, SubcontractPayment,
    SubcontractPerformanceReview, SubcontractVariation, Subcontractor,
)
from app.security.access import Principal, current_principal

router = APIRouter(prefix="/subcontracts", tags=["Phase 9 - Subcontract Management"])

PERMISSION_ACTIONS = {
    "subcontracts.view": ("subcontracts", "view", "View subcontractors, packages, contracts and certificates"),
    "subcontracts.manage": ("subcontracts", "manage", "Create and manage subcontract packages and evidence"),
    "subcontracts.approve": ("subcontracts", "approve", "Approve awards, contracts, variations and certificates"),
    "subcontracts.certify": ("subcontracts", "certify", "Prepare work certificates and performance evidence"),
    "subcontracts.pay": ("subcontracts", "pay", "Record supplied subcontract payment evidence"),
    "subcontracts.export": ("subcontracts", "export", "Export subcontract commercial evidence"),
}
POLICY_DEFAULT = {
    "minimum_bids": 3,
    "low_value_bid_waiver": 5000,
    "default_retention_pct": 5,
    "max_retention_pct": 15,
    "certificate_requires_document": True,
    "performance_alert_score": 2.5,
}


def require_anywhere(principal: Principal, permission: str) -> None:
    if not principal.has_permission_anywhere(permission):
        raise HTTPException(status_code=403, detail=f"Permission required: {permission}")


def require_company(principal: Principal, permission: str) -> None:
    if not principal.has_company_permission(permission):
        raise HTTPException(status_code=403, detail=f"Company-level permission required: {permission}")


def require_scope(principal: Principal, permission: str, branch_id: int, site_id: int | None = None) -> None:
    if not principal.can(permission, branch_id=branch_id, site_id=site_id):
        raise HTTPException(status_code=403, detail=f"Permission required in this branch/site: {permission}")


def audit(db: Session, principal: Principal, action: str, entity_type: str, entity_id: int | str | None, *, branch_id: int | None = None, site_id: int | None = None, detail: dict[str, Any] | None = None) -> None:
    db.add(SubcontractAuditEvent(
        company_id=principal.user.company_id, branch_id=branch_id, site_id=site_id,
        actor=principal.user.full_name, action=action, entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None, detail=detail or {},
    ))


def policy(db: Session, company_id: int) -> dict[str, Any]:
    row = db.scalar(select(CompanySetting).where(
        CompanySetting.company_id == company_id, CompanySetting.key == "subcontract_policy",
    ))
    return {**POLICY_DEFAULT, **(row.value if row and isinstance(row.value, dict) else {})}


def ensure_scope(db: Session, company_id: int, branch_id: int, site_id: int | None, project_id: int, cost_centre_id: int | None) -> Project:
    branch = db.get(Branch, branch_id)
    project = db.get(Project, project_id)
    if not branch or branch.company_id != company_id:
        raise HTTPException(status_code=422, detail="Branch does not belong to the company")
    if not project or project.company_id != company_id or project.branch_id != branch_id:
        raise HTTPException(status_code=422, detail="Project does not belong to the selected branch")
    if site_id is not None:
        valid_site = db.scalar(select(ProjectSiteLink.id).where(
            ProjectSiteLink.project_id == project.id, ProjectSiteLink.site_id == site_id,
        ))
        if not valid_site:
            raise HTTPException(status_code=422, detail="Site is not linked to the selected project")
    if cost_centre_id is not None:
        centre = db.get(CostCentre, cost_centre_id)
        if not centre or centre.company_id != company_id:
            raise HTTPException(status_code=422, detail="Cost centre does not belong to the company")
        if centre.branch_id is not None and centre.branch_id != branch_id:
            raise HTTPException(status_code=422, detail="Cost centre is outside the selected branch")
        if site_id and centre.site_id and centre.site_id != site_id:
            raise HTTPException(status_code=422, detail="Cost centre is outside the selected site")
    return project


def package_or_404(db: Session, principal: Principal, package_id: int, permission: str = "subcontracts.view") -> SubcontractPackage:
    row = db.get(SubcontractPackage, package_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Subcontract package not found")
    require_scope(principal, permission, row.branch_id, row.site_id)
    return row


def contract_or_404(db: Session, principal: Principal, contract_id: int, permission: str = "subcontracts.view") -> SubcontractContract:
    row = db.get(SubcontractContract, contract_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Subcontract contract not found")
    require_scope(principal, permission, row.branch_id, row.site_id)
    return row


def workflow(db: Session, company_id: int, code: str) -> ApprovalWorkflow:
    row = db.scalar(select(ApprovalWorkflow).where(
        ApprovalWorkflow.company_id == company_id, ApprovalWorkflow.code == code,
        ApprovalWorkflow.is_active.is_(True),
    ))
    if not row or not db.scalar(select(func.count()).select_from(ApprovalStep).where(ApprovalStep.workflow_id == row.id)):
        raise HTTPException(status_code=409, detail=f"Approval workflow {code} is not configured")
    return row


def create_approval(db: Session, principal: Principal, *, code: str, entity_type: str, entity_id: int, title: str, package: SubcontractPackage, amount: Decimal) -> ApprovalRequest:
    selected = workflow(db, principal.user.company_id, code)
    row = ApprovalRequest(
        company_id=principal.user.company_id, workflow_id=selected.id, branch_id=package.branch_id,
        site_id=package.site_id, entity_type=entity_type, entity_id=str(entity_id),
        reference=issue_reference(db, principal.user.company_id, "APPROVAL", "APR"),
        title=title, amount=money(amount), status="pending", current_step_order=1,
        requested_by=principal.user.full_name,
    )
    db.add(row)
    db.flush()
    return row


def contract_ceiling(db: Session, contract: SubcontractContract) -> Decimal:
    approved_variations = db.scalar(select(func.coalesce(func.sum(SubcontractVariation.value), 0)).where(
        SubcontractVariation.contract_id == contract.id, SubcontractVariation.status == "approved",
    )) or Decimal("0")
    return money(Decimal(contract.original_contract_sum) + Decimal(approved_variations))


def payment_total(db: Session, certificate_id: int) -> Decimal:
    total = db.scalar(select(func.coalesce(func.sum(SubcontractPayment.amount), 0)).where(
        SubcontractPayment.certificate_id == certificate_id,
    ))
    return money(total or 0)


def bootstrap_permissions(db: Session, company_id: int) -> None:
    permissions: dict[str, Permission] = {}
    for code, (module, action, description) in PERMISSION_ACTIONS.items():
        row = db.scalar(select(Permission).where(Permission.code == code))
        if not row:
            row = Permission(code=code, module=module, action=action, description=description)
            db.add(row)
            db.flush()
        permissions[code] = row
    roles = {row.code: row for row in db.scalars(select(Role).where(Role.company_id == company_id)).all()}
    for code, name, scope in (
        ("SUBCONTRACT_MANAGER", "Subcontract Manager", "company"),
        ("SUBCONTRACT_OFFICER", "Subcontract Officer", "branch"),
        ("SITE_COMMERCIAL_OFFICER", "Site Commercial Officer", "site"),
    ):
        if code not in roles:
            role = Role(company_id=company_id, code=code, name=name, scope_level=scope,
                        description=f"Phase 9 {name.lower()} role", is_system=True, is_active=True)
            db.add(role)
            db.flush()
            roles[code] = role
    grants = {
        "SYSTEM_ADMIN": set(PERMISSION_ACTIONS),
        "HQ_EXECUTIVE": {"subcontracts.view", "subcontracts.approve", "subcontracts.export"},
        "BRANCH_MANAGER": {"subcontracts.view", "subcontracts.manage", "subcontracts.approve", "subcontracts.certify", "subcontracts.export"},
        "SITE_MANAGER": {"subcontracts.view", "subcontracts.manage", "subcontracts.certify"},
        "PROJECT_MANAGER": {"subcontracts.view", "subcontracts.manage", "subcontracts.certify"},
        "APPROVER": {"subcontracts.approve"},
        "AUDITOR": {"subcontracts.view", "subcontracts.export"},
        "SUBCONTRACT_MANAGER": set(PERMISSION_ACTIONS),
        "SUBCONTRACT_OFFICER": {"subcontracts.view", "subcontracts.manage", "subcontracts.certify", "subcontracts.export"},
        "SITE_COMMERCIAL_OFFICER": {"subcontracts.view", "subcontracts.certify"},
    }
    for role_code, codes in grants.items():
        role = roles.get(role_code)
        if not role:
            continue
        existing = set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id == role.id)).all())
        for code in codes:
            if permissions[code].id not in existing:
                db.add(RolePermission(role_id=role.id, permission_id=permissions[code].id))
                existing.add(permissions[code].id)
    for code, name, prefix in (
        ("SUBCONTRACTOR", "Subcontractor Number", "SUB"),
        ("SUBCONTRACT_PACKAGE", "Subcontract Package", "SCP"),
        ("SUBCONTRACT_INVITATION", "Subcontract Invitation", "SCI"),
        ("SUBCONTRACT_BID", "Subcontract Bid", "SCB"),
        ("SUBCONTRACT_CONTRACT", "Subcontract Contract", "SCT"),
        ("SUBCONTRACT_VARIATION", "Subcontract Variation", "SCV"),
        ("SUBCONTRACT_CERTIFICATE", "Subcontract Certificate", "SCC"),
    ):
        if not db.scalar(select(NumberSequence).where(NumberSequence.company_id == company_id, NumberSequence.code == code)):
            db.add(NumberSequence(company_id=company_id, code=code, name=name, prefix=prefix, next_number=1, padding=5, reset_period="yearly"))
    branch, hq = roles.get("BRANCH_MANAGER"), roles.get("HQ_EXECUTIVE")
    if not branch or not hq:
        raise HTTPException(status_code=409, detail="Branch Manager and HQ Executive roles are required")
    for code, name in (
        ("SUBCONTRACT_AWARD", "Subcontract Award Approval"),
        ("SUBCONTRACT_CONTRACT", "Subcontract Contract Approval"),
        ("SUBCONTRACT_VARIATION", "Subcontract Variation Approval"),
        ("SUBCONTRACT_CERTIFICATE", "Subcontract Certificate Approval"),
    ):
        wf = db.scalar(select(ApprovalWorkflow).where(ApprovalWorkflow.company_id == company_id, ApprovalWorkflow.code == code))
        if not wf:
            wf = ApprovalWorkflow(company_id=company_id, code=code, name=name, module="subcontracts",
                                  description=f"Controlled {name.lower()}", min_amount=Decimal("0"), is_active=True)
            db.add(wf)
            db.flush()
        if not db.scalar(select(func.count()).select_from(ApprovalStep).where(ApprovalStep.workflow_id == wf.id)):
            db.add_all([
                ApprovalStep(workflow_id=wf.id, step_order=1, name="Branch Commercial Review", role_id=branch.id, required_approvals=1, escalation_hours=24),
                ApprovalStep(workflow_id=wf.id, step_order=2, name="Head Office Approval", role_id=hq.id, required_approvals=1, escalation_hours=48),
            ])
    if not db.scalar(select(CompanySetting).where(CompanySetting.company_id == company_id, CompanySetting.key == "subcontract_policy")):
        db.add(CompanySetting(company_id=company_id, key="subcontract_policy", value=dict(POLICY_DEFAULT), description="Phase 9 subcontract governance"))


class SubcontractorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    legal_name: str = Field(min_length=2, max_length=240)
    trading_name: str | None = Field(default=None, max_length=240)
    registration_number: str | None = Field(default=None, max_length=120)
    tax_number: str | None = Field(default=None, max_length=120)
    contact_name: str | None = Field(default=None, max_length=180)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    address: str | None = None
    trade_categories: list[str] = Field(default_factory=list, max_length=50)
    safety_rating: Decimal | None = Field(default=None, ge=0, le=5)
    status: Literal["pending", "active", "suspended", "blacklisted"] = "pending"
    compliance_document_id: int | None = None
    insurance_document_id: int | None = None
    notes: str | None = None


class PackageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch_id: int
    site_id: int | None = None
    project_id: int
    cost_centre_id: int | None = None
    package_code: str = Field(min_length=2, max_length=80)
    title: str = Field(min_length=2, max_length=240)
    description: str | None = None
    trade_category: str | None = Field(default=None, max_length=100)
    planned_start_date: date | None = None
    planned_completion_date: date | None = None
    budget_amount: Decimal = Field(default=0, ge=0)


class PackageLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(min_length=2, max_length=300)
    specification: str | None = None
    quantity: Decimal = Field(default=1, gt=0)
    unit: str = Field(default="item", min_length=1, max_length=40)
    budget_rate: Decimal = Field(default=0, ge=0)
    milestone_id: int | None = None
    notes: str | None = None


class InvitationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subcontractor_id: int
    due_date: date | None = None
    invitation_document_id: int | None = None
    notes: str | None = None


class BidLineInput(BaseModel):
    package_line_id: int
    quantity: Decimal = Field(gt=0)
    unit_rate: Decimal = Field(ge=0)
    notes: str | None = None


class BidInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subcontractor_id: int
    bid_reference: str = Field(min_length=1, max_length=120)
    bid_date: date
    valid_until: date | None = None
    planned_duration_days: int | None = Field(default=None, ge=0, le=3650)
    tax_amount: Decimal = Field(default=0, ge=0)
    document_id: int | None = None
    exclusions: str | None = None
    lines: list[BidLineInput] = Field(min_length=1, max_length=500)


class EvaluationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    technical_score: Decimal = Field(ge=0, le=100)
    commercial_score: Decimal = Field(ge=0, le=100)
    hse_score: Decimal = Field(ge=0, le=100)
    programme_score: Decimal = Field(ge=0, le=100)
    recommendation: Literal["recommended", "reserve", "not_recommended"] = "recommended"
    evaluation_document_id: int | None = None
    notes: str | None = None


class AwardInput(BaseModel):
    bid_id: int
    award_document_id: int | None = None


class ContractInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    package_id: int
    title: str = Field(min_length=2, max_length=240)
    contract_reference: str | None = Field(default=None, max_length=160)
    start_date: date
    completion_date: date
    retention_pct: Decimal | None = Field(default=None, ge=0, le=100)
    retention_cap: Decimal | None = Field(default=None, ge=0)
    advance_amount: Decimal = Field(default=0, ge=0)
    contract_document_id: int | None = None
    notes: str | None = None


class VariationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=2, max_length=240)
    reason: str = Field(min_length=5)
    value: Decimal
    time_extension_days: int = Field(default=0, ge=0, le=3650)
    document_id: int | None = None


class CertificateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    certificate_type: Literal["interim", "final", "retention_release"] = "interim"
    period_start: date
    period_end: date
    gross_value: Decimal = Field(ge=0)
    other_deductions: Decimal = Field(default=0, ge=0)
    evidence_document_id: int | None = None
    notes: str | None = None


class PaymentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payment_reference: str = Field(min_length=2, max_length=120)
    payment_date: date
    amount: Decimal = Field(gt=0)
    payment_document_id: int | None = None
    notes: str | None = None


class PerformanceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_date: date
    quality_score: Decimal = Field(ge=0, le=5)
    programme_score: Decimal = Field(ge=0, le=5)
    safety_score: Decimal = Field(ge=0, le=5)
    commercial_score: Decimal = Field(ge=0, le=5)
    improvement_action: str | None = None
    due_date: date | None = None
    document_id: int | None = None


class PolicyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    minimum_bids: int = Field(default=3, ge=1, le=10)
    low_value_bid_waiver: Decimal = Field(default=5000, ge=0)
    default_retention_pct: Decimal = Field(default=5, ge=0, le=100)
    max_retention_pct: Decimal = Field(default=15, ge=0, le=100)
    certificate_requires_document: bool = True
    performance_alert_score: Decimal = Field(default=2.5, ge=0, le=5)


class ApprovalDecisionInput(BaseModel):
    decision: Literal["approve", "reject"]
    comment: str | None = None


@router.get("/status")
def phase9_status(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    initialized = db.scalar(select(Permission.id).where(Permission.code == "subcontracts.view")) is not None
    if initialized:
        require_anywhere(principal, "subcontracts.view")
    elif not principal.has_company_permission("company.manage"):
        raise HTTPException(status_code=403, detail="Company administration permission required")
    return {"initialized": initialized, "phase": 9, "status": "operational" if initialized else "setup_required"}


@router.post("/bootstrap")
def bootstrap_phase9(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if not principal.has_company_permission("company.manage") and not principal.has_company_permission("subcontracts.manage"):
        raise HTTPException(status_code=403, detail="Company-level administration is required to initialise Phase 9")
    bootstrap_permissions(db, principal.user.company_id)
    audit(db, principal, "subcontracts.phase9.bootstrap", "company", principal.user.company_id, detail={"permissions": len(PERMISSION_ACTIONS)})
    commit(db)
    return {"initialized": True, "phase": 9, "message": "Subcontract Management controls initialised"}


@router.get("/catalog")
def catalog(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_anywhere(principal, "subcontracts.view")
    cid = principal.user.company_id
    branches = [r for r in db.scalars(select(Branch).where(Branch.company_id == cid, Branch.is_active.is_(True)).order_by(Branch.name)).all() if principal.can("subcontracts.view", branch_id=r.id)]
    projects = [r for r in db.scalars(select(Project).where(Project.company_id == cid).order_by(Project.project_number)).all() if principal.can("subcontracts.view", branch_id=r.branch_id, site_id=r.primary_site_id)]
    packages = [r for r in db.scalars(select(SubcontractPackage).where(SubcontractPackage.company_id == cid).order_by(SubcontractPackage.package_number)).all() if principal.can("subcontracts.view", branch_id=r.branch_id, site_id=r.site_id)]
    vendors = db.scalars(select(Subcontractor).where(Subcontractor.company_id == cid).order_by(Subcontractor.legal_name)).all()
    documents = db.scalars(select(Document).where(Document.company_id == cid, Document.status == "active").order_by(Document.id.desc()).limit(500)).all()
    return {
        "branches": [row_dict(r) for r in branches], "projects": [row_dict(r) for r in projects],
        "packages": [row_dict(r) for r in packages], "subcontractors": [row_dict(r) for r in vendors],
        "documents": [{"id": r.id, "title": r.title, "branch_id": r.branch_id, "site_id": r.site_id, "category": r.category} for r in documents if r.branch_id is None or principal.can("subcontracts.view", branch_id=r.branch_id, site_id=r.site_id)],
        "permissions": sorted(code for code in principal.permission_codes if code.startswith("subcontracts.")),
    }


@router.get("/policy/current")
def get_policy(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_anywhere(principal, "subcontracts.view")
    return policy(db, principal.user.company_id)


@router.put("/policy/current")
def update_policy(payload: PolicyInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_company(principal, "subcontracts.manage")
    if payload.default_retention_pct > payload.max_retention_pct:
        raise HTTPException(status_code=422, detail="Default retention cannot exceed the maximum retention policy")
    row = db.scalar(select(CompanySetting).where(CompanySetting.company_id == principal.user.company_id, CompanySetting.key == "subcontract_policy"))
    if not row:
        row = CompanySetting(company_id=principal.user.company_id, key="subcontract_policy", value={}, description="Phase 9 subcontract governance")
        db.add(row)
    row.value = {key: json_value(value) for key, value in payload.model_dump().items()}
    audit(db, principal, "subcontracts.policy.updated", "company_setting", row.id, detail=row.value)
    commit(db)
    return row.value


@router.get("/subcontractors")
def list_subcontractors(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    require_anywhere(principal, "subcontracts.view")
    return [row_dict(row) for row in db.scalars(select(Subcontractor).where(Subcontractor.company_id == principal.user.company_id).order_by(Subcontractor.legal_name)).all()]


@router.post("/subcontractors", status_code=201)
def create_subcontractor(payload: SubcontractorInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_company(principal, "subcontracts.manage")
    ensure_document(db, principal.user.company_id, payload.compliance_document_id)
    ensure_document(db, principal.user.company_id, payload.insurance_document_id)
    values = payload.model_dump()
    row = Subcontractor(
        company_id=principal.user.company_id,
        subcontractor_code=issue_reference(db, principal.user.company_id, "SUBCONTRACTOR", "SUB"),
        created_by=principal.user.full_name,
        approved_by=principal.user.full_name if values["status"] == "active" else None,
        approved_at=utcnow() if values["status"] == "active" else None,
        **values,
    )
    db.add(row)
    db.flush()
    audit(db, principal, "subcontractor.created", "subcontractor", row.id, detail={"code": row.subcontractor_code, "status": row.status})
    commit(db, "Subcontractor code or details conflict with an existing record")
    return row_dict(row)


@router.put("/subcontractors/{subcontractor_id:int}")
def update_subcontractor(subcontractor_id: int, payload: SubcontractorInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_company(principal, "subcontracts.manage")
    row = db.get(Subcontractor, subcontractor_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Subcontractor not found")
    ensure_document(db, row.company_id, payload.compliance_document_id)
    ensure_document(db, row.company_id, payload.insurance_document_id)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    if row.status == "active" and not row.approved_at:
        row.approved_at, row.approved_by = utcnow(), principal.user.full_name
    audit(db, principal, "subcontractor.updated", "subcontractor", row.id, detail={"status": row.status})
    commit(db)
    return row_dict(row)


@router.get("/packages")
def list_packages(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    require_anywhere(principal, "subcontracts.view")
    rows = db.scalars(select(SubcontractPackage).where(SubcontractPackage.company_id == principal.user.company_id).order_by(SubcontractPackage.created_at.desc())).all()
    return [row_dict(row) for row in rows if principal.can("subcontracts.view", branch_id=row.branch_id, site_id=row.site_id)]


@router.post("/packages", status_code=201)
def create_package(payload: PackageInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    project = ensure_scope(db, principal.user.company_id, payload.branch_id, payload.site_id, payload.project_id, payload.cost_centre_id)
    require_scope(principal, "subcontracts.manage", payload.branch_id, payload.site_id)
    if project.status not in {"ready", "operational", "active"}:
        raise HTTPException(status_code=409, detail="Only a mobilised or operational project may receive a subcontract package")
    if payload.planned_start_date and payload.planned_completion_date and payload.planned_completion_date < payload.planned_start_date:
        raise HTTPException(status_code=422, detail="Package completion date cannot precede the start date")
    row = SubcontractPackage(
        company_id=principal.user.company_id,
        package_number=issue_reference(db, principal.user.company_id, "SUBCONTRACT_PACKAGE", "SCP"),
        created_by=principal.user.full_name,
        budget_amount=money(payload.budget_amount),
        **payload.model_dump(exclude={"budget_amount"}),
    )
    db.add(row)
    db.flush()
    audit(db, principal, "subcontract.package.created", "subcontract_package", row.id, branch_id=row.branch_id, site_id=row.site_id, detail={"number": row.package_number})
    commit(db, "A package with this code already exists for the project")
    return row_dict(row)


@router.get("/packages/{package_id:int}")
def package_detail(package_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    package = package_or_404(db, principal, package_id)
    lines = db.scalars(select(SubcontractPackageLine).where(SubcontractPackageLine.package_id == package.id).order_by(SubcontractPackageLine.line_number)).all()
    invitations = db.scalars(select(SubcontractInvitation).where(SubcontractInvitation.package_id == package.id).order_by(SubcontractInvitation.id)).all()
    bids = db.scalars(select(SubcontractBid).where(SubcontractBid.package_id == package.id).order_by(SubcontractBid.total_amount)).all()
    evaluations = db.scalars(select(SubcontractEvaluation).where(SubcontractEvaluation.package_id == package.id).order_by(SubcontractEvaluation.total_score.desc())).all()
    return {"package": row_dict(package), "lines": [row_dict(row) for row in lines], "invitations": [row_dict(row) for row in invitations], "bids": [row_dict(row) for row in bids], "evaluations": [row_dict(row) for row in evaluations]}


@router.post("/packages/{package_id:int}/lines", status_code=201)
def add_package_line(package_id: int, payload: PackageLineInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    package = package_or_404(db, principal, package_id, "subcontracts.manage")
    if package.status not in {"draft", "rejected"}:
        raise HTTPException(status_code=409, detail="Only draft/rejected packages can be changed")
    if payload.milestone_id:
        milestone = db.get(__import__("app.models", fromlist=["ProjectMilestone"]).ProjectMilestone, payload.milestone_id)
        if not milestone or milestone.project_id != package.project_id:
            raise HTTPException(status_code=422, detail="Package milestone does not belong to the project")
    line_number = (db.scalar(select(func.coalesce(func.max(SubcontractPackageLine.line_number), 0)).where(SubcontractPackageLine.package_id == package.id)) or 0) + 1
    row = SubcontractPackageLine(company_id=package.company_id, package_id=package.id, line_number=line_number, budget_rate=Decimal(str(payload.budget_rate)).quantize(Decimal("0.0001")), budget_amount=money(payload.quantity * payload.budget_rate), **payload.model_dump(exclude={"budget_rate"}))
    db.add(row)
    db.flush()
    package.budget_amount = money(db.scalar(select(func.coalesce(func.sum(SubcontractPackageLine.budget_amount), 0)).where(SubcontractPackageLine.package_id == package.id)) or 0)
    audit(db, principal, "subcontract.package.line.added", "subcontract_package_line", row.id, branch_id=package.branch_id, site_id=package.site_id, detail={"amount": str(row.budget_amount)})
    commit(db)
    return row_dict(row)


@router.post("/packages/{package_id:int}/invite", status_code=201)
def invite_subcontractor(package_id: int, payload: InvitationInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    package = package_or_404(db, principal, package_id, "subcontracts.manage")
    if package.status not in {"draft", "tendering", "rejected"}:
        raise HTTPException(status_code=409, detail="Package is not available for subcontractor invitations")
    vendor = db.get(Subcontractor, payload.subcontractor_id)
    if not vendor or vendor.company_id != package.company_id or vendor.status != "active":
        raise HTTPException(status_code=422, detail="Only an active approved subcontractor may be invited")
    ensure_document(db, package.company_id, payload.invitation_document_id)
    row = SubcontractInvitation(company_id=package.company_id, package_id=package.id, subcontractor_id=vendor.id, invitation_number=issue_reference(db, package.company_id, "SUBCONTRACT_INVITATION", "SCI"), due_date=payload.due_date, invitation_document_id=payload.invitation_document_id, invited_by=principal.user.full_name, notes=payload.notes)
    db.add(row)
    package.status = "tendering"
    audit(db, principal, "subcontract.invitation.created", "subcontract_invitation", None, branch_id=package.branch_id, site_id=package.site_id, detail={"package": package.package_number, "subcontractor": vendor.subcontractor_code})
    commit(db, "This subcontractor is already invited to the package")
    return row_dict(row)


@router.post("/packages/{package_id:int}/bids", status_code=201)
def record_bid(package_id: int, payload: BidInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    package = package_or_404(db, principal, package_id, "subcontracts.manage")
    if package.status not in {"tendering", "evaluation", "rejected"}:
        raise HTTPException(status_code=409, detail="Package is not open for bid recording")
    vendor = db.get(Subcontractor, payload.subcontractor_id)
    if not vendor or vendor.company_id != package.company_id or vendor.status != "active":
        raise HTTPException(status_code=422, detail="Bid subcontractor is not active")
    if payload.valid_until and payload.valid_until < payload.bid_date:
        raise HTTPException(status_code=422, detail="Bid validity cannot precede the bid date")
    ensure_document(db, package.company_id, payload.document_id)
    package_lines = {line.id: line for line in db.scalars(select(SubcontractPackageLine).where(SubcontractPackageLine.package_id == package.id)).all()}
    if not package_lines:
        raise HTTPException(status_code=409, detail="A package needs scope lines before bids can be recorded")
    incoming_ids = [line.package_line_id for line in payload.lines]
    if len(set(incoming_ids)) != len(incoming_ids) or set(incoming_ids) != set(package_lines):
        raise HTTPException(status_code=422, detail="A bid must price every package scope line exactly once")
    row = SubcontractBid(company_id=package.company_id, package_id=package.id, subcontractor_id=vendor.id, bid_number=issue_reference(db, package.company_id, "SUBCONTRACT_BID", "SCB"), bid_reference=payload.bid_reference, bid_date=payload.bid_date, valid_until=payload.valid_until, planned_duration_days=payload.planned_duration_days, tax_amount=money(payload.tax_amount), document_id=payload.document_id, exclusions=payload.exclusions, submitted_by=principal.user.full_name)
    db.add(row)
    db.flush()
    subtotal = Decimal("0")
    for line in payload.lines:
        scope = package_lines[line.package_line_id]
        amount = money(line.quantity * line.unit_rate)
        subtotal += amount
        db.add(SubcontractBidLine(company_id=package.company_id, bid_id=row.id, package_line_id=scope.id, quantity=line.quantity, unit_rate=Decimal(str(line.unit_rate)).quantize(Decimal("0.0001")), line_total=amount, notes=line.notes))
    row.subtotal, row.total_amount = money(subtotal), money(subtotal + row.tax_amount)
    package.status = "evaluation"
    audit(db, principal, "subcontract.bid.recorded", "subcontract_bid", row.id, branch_id=package.branch_id, site_id=package.site_id, detail={"number": row.bid_number, "total": str(row.total_amount)})
    commit(db, "Bid reference already exists for this subcontractor and package")
    return row_dict(row)


@router.post("/bids/{bid_id:int}/evaluation", status_code=201)
def evaluate_bid(bid_id: int, payload: EvaluationInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    bid = db.get(SubcontractBid, bid_id)
    if not bid or bid.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Subcontract bid not found")
    package = package_or_404(db, principal, bid.package_id, "subcontracts.manage")
    if package.status not in {"evaluation", "rejected"}:
        raise HTTPException(status_code=409, detail="Package is not available for evaluation")
    ensure_document(db, package.company_id, payload.evaluation_document_id)
    total = (payload.technical_score + payload.commercial_score + payload.hse_score + payload.programme_score) / Decimal("4")
    row = SubcontractEvaluation(company_id=package.company_id, package_id=package.id, bid_id=bid.id, technical_score=payload.technical_score, commercial_score=payload.commercial_score, hse_score=payload.hse_score, programme_score=payload.programme_score, total_score=total.quantize(Decimal("0.01")), recommendation=payload.recommendation, evaluation_document_id=payload.evaluation_document_id, notes=payload.notes, evaluated_by=principal.user.full_name)
    db.add(row)
    audit(db, principal, "subcontract.bid.evaluated", "subcontract_evaluation", None, branch_id=package.branch_id, site_id=package.site_id, detail={"bid": bid.bid_number, "score": str(row.total_score)})
    commit(db, "This bid already has an evaluation")
    return row_dict(row)


@router.post("/packages/{package_id:int}/award")
def submit_award(package_id: int, payload: AwardInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    package = package_or_404(db, principal, package_id, "subcontracts.manage")
    if package.status not in {"evaluation", "rejected"}:
        raise HTTPException(status_code=409, detail="Package is not ready for award")
    bid = db.get(SubcontractBid, payload.bid_id)
    if not bid or bid.package_id != package.id:
        raise HTTPException(status_code=422, detail="Selected bid does not belong to this package")
    evaluation = db.scalar(select(SubcontractEvaluation).where(SubcontractEvaluation.package_id == package.id, SubcontractEvaluation.bid_id == bid.id))
    if not evaluation or evaluation.recommendation != "recommended":
        raise HTTPException(status_code=409, detail="Only a positively evaluated bid may be submitted for award")
    if bid.valid_until and bid.valid_until < date.today():
        raise HTTPException(status_code=409, detail="An expired bid cannot be awarded")
    ensure_document(db, package.company_id, payload.award_document_id)
    request = create_approval(db, principal, code="SUBCONTRACT_AWARD", entity_type="subcontract_award", entity_id=package.id, title=f"Subcontract award {package.package_number}: {package.title}", package=package, amount=bid.total_amount)
    package.selected_bid_id, package.award_document_id, package.award_approval_request_id, package.status = bid.id, payload.award_document_id, request.id, "award_submitted"
    audit(db, principal, "subcontract.award.submitted", "subcontract_package", package.id, branch_id=package.branch_id, site_id=package.site_id, detail={"bid": bid.bid_number, "approval_request_id": request.id})
    commit(db)
    return row_dict(request)


@router.get("/contracts")
def list_contracts(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    require_anywhere(principal, "subcontracts.view")
    rows = db.scalars(select(SubcontractContract).where(SubcontractContract.company_id == principal.user.company_id).order_by(SubcontractContract.created_at.desc())).all()
    return [row_dict(row) for row in rows if principal.can("subcontracts.view", branch_id=row.branch_id, site_id=row.site_id)]


@router.post("/contracts", status_code=201)
def create_contract(payload: ContractInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    package = package_or_404(db, principal, payload.package_id, "subcontracts.manage")
    if package.status != "awarded" or not package.selected_bid_id:
        raise HTTPException(status_code=409, detail="Only an approved awarded package can become a subcontract contract")
    if payload.completion_date < payload.start_date:
        raise HTTPException(status_code=422, detail="Contract completion date cannot precede the start date")
    bid = db.get(SubcontractBid, package.selected_bid_id)
    if not bid:
        raise HTTPException(status_code=409, detail="Awarded bid is unavailable")
    cfg = policy(db, package.company_id)
    retention = payload.retention_pct if payload.retention_pct is not None else Decimal(str(cfg["default_retention_pct"]))
    if retention > Decimal(str(cfg["max_retention_pct"])):
        raise HTTPException(status_code=422, detail="Contract retention exceeds the company policy maximum")
    ensure_document(db, package.company_id, payload.contract_document_id)
    row = SubcontractContract(company_id=package.company_id, branch_id=package.branch_id, site_id=package.site_id, project_id=package.project_id, package_id=package.id, subcontractor_id=bid.subcontractor_id, selected_bid_id=bid.id, cost_centre_id=package.cost_centre_id, contract_number=issue_reference(db, package.company_id, "SUBCONTRACT_CONTRACT", "SCT"), title=payload.title, contract_reference=payload.contract_reference, start_date=payload.start_date, completion_date=payload.completion_date, original_contract_sum=money(bid.total_amount), retention_pct=retention, retention_cap=money(payload.retention_cap) if payload.retention_cap is not None else None, advance_amount=money(payload.advance_amount), contract_document_id=payload.contract_document_id, notes=payload.notes, created_by=principal.user.full_name)
    db.add(row)
    db.flush()
    audit(db, principal, "subcontract.contract.created", "subcontract_contract", row.id, branch_id=row.branch_id, site_id=row.site_id, detail={"number": row.contract_number, "amount": str(row.original_contract_sum)})
    commit(db, "A contract already exists for this subcontract package")
    return row_dict(row)


@router.get("/contracts/{contract_id:int}")
def contract_detail(contract_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    contract = contract_or_404(db, principal, contract_id)
    variations = db.scalars(select(SubcontractVariation).where(SubcontractVariation.contract_id == contract.id).order_by(SubcontractVariation.id)).all()
    certificates = db.scalars(select(SubcontractCertificate).where(SubcontractCertificate.contract_id == contract.id).order_by(SubcontractCertificate.period_end.desc(), SubcontractCertificate.id.desc())).all()
    payments = db.scalars(select(SubcontractPayment).join(SubcontractCertificate).where(SubcontractCertificate.contract_id == contract.id).order_by(SubcontractPayment.payment_date.desc())).all()
    reviews = db.scalars(select(SubcontractPerformanceReview).where(SubcontractPerformanceReview.contract_id == contract.id).order_by(SubcontractPerformanceReview.review_date.desc())).all()
    return {"contract": {**row_dict(contract), "current_contract_sum": str(contract_ceiling(db, contract))}, "variations": [row_dict(row) for row in variations], "certificates": [row_dict(row) for row in certificates], "payments": [row_dict(row) for row in payments], "performance_reviews": [row_dict(row) for row in reviews]}


@router.post("/contracts/{contract_id:int}/submit")
def submit_contract(contract_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    contract = contract_or_404(db, principal, contract_id, "subcontracts.manage")
    if contract.status not in {"draft", "rejected"}:
        raise HTTPException(status_code=409, detail="Only draft/rejected contracts can be submitted")
    if not contract.contract_document_id:
        raise HTTPException(status_code=409, detail="A controlled contract document is required before approval")
    package = db.get(SubcontractPackage, contract.package_id)
    request = create_approval(db, principal, code="SUBCONTRACT_CONTRACT", entity_type="subcontract_contract", entity_id=contract.id, title=f"Subcontract contract {contract.contract_number}: {contract.title}", package=package, amount=contract.original_contract_sum)
    contract.approval_request_id, contract.status = request.id, "submitted"
    audit(db, principal, "subcontract.contract.submitted", "subcontract_contract", contract.id, branch_id=contract.branch_id, site_id=contract.site_id, detail={"approval_request_id": request.id})
    commit(db)
    return row_dict(request)


@router.post("/contracts/{contract_id:int}/variations", status_code=201)
def create_variation(contract_id: int, payload: VariationInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    contract = contract_or_404(db, principal, contract_id, "subcontracts.manage")
    if contract.status not in {"active", "completed"}:
        raise HTTPException(status_code=409, detail="Only an active/completed contract may receive a variation")
    ensure_document(db, contract.company_id, payload.document_id)
    row = SubcontractVariation(company_id=contract.company_id, contract_id=contract.id, variation_number=issue_reference(db, contract.company_id, "SUBCONTRACT_VARIATION", "SCV"), title=payload.title, reason=payload.reason, value=money(payload.value), time_extension_days=payload.time_extension_days, document_id=payload.document_id, created_by=principal.user.full_name)
    db.add(row)
    db.flush()
    audit(db, principal, "subcontract.variation.created", "subcontract_variation", row.id, branch_id=contract.branch_id, site_id=contract.site_id, detail={"value": str(row.value)})
    commit(db)
    return row_dict(row)


@router.post("/variations/{variation_id:int}/submit")
def submit_variation(variation_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    variation = db.get(SubcontractVariation, variation_id)
    if not variation or variation.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Subcontract variation not found")
    contract = contract_or_404(db, principal, variation.contract_id, "subcontracts.manage")
    if variation.status not in {"draft", "rejected"}:
        raise HTTPException(status_code=409, detail="Only draft/rejected variations can be submitted")
    package = db.get(SubcontractPackage, contract.package_id)
    request = create_approval(db, principal, code="SUBCONTRACT_VARIATION", entity_type="subcontract_variation", entity_id=variation.id, title=f"Subcontract variation {variation.variation_number}: {variation.title}", package=package, amount=variation.value)
    variation.approval_request_id, variation.status = request.id, "submitted"
    audit(db, principal, "subcontract.variation.submitted", "subcontract_variation", variation.id, branch_id=contract.branch_id, site_id=contract.site_id, detail={"approval_request_id": request.id})
    commit(db)
    return row_dict(request)


@router.post("/contracts/{contract_id:int}/certificates", status_code=201)
def create_certificate(contract_id: int, payload: CertificateInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    contract = contract_or_404(db, principal, contract_id, "subcontracts.certify")
    if contract.status != "active":
        raise HTTPException(status_code=409, detail="Only an active contract may be certified")
    if payload.period_end < payload.period_start:
        raise HTTPException(status_code=422, detail="Certificate period end cannot precede the start")
    cfg = policy(db, contract.company_id)
    if cfg["certificate_requires_document"] and not payload.evidence_document_id:
        raise HTTPException(status_code=409, detail="A controlled measurement/certificate evidence document is required")
    ensure_document(db, contract.company_id, payload.evidence_document_id)
    previous = money(contract.certified_amount)
    gross = money(payload.gross_value)
    cumulative = money(previous + gross)
    ceiling = contract_ceiling(db, contract)
    if cumulative > ceiling:
        raise HTTPException(status_code=409, detail=f"Certificate exceeds the approved contract ceiling of {ceiling}")
    retention = money(gross * Decimal(contract.retention_pct) / Decimal("100"))
    if contract.retention_cap is not None:
        retention = max(Decimal("0"), min(retention, money(Decimal(contract.retention_cap) - Decimal(contract.retention_held))))
    net = money(gross - retention - money(payload.other_deductions))
    if net < 0:
        raise HTTPException(status_code=422, detail="Certificate deductions cannot exceed the certified gross value")
    row = SubcontractCertificate(company_id=contract.company_id, contract_id=contract.id, certificate_number=issue_reference(db, contract.company_id, "SUBCONTRACT_CERTIFICATE", "SCC"), certificate_type=payload.certificate_type, period_start=payload.period_start, period_end=payload.period_end, gross_value=gross, previous_certified=previous, cumulative_certified=cumulative, retention_deduction=retention, other_deductions=money(payload.other_deductions), net_payable=net, evidence_document_id=payload.evidence_document_id, notes=payload.notes, prepared_by=principal.user.full_name)
    db.add(row)
    db.flush()
    audit(db, principal, "subcontract.certificate.created", "subcontract_certificate", row.id, branch_id=contract.branch_id, site_id=contract.site_id, detail={"number": row.certificate_number, "net_payable": str(row.net_payable)})
    commit(db)
    return row_dict(row)


@router.post("/certificates/{certificate_id:int}/submit")
def submit_certificate(certificate_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    certificate = db.get(SubcontractCertificate, certificate_id)
    if not certificate or certificate.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Subcontract certificate not found")
    contract = contract_or_404(db, principal, certificate.contract_id, "subcontracts.certify")
    if certificate.status not in {"draft", "rejected"}:
        raise HTTPException(status_code=409, detail="Only draft/rejected certificates can be submitted")
    package = db.get(SubcontractPackage, contract.package_id)
    request = create_approval(db, principal, code="SUBCONTRACT_CERTIFICATE", entity_type="subcontract_certificate", entity_id=certificate.id, title=f"Subcontract certificate {certificate.certificate_number}", package=package, amount=certificate.net_payable)
    certificate.approval_request_id, certificate.status = request.id, "submitted"
    audit(db, principal, "subcontract.certificate.submitted", "subcontract_certificate", certificate.id, branch_id=contract.branch_id, site_id=contract.site_id, detail={"approval_request_id": request.id})
    commit(db)
    return row_dict(request)


@router.post("/certificates/{certificate_id:int}/payments", status_code=201)
def record_payment(certificate_id: int, payload: PaymentInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    certificate = db.get(SubcontractCertificate, certificate_id)
    if not certificate or certificate.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Subcontract certificate not found")
    contract = contract_or_404(db, principal, certificate.contract_id, "subcontracts.pay")
    if certificate.status not in {"approved", "part_paid"}:
        raise HTTPException(status_code=409, detail="Only an approved certificate can have payment evidence")
    ensure_document(db, certificate.company_id, payload.payment_document_id)
    amount = money(payload.amount)
    outstanding = money(Decimal(certificate.net_payable) - payment_total(db, certificate.id))
    if amount > outstanding:
        raise HTTPException(status_code=409, detail=f"Payment exceeds the remaining approved certificate amount of {outstanding}")
    row = SubcontractPayment(company_id=certificate.company_id, certificate_id=certificate.id, payment_reference=payload.payment_reference, payment_date=payload.payment_date, amount=amount, payment_document_id=payload.payment_document_id, notes=payload.notes, recorded_by=principal.user.full_name)
    db.add(row)
    db.flush()
    paid = payment_total(db, certificate.id)
    certificate.status = "paid" if paid >= Decimal(certificate.net_payable) else "part_paid"
    contract.paid_amount = money(Decimal(contract.paid_amount) + amount)
    audit(db, principal, "subcontract.payment.recorded", "subcontract_payment", row.id, branch_id=contract.branch_id, site_id=contract.site_id, detail={"certificate": certificate.certificate_number, "amount": str(amount)})
    commit(db, "Payment reference already exists")
    return row_dict(row)


@router.post("/contracts/{contract_id:int}/performance-reviews", status_code=201)
def create_performance_review(contract_id: int, payload: PerformanceInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    contract = contract_or_404(db, principal, contract_id, "subcontracts.certify")
    if contract.status not in {"active", "completed"}:
        raise HTTPException(status_code=409, detail="Performance can only be recorded for an active/completed contract")
    ensure_document(db, contract.company_id, payload.document_id)
    score = ((payload.quality_score + payload.programme_score + payload.safety_score + payload.commercial_score) / Decimal("4")).quantize(Decimal("0.01"))
    row = SubcontractPerformanceReview(company_id=contract.company_id, contract_id=contract.id, review_date=payload.review_date, quality_score=payload.quality_score, programme_score=payload.programme_score, safety_score=payload.safety_score, commercial_score=payload.commercial_score, overall_score=score, improvement_action=payload.improvement_action, due_date=payload.due_date, document_id=payload.document_id, reviewed_by=principal.user.full_name)
    db.add(row)
    vendor = db.get(Subcontractor, contract.subcontractor_id)
    if vendor:
        vendor.performance_rating = score
    audit(db, principal, "subcontract.performance.reviewed", "subcontract_performance_review", None, branch_id=contract.branch_id, site_id=contract.site_id, detail={"overall_score": str(score)})
    commit(db, "A performance review already exists for this contract and date")
    return row_dict(row)


@router.post("/approvals/{request_id:int}/decision")
def decide_approval(request_id: int, payload: ApprovalDecisionInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    request = db.get(ApprovalRequest, request_id)
    entity_map = {
        "subcontract_award": (SubcontractPackage, "award_submitted"),
        "subcontract_contract": (SubcontractContract, "submitted"),
        "subcontract_variation": (SubcontractVariation, "submitted"),
        "subcontract_certificate": (SubcontractCertificate, "submitted"),
    }
    if not request or request.company_id != principal.user.company_id or request.entity_type not in entity_map:
        raise HTTPException(status_code=404, detail="Subcontract approval request not found")
    model, expected_status = entity_map[request.entity_type]
    entity = db.get(model, int(request.entity_id))
    if not entity:
        raise HTTPException(status_code=404, detail="Subcontract approval entity not found")
    contract = entity if isinstance(entity, SubcontractContract) else (db.get(SubcontractContract, entity.contract_id) if hasattr(entity, "contract_id") else None)
    package = entity if isinstance(entity, SubcontractPackage) else (db.get(SubcontractPackage, contract.package_id) if contract else None)
    if not package:
        raise HTTPException(status_code=409, detail="Subcontract approval scope is unavailable")
    require_scope(principal, "subcontracts.approve", package.branch_id, package.site_id)
    if request.status != "pending" or entity.status != expected_status:
        raise HTTPException(status_code=409, detail="Approval request is not pending")
    step = db.scalar(select(ApprovalStep).where(ApprovalStep.workflow_id == request.workflow_id, ApprovalStep.step_order == request.current_step_order))
    if not step or not assignment_authorised(db, principal, step.role_id, package.branch_id, package.site_id):
        raise HTTPException(status_code=403, detail="Your active role assignment is not authorised for this approval step")
    if request.requested_by == principal.user.full_name and not allow_self_approval(db, principal.user.company_id):
        raise HTTPException(status_code=422, detail="Self-approval is disabled by company approval policy")
    db.add(ApprovalAction(request_id=request.id, step_order=step.step_order, role_id=step.role_id, actor_name=principal.user.full_name, action=payload.decision, comment=payload.comment))
    if payload.decision == "reject":
        request.status, request.completed_at, entity.status = "rejected", utcnow(), "rejected"
    else:
        count = (db.scalar(select(func.count()).select_from(ApprovalAction).where(ApprovalAction.request_id == request.id, ApprovalAction.step_order == step.step_order, ApprovalAction.action == "approve")) or 0) + 1
        if count >= step.required_approvals:
            next_step = db.scalar(select(ApprovalStep).where(ApprovalStep.workflow_id == request.workflow_id, ApprovalStep.step_order > step.step_order).order_by(ApprovalStep.step_order).limit(1))
            if next_step:
                request.current_step_order = next_step.step_order
            else:
                request.status, request.completed_at = "approved", utcnow()
                if isinstance(entity, SubcontractPackage):
                    entity.status = "awarded"
                elif isinstance(entity, SubcontractContract):
                    entity.status, entity.approved_at = "active", utcnow()
                    db.get(SubcontractPackage, entity.package_id).status = "contracted"
                elif isinstance(entity, SubcontractVariation):
                    entity.status, entity.approved_at = "approved", utcnow()
                elif isinstance(entity, SubcontractCertificate):
                    entity.status, entity.approved_at = "approved", utcnow()
                    c = db.get(SubcontractContract, entity.contract_id)
                    c.certified_amount = money(Decimal(c.certified_amount) + Decimal(entity.gross_value))
                    c.retention_held = money(Decimal(c.retention_held) + Decimal(entity.retention_deduction))
                    entity.approved_snapshot = {"certificate": row_dict(entity), "contract_number": c.contract_number, "approved_at": entity.approved_at.isoformat()}
    audit(db, principal, f"subcontract.approval.{payload.decision}", "approval_request", request.id, branch_id=package.branch_id, site_id=package.site_id, detail={"entity_type": request.entity_type, "status": request.status, "step": step.step_order})
    commit(db)
    return row_dict(request)


@router.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_anywhere(principal, "subcontracts.view")
    cid = principal.user.company_id
    packages = [row for row in db.scalars(select(SubcontractPackage).where(SubcontractPackage.company_id == cid)).all() if principal.can("subcontracts.view", branch_id=row.branch_id, site_id=row.site_id)]
    contracts = [row for row in db.scalars(select(SubcontractContract).where(SubcontractContract.company_id == cid)).all() if principal.can("subcontracts.view", branch_id=row.branch_id, site_id=row.site_id)]
    certificates = [row for row in db.scalars(select(SubcontractCertificate).where(SubcontractCertificate.company_id == cid)).all() if principal.can("subcontracts.view", branch_id=db.get(SubcontractContract, row.contract_id).branch_id, site_id=db.get(SubcontractContract, row.contract_id).site_id)]
    commitment = sum((Decimal(row.original_contract_sum) for row in contracts if row.status in {"submitted", "active", "completed"}), Decimal("0"))
    certified = sum((Decimal(row.gross_value) for row in certificates if row.status in {"approved", "part_paid", "paid"}), Decimal("0"))
    payable = sum((Decimal(row.net_payable) - payment_total(db, row.id) for row in certificates if row.status in {"approved", "part_paid"}), Decimal("0"))
    return {"packages": len(packages), "packages_pending_award": sum(row.status == "award_submitted" for row in packages), "contracts": len(contracts), "contracts_pending": sum(row.status == "submitted" for row in contracts), "commitments": str(money(commitment)), "certified": str(money(certified)), "payable": str(money(payable))}


@router.get("/dashboard/alerts")
def dashboard_alerts(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    require_anywhere(principal, "subcontracts.view")
    cid, today, result = principal.user.company_id, date.today(), []
    for invite in db.scalars(select(SubcontractInvitation).where(SubcontractInvitation.company_id == cid, SubcontractInvitation.status == "invited", SubcontractInvitation.due_date.is_not(None))).all():
        package = db.get(SubcontractPackage, invite.package_id)
        if package and invite.due_date <= today and principal.can("subcontracts.view", branch_id=package.branch_id, site_id=package.site_id):
            result.append({"type": "bid_due", "severity": "critical" if invite.due_date < today else "warning", "reference": invite.invitation_number, "message": f"Bid due {invite.due_date.isoformat()}"})
    for contract in db.scalars(select(SubcontractContract).where(SubcontractContract.company_id == cid, SubcontractContract.status == "active")).all():
        if contract.completion_date < today and principal.can("subcontracts.view", branch_id=contract.branch_id, site_id=contract.site_id):
            result.append({"type": "contract_overdue", "severity": "critical", "reference": contract.contract_number, "message": f"Completion date {contract.completion_date.isoformat()} has passed"})
    threshold = Decimal(str(policy(db, cid)["performance_alert_score"]))
    for review in db.scalars(select(SubcontractPerformanceReview).where(SubcontractPerformanceReview.company_id == cid, SubcontractPerformanceReview.overall_score < threshold, SubcontractPerformanceReview.status == "open")).all():
        contract = db.get(SubcontractContract, review.contract_id)
        if contract and principal.can("subcontracts.view", branch_id=contract.branch_id, site_id=contract.site_id):
            result.append({"type": "performance", "severity": "warning", "reference": contract.contract_number, "message": f"Performance score {review.overall_score} requires follow-up"})
    return result


@router.get("/exports/contracts.csv")
def export_contracts(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> StreamingResponse:
    require_anywhere(principal, "subcontracts.export")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Contract", "Package", "Project ID", "Subcontractor", "Branch ID", "Site ID", "Original Sum", "Current Sum", "Certified", "Paid", "Retention Held", "Status", "Completion"])
    for row in db.scalars(select(SubcontractContract).where(SubcontractContract.company_id == principal.user.company_id).order_by(SubcontractContract.contract_number)).all():
        if not principal.can("subcontracts.export", branch_id=row.branch_id, site_id=row.site_id):
            continue
        vendor, package = db.get(Subcontractor, row.subcontractor_id), db.get(SubcontractPackage, row.package_id)
        writer.writerow([row.contract_number, package.package_number if package else "", row.project_id, vendor.legal_name if vendor else "", row.branch_id, row.site_id or "", row.original_contract_sum, contract_ceiling(db, row), row.certified_amount, row.paid_amount, row.retention_held, row.status, row.completion_date])
    return StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=buildtrack-subcontract-contracts.csv"})


@router.get("/exports/certificates.csv")
def export_certificates(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> StreamingResponse:
    require_anywhere(principal, "subcontracts.export")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Certificate", "Contract", "Period Start", "Period End", "Gross", "Retention", "Other Deductions", "Net Payable", "Paid", "Status"])
    for row in db.scalars(select(SubcontractCertificate).where(SubcontractCertificate.company_id == principal.user.company_id).order_by(SubcontractCertificate.period_end.desc())).all():
        contract = db.get(SubcontractContract, row.contract_id)
        if contract and principal.can("subcontracts.export", branch_id=contract.branch_id, site_id=contract.site_id):
            writer.writerow([row.certificate_number, contract.contract_number, row.period_start, row.period_end, row.gross_value, row.retention_deduction, row.other_deductions, row.net_payable, payment_total(db, row.id), row.status])
    return StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=buildtrack-subcontract-certificates.csv"})


@router.get("/audit/events")
def audit_events(db: Session = Depends(get_db), principal: Principal = Depends(current_principal), limit: int = Query(default=250, ge=1, le=1000)) -> list[dict[str, Any]]:
    require_anywhere(principal, "subcontracts.view")
    rows = db.scalars(select(SubcontractAuditEvent).where(SubcontractAuditEvent.company_id == principal.user.company_id).order_by(SubcontractAuditEvent.occurred_at.desc()).limit(limit)).all()
    return [row_dict(row) for row in rows if row.branch_id is None or principal.can("subcontracts.view", branch_id=row.branch_id, site_id=row.site_id)]
