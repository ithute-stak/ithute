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
    allow_self_approval, assignment_authorised, commit, ensure_document, issue_reference,
    money, row_dict, utcnow,
)
from app.db.session import get_db
from app.models import (
    ApprovalAction, ApprovalRequest, ApprovalStep, ApprovalWorkflow, ClientClaim,
    ClientContract, ClientInvoice, ClientReceipt, ClientValuation, ClientVariation,
    CommercialAuditEvent, CompanySetting, CostCentre, NumberSequence, Permission,
    Project, ProjectBudgetBaseline, ProjectCashFlowForecast, ProjectCostTransaction,
    PurchaseOrder, Role, RolePermission, SubcontractContract, SubcontractVariation,
)
from app.security.access import Principal, current_principal


router = APIRouter(prefix="/commercial", tags=["Phase 11 - Cost and Commercial Control"])

PERMISSIONS = {
    "commercial.view": ("commercial", "view", "View project commercial controls and reports"),
    "commercial.manage": ("commercial", "manage", "Manage client contracts, costs, cash flow and claims"),
    "commercial.approve": ("commercial", "approve", "Approve client commercial submissions"),
    "commercial.receive": ("commercial", "receive", "Record supplied client-payment evidence"),
    "commercial.export": ("commercial", "export", "Export controlled commercial reports"),
}
POLICY_DEFAULT = {
    "default_retention_pct": 5,
    "max_retention_pct": 15,
    "cost_variance_warning_pct": 10,
    "invoice_due_warning_days": 7,
    "evidence_required_for_submission": True,
}


def require_anywhere(principal: Principal, permission: str) -> None:
    if not principal.has_permission_anywhere(permission):
        raise HTTPException(status_code=403, detail=f"Permission required: {permission}")


def require_scope(principal: Principal, permission: str, branch_id: int, site_id: int | None) -> None:
    if not principal.can(permission, branch_id=branch_id, site_id=site_id):
        raise HTTPException(status_code=403, detail=f"Permission required in this branch/site: {permission}")


def policy(db: Session, company_id: int) -> dict[str, Any]:
    row = db.scalar(select(CompanySetting).where(CompanySetting.company_id == company_id, CompanySetting.key == "commercial_policy"))
    return {**POLICY_DEFAULT, **(row.value if row and isinstance(row.value, dict) else {})}


def audit(db: Session, principal: Principal, action: str, entity_type: str, entity_id: int | str | None, *, project: Project, detail: dict[str, Any] | None = None) -> None:
    db.add(CommercialAuditEvent(
        company_id=principal.user.company_id, branch_id=project.branch_id, site_id=project.primary_site_id,
        project_id=project.id, actor=principal.user.full_name, action=action, entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None, detail=detail or {},
    ))


def project_or_404(db: Session, principal: Principal, project_id: int, permission: str = "commercial.view") -> Project:
    row = db.get(Project, project_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Project not found")
    require_scope(principal, permission, row.branch_id, row.primary_site_id)
    return row


def contract_or_404(db: Session, principal: Principal, contract_id: int, permission: str = "commercial.view") -> ClientContract:
    row = db.get(ClientContract, contract_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Client contract not found")
    require_scope(principal, permission, row.branch_id, row.site_id)
    return row


def entity_project(db: Session, entity: Any) -> Project:
    if isinstance(entity, ClientClaim):
        project = db.get(Project, entity.project_id)
    elif isinstance(entity, ProjectCostTransaction):
        project = db.get(Project, entity.project_id)
    else:
        contract_id = entity.id if isinstance(entity, ClientContract) else entity.contract_id
        contract = db.get(ClientContract, contract_id)
        project = db.get(Project, contract.project_id) if contract else None
    if not project:
        raise HTTPException(status_code=409, detail="Commercial project scope is unavailable")
    return project


def commercial_workflow(db: Session, company_id: int, code: str) -> ApprovalWorkflow:
    row = db.scalar(select(ApprovalWorkflow).where(ApprovalWorkflow.company_id == company_id, ApprovalWorkflow.code == code, ApprovalWorkflow.is_active.is_(True)))
    if not row or not db.scalar(select(func.count()).select_from(ApprovalStep).where(ApprovalStep.workflow_id == row.id)):
        raise HTTPException(status_code=409, detail=f"Commercial approval workflow {code} is not configured")
    return row


def make_approval(db: Session, principal: Principal, *, code: str, entity_type: str, entity_id: int, title: str, project: Project, amount: Decimal) -> ApprovalRequest:
    workflow = commercial_workflow(db, principal.user.company_id, code)
    row = ApprovalRequest(
        company_id=principal.user.company_id, workflow_id=workflow.id, branch_id=project.branch_id,
        site_id=project.primary_site_id, entity_type=entity_type, entity_id=str(entity_id),
        reference=issue_reference(db, principal.user.company_id, "COMMERCIAL_APPROVAL", "CAP"), title=title,
        amount=money(amount), status="pending", current_step_order=1, requested_by=principal.user.full_name,
    )
    db.add(row)
    db.flush()
    return row


def approved_variation_total(db: Session, contract_id: int) -> Decimal:
    return money(db.scalar(select(func.coalesce(func.sum(ClientVariation.value), 0)).where(ClientVariation.contract_id == contract_id, ClientVariation.status == "approved")) or 0)


def current_contract_sum(db: Session, contract: ClientContract) -> Decimal:
    return money(Decimal(contract.original_contract_sum) + approved_variation_total(db, contract.id))


def approved_valuation_total(db: Session, contract_id: int) -> Decimal:
    return money(db.scalar(select(func.coalesce(func.sum(ClientValuation.gross_value), 0)).where(ClientValuation.contract_id == contract_id, ClientValuation.status.in_(("approved", "invoiced", "part_paid", "paid")))) or 0)


def cost_actual_total(db: Session, project_id: int) -> Decimal:
    # A reversed original remains part of the immutable ledger; its controlled negative
    # reversal offsets it. Excluding the original would make a reversal look like income.
    return money(db.scalar(select(func.coalesce(func.sum(ProjectCostTransaction.amount), 0)).where(ProjectCostTransaction.project_id == project_id, ProjectCostTransaction.status.in_(("posted", "reversed")))) or 0)


def procurement_commitment(db: Session, project_id: int) -> Decimal:
    return money(db.scalar(select(func.coalesce(func.sum(PurchaseOrder.total_amount), 0)).where(PurchaseOrder.project_id == project_id, PurchaseOrder.status.in_(("submitted", "approved", "issued", "part_received", "received")))) or 0)


def subcontract_commitment(db: Session, project_id: int) -> Decimal:
    contracts = db.scalars(select(SubcontractContract).where(SubcontractContract.project_id == project_id, SubcontractContract.status.in_(("submitted", "active", "completed")))).all()
    return money(sum((Decimal(item.original_contract_sum) + (db.scalar(select(func.coalesce(func.sum(SubcontractVariation.value), 0)).where(SubcontractVariation.contract_id == item.id, SubcontractVariation.status == "approved")) or Decimal("0")) for item in contracts), Decimal("0")))


def latest_budget(db: Session, project: Project) -> Decimal:
    baseline = db.scalar(select(ProjectBudgetBaseline).where(ProjectBudgetBaseline.project_id == project.id, ProjectBudgetBaseline.status == "approved").order_by(ProjectBudgetBaseline.version.desc()).limit(1))
    return money(baseline.total_amount if baseline else project.baseline_budget)


def bootstrap_permissions(db: Session, company_id: int) -> None:
    permissions: dict[str, Permission] = {}
    for code, (module, action, description) in PERMISSIONS.items():
        row = db.scalar(select(Permission).where(Permission.code == code))
        if not row:
            row = Permission(code=code, module=module, action=action, description=description)
            db.add(row); db.flush()
        permissions[code] = row
    roles = {row.code: row for row in db.scalars(select(Role).where(Role.company_id == company_id)).all()}
    for code, name, scope in (("COMMERCIAL_MANAGER", "Commercial Manager", "company"), ("QUANTITY_SURVEYOR", "Quantity Surveyor", "branch"), ("PROJECT_COMMERCIAL_OFFICER", "Project Commercial Officer", "site")):
        if code not in roles:
            row = Role(company_id=company_id, code=code, name=name, scope_level=scope, description=f"Phase 11 {name.lower()} role", is_system=True, is_active=True)
            db.add(row); db.flush(); roles[code] = row
    grants = {
        "SYSTEM_ADMIN": set(PERMISSIONS), "HQ_EXECUTIVE": {"commercial.view", "commercial.approve", "commercial.export"},
        "BRANCH_MANAGER": {"commercial.view", "commercial.manage", "commercial.approve", "commercial.export"},
        "SITE_MANAGER": {"commercial.view", "commercial.manage"}, "PROJECT_MANAGER": {"commercial.view", "commercial.manage"},
        "APPROVER": {"commercial.approve"}, "AUDITOR": {"commercial.view", "commercial.export"},
        "COMMERCIAL_MANAGER": set(PERMISSIONS), "QUANTITY_SURVEYOR": {"commercial.view", "commercial.manage", "commercial.export"},
        "PROJECT_COMMERCIAL_OFFICER": {"commercial.view", "commercial.manage"},
    }
    for role_code, codes in grants.items():
        role = roles.get(role_code)
        if not role:
            continue
        existing = set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id == role.id)).all())
        for code in codes:
            if permissions[code].id not in existing:
                db.add(RolePermission(role_id=role.id, permission_id=permissions[code].id)); existing.add(permissions[code].id)
    for code, name, prefix in (("CLIENT_CONTRACT", "Client Contract", "CLC"), ("CLIENT_VARIATION", "Client Variation", "CLV"), ("PROJECT_COST", "Project Cost Transaction", "PCT"), ("CLIENT_VALUATION", "Client Valuation", "CLN"), ("CLIENT_INVOICE", "Client Invoice", "CLI"), ("CLIENT_CLAIM", "Client Claim", "CLC"), ("COMMERCIAL_APPROVAL", "Commercial Approval", "CAP")):
        if not db.scalar(select(NumberSequence).where(NumberSequence.company_id == company_id, NumberSequence.code == code)):
            db.add(NumberSequence(company_id=company_id, code=code, name=name, prefix=prefix, next_number=1, padding=5, reset_period="yearly"))
    branch, hq = roles.get("BRANCH_MANAGER"), roles.get("HQ_EXECUTIVE")
    if not branch or not hq:
        raise HTTPException(status_code=409, detail="Branch Manager and HQ Executive roles are required")
    for code, name in (("CLIENT_CONTRACT", "Client Contract Approval"), ("CLIENT_VARIATION", "Client Variation Approval"), ("CLIENT_VALUATION", "Client Valuation Approval"), ("CLIENT_INVOICE", "Client Invoice Approval"), ("CLIENT_CLAIM", "Client Claim Approval")):
        row = db.scalar(select(ApprovalWorkflow).where(ApprovalWorkflow.company_id == company_id, ApprovalWorkflow.code == code))
        if not row:
            row = ApprovalWorkflow(company_id=company_id, code=code, name=name, module="commercial", description=f"Controlled {name.lower()}", min_amount=Decimal("0"), is_active=True)
            db.add(row); db.flush()
        if not db.scalar(select(func.count()).select_from(ApprovalStep).where(ApprovalStep.workflow_id == row.id)):
            db.add_all([ApprovalStep(workflow_id=row.id, step_order=1, name="Branch Commercial Review", role_id=branch.id, required_approvals=1, escalation_hours=24), ApprovalStep(workflow_id=row.id, step_order=2, name="Head Office Commercial Approval", role_id=hq.id, required_approvals=1, escalation_hours=48)])
    if not db.scalar(select(CompanySetting).where(CompanySetting.company_id == company_id, CompanySetting.key == "commercial_policy")):
        db.add(CompanySetting(company_id=company_id, key="commercial_policy", value=dict(POLICY_DEFAULT), description="Phase 11 commercial governance"))


class ContractInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: int
    title: str = Field(min_length=2, max_length=240)
    client_name: str = Field(min_length=2, max_length=240)
    client_reference: str | None = Field(default=None, max_length=180)
    start_date: date
    completion_date: date
    original_contract_sum: Decimal = Field(ge=0)
    retention_pct: Decimal | None = Field(default=None, ge=0, le=100)
    contract_document_id: int | None = None
    notes: str | None = None


class VariationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=2, max_length=240)
    reason: str = Field(min_length=5)
    value: Decimal
    time_extension_days: int = Field(default=0, ge=0, le=3650)
    document_id: int | None = None


class CostInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: int
    transaction_date: date
    transaction_type: Literal["actual", "accrual", "adjustment"] = "actual"
    cost_type: Literal["labour", "materials", "plant", "subcontract", "overhead", "professional", "other"]
    cost_code: str | None = Field(default=None, max_length=80)
    description: str = Field(min_length=2, max_length=300)
    amount: Decimal = Field(gt=0)
    source_type: str | None = Field(default=None, max_length=64)
    source_reference: str | None = Field(default=None, max_length=160)
    document_id: int | None = None
    notes: str | None = None


class ValuationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period_start: date
    period_end: date
    gross_value: Decimal = Field(ge=0)
    other_deductions: Decimal = Field(default=0, ge=0)
    evidence_document_id: int | None = None
    notes: str | None = None


class InvoiceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invoice_date: date
    due_date: date | None = None
    invoice_document_id: int | None = None
    notes: str | None = None


class ReceiptInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receipt_reference: str = Field(min_length=2, max_length=120)
    receipt_date: date
    amount: Decimal = Field(gt=0)
    payment_document_id: int | None = None
    notes: str | None = None


class ClaimInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: int
    contract_id: int | None = None
    claim_type: Literal["extension_of_time", "prolongation", "disruption", "payment", "variation", "other"]
    title: str = Field(min_length=2, max_length=240)
    basis: str = Field(min_length=8)
    claimed_amount: Decimal = Field(ge=0)
    notice_date: date | None = None
    response_due_date: date | None = None
    document_id: int | None = None
    notes: str | None = None


class ClaimResolutionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["agreed", "rejected", "withdrawn"]
    assessed_amount: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None


class ForecastInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: int
    forecast_month: date
    expected_inflow: Decimal = Field(ge=0)
    expected_outflow: Decimal = Field(ge=0)
    source: Literal["manual", "valuation", "commercial_review"] = "manual"
    notes: str | None = None


class ApprovalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]
    comment: str | None = Field(default=None, max_length=2000)


@router.get("/status")
def status(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    return {"phase": 11, "module": "cost_and_commercial_control", "configured": bool(db.scalar(select(CompanySetting).where(CompanySetting.company_id == principal.user.company_id, CompanySetting.key == "commercial_policy"))), "currency": "LSL"}


@router.post("/bootstrap")
def bootstrap(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, str]:
    if not principal.has_company_permission("company.manage") and not principal.has_company_permission("commercial.manage"):
        raise HTTPException(status_code=403, detail="Company-level administration is required to initialise Commercial Control")
    bootstrap_permissions(db, principal.user.company_id); commit(db)
    return {"status": "ready", "message": "Commercial permissions, roles, numbers, workflows and policy are ready."}


@router.get("/projects")
def projects(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    require_anywhere(principal, "commercial.view")
    return [row_dict(row) for row in db.scalars(select(Project).where(Project.company_id == principal.user.company_id).order_by(Project.project_number)).all() if principal.can("commercial.view", branch_id=row.branch_id, site_id=row.primary_site_id)]


@router.get("/contracts")
def contracts(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    require_anywhere(principal, "commercial.view")
    return [row_dict(row) for row in db.scalars(select(ClientContract).where(ClientContract.company_id == principal.user.company_id).order_by(ClientContract.created_at.desc())).all() if principal.can("commercial.view", branch_id=row.branch_id, site_id=row.site_id)]


@router.post("/contracts", status_code=201)
def create_contract(payload: ContractInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    project = project_or_404(db, principal, payload.project_id, "commercial.manage")
    if payload.completion_date < payload.start_date:
        raise HTTPException(status_code=422, detail="Contract completion date cannot precede its start date")
    ensure_document(db, project.company_id, payload.contract_document_id)
    cfg = policy(db, project.company_id)
    retention = payload.retention_pct if payload.retention_pct is not None else Decimal(str(cfg["default_retention_pct"]))
    if retention > Decimal(str(cfg["max_retention_pct"])):
        raise HTTPException(status_code=422, detail="Retention exceeds the company commercial-policy maximum")
    row = ClientContract(company_id=project.company_id, branch_id=project.branch_id, site_id=project.primary_site_id, project_id=project.id, cost_centre_id=project.cost_centre_id, contract_number=issue_reference(db, project.company_id, "CLIENT_CONTRACT", "CLC"), title=payload.title, client_name=payload.client_name, client_reference=payload.client_reference or project.contract_reference, start_date=payload.start_date, completion_date=payload.completion_date, original_contract_sum=money(payload.original_contract_sum), retention_pct=retention, contract_document_id=payload.contract_document_id, notes=payload.notes, created_by=principal.user.full_name)
    db.add(row); db.flush(); audit(db, principal, "commercial.contract.created", "client_contract", row.id, project=project, detail={"number": row.contract_number, "amount": str(row.original_contract_sum)}); commit(db, "A client contract already exists for this project")
    return row_dict(row)


@router.get("/contracts/{contract_id:int}")
def contract_detail(contract_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    contract = contract_or_404(db, principal, contract_id)
    return {"contract": {**row_dict(contract), "current_contract_sum": str(current_contract_sum(db, contract))}, "variations": [row_dict(row) for row in db.scalars(select(ClientVariation).where(ClientVariation.contract_id == contract.id).order_by(ClientVariation.id)).all()], "valuations": [row_dict(row) for row in db.scalars(select(ClientValuation).where(ClientValuation.contract_id == contract.id).order_by(ClientValuation.period_end.desc())).all()], "invoices": [row_dict(row) for row in db.scalars(select(ClientInvoice).where(ClientInvoice.contract_id == contract.id).order_by(ClientInvoice.invoice_date.desc())).all()]}


@router.post("/contracts/{contract_id:int}/submit")
def submit_contract(contract_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    contract = contract_or_404(db, principal, contract_id, "commercial.manage")
    if contract.status not in {"draft", "rejected"}:
        raise HTTPException(status_code=409, detail="Only draft/rejected client contracts can be submitted")
    if policy(db, contract.company_id)["evidence_required_for_submission"] and not contract.contract_document_id:
        raise HTTPException(status_code=409, detail="A controlled client-contract document is required before submission")
    project = entity_project(db, contract); request = make_approval(db, principal, code="CLIENT_CONTRACT", entity_type="client_contract", entity_id=contract.id, title=f"Client contract {contract.contract_number}: {contract.title}", project=project, amount=contract.original_contract_sum)
    contract.status, contract.approval_request_id = "submitted", request.id; audit(db, principal, "commercial.contract.submitted", "client_contract", contract.id, project=project, detail={"approval_request_id": request.id}); commit(db)
    return row_dict(request)


@router.post("/contracts/{contract_id:int}/variations", status_code=201)
def create_variation(contract_id: int, payload: VariationInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    contract = contract_or_404(db, principal, contract_id, "commercial.manage")
    if contract.status not in {"submitted", "active", "completed"}:
        raise HTTPException(status_code=409, detail="A client contract must be submitted or active before recording a variation")
    ensure_document(db, contract.company_id, payload.document_id)
    row = ClientVariation(company_id=contract.company_id, contract_id=contract.id, variation_number=issue_reference(db, contract.company_id, "CLIENT_VARIATION", "CLV"), title=payload.title, reason=payload.reason, value=money(payload.value), time_extension_days=payload.time_extension_days, document_id=payload.document_id, created_by=principal.user.full_name)
    project = entity_project(db, contract); db.add(row); db.flush(); audit(db, principal, "commercial.variation.created", "client_variation", row.id, project=project, detail={"number": row.variation_number, "value": str(row.value)}); commit(db)
    return row_dict(row)


@router.post("/variations/{variation_id:int}/submit")
def submit_variation(variation_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = db.get(ClientVariation, variation_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Client variation not found")
    contract = contract_or_404(db, principal, row.contract_id, "commercial.manage")
    if row.status not in {"draft", "rejected"}:
        raise HTTPException(status_code=409, detail="Only draft/rejected client variations can be submitted")
    if policy(db, row.company_id)["evidence_required_for_submission"] and not row.document_id:
        raise HTTPException(status_code=409, detail="A controlled variation document is required before submission")
    project = entity_project(db, contract); request = make_approval(db, principal, code="CLIENT_VARIATION", entity_type="client_variation", entity_id=row.id, title=f"Client variation {row.variation_number}: {row.title}", project=project, amount=row.value)
    row.status, row.approval_request_id = "submitted", request.id; audit(db, principal, "commercial.variation.submitted", "client_variation", row.id, project=project, detail={"approval_request_id": request.id}); commit(db)
    return row_dict(request)


@router.get("/costs")
def costs(project_id: int | None = None, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    require_anywhere(principal, "commercial.view")
    rows = db.scalars(select(ProjectCostTransaction).where(ProjectCostTransaction.company_id == principal.user.company_id).order_by(ProjectCostTransaction.transaction_date.desc(), ProjectCostTransaction.id.desc())).all()
    result = []
    for row in rows:
        if project_id is not None and row.project_id != project_id:
            continue
        if principal.can("commercial.view", branch_id=row.branch_id, site_id=row.site_id): result.append(row_dict(row))
    return result


@router.post("/costs", status_code=201)
def create_cost(payload: CostInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    project = project_or_404(db, principal, payload.project_id, "commercial.manage")
    ensure_document(db, project.company_id, payload.document_id)
    row = ProjectCostTransaction(company_id=project.company_id, branch_id=project.branch_id, site_id=project.primary_site_id, project_id=project.id, cost_centre_id=project.cost_centre_id, transaction_number=issue_reference(db, project.company_id, "PROJECT_COST", "PCT"), transaction_date=payload.transaction_date, transaction_type=payload.transaction_type, cost_type=payload.cost_type, cost_code=payload.cost_code, description=payload.description, amount=money(payload.amount), source_type=payload.source_type, source_reference=payload.source_reference, document_id=payload.document_id, notes=payload.notes, recorded_by=principal.user.full_name)
    db.add(row); db.flush(); audit(db, principal, "commercial.cost.posted", "project_cost_transaction", row.id, project=project, detail={"number": row.transaction_number, "amount": str(row.amount), "type": row.cost_type}); commit(db)
    return row_dict(row)


@router.post("/costs/{cost_id:int}/reverse", status_code=201)
def reverse_cost(cost_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    original = db.get(ProjectCostTransaction, cost_id)
    if not original or original.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Cost transaction not found")
    project = project_or_404(db, principal, original.project_id, "commercial.manage")
    if original.status != "posted":
        raise HTTPException(status_code=409, detail="Only posted cost transactions can be reversed")
    row = ProjectCostTransaction(company_id=original.company_id, branch_id=original.branch_id, site_id=original.site_id, project_id=original.project_id, cost_centre_id=original.cost_centre_id, transaction_number=issue_reference(db, original.company_id, "PROJECT_COST", "PCT"), transaction_date=date.today(), transaction_type="adjustment", cost_type=original.cost_type, cost_code=original.cost_code, description=f"Reversal of {original.transaction_number}: {original.description}", amount=money(-Decimal(original.amount)), source_type="reversal", source_reference=original.transaction_number, document_id=original.document_id, reversal_of_id=original.id, notes="System-controlled reversal; original remains immutable.", recorded_by=principal.user.full_name)
    original.status = "reversed"; db.add(row); db.flush(); audit(db, principal, "commercial.cost.reversed", "project_cost_transaction", row.id, project=project, detail={"reversal_of": original.transaction_number}); commit(db)
    return row_dict(row)


@router.post("/contracts/{contract_id:int}/valuations", status_code=201)
def create_valuation(contract_id: int, payload: ValuationInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    contract = contract_or_404(db, principal, contract_id, "commercial.manage")
    if contract.status != "active":
        raise HTTPException(status_code=409, detail="Only an active client contract may be valued")
    if payload.period_end < payload.period_start:
        raise HTTPException(status_code=422, detail="Valuation period end cannot precede the start")
    ensure_document(db, contract.company_id, payload.evidence_document_id)
    previous = approved_valuation_total(db, contract.id); gross = money(payload.gross_value); cumulative = money(previous + gross)
    ceiling = current_contract_sum(db, contract)
    if cumulative > ceiling:
        raise HTTPException(status_code=409, detail=f"Valuation exceeds the approved client contract ceiling of {ceiling}")
    retention = money(gross * Decimal(contract.retention_pct) / Decimal("100")); net = money(gross - retention - money(payload.other_deductions))
    if net < 0: raise HTTPException(status_code=422, detail="Valuation deductions cannot exceed the gross value")
    row = ClientValuation(company_id=contract.company_id, contract_id=contract.id, valuation_number=issue_reference(db, contract.company_id, "CLIENT_VALUATION", "CLN"), period_start=payload.period_start, period_end=payload.period_end, gross_value=gross, previous_certified=previous, cumulative_certified=cumulative, retention_deduction=retention, other_deductions=money(payload.other_deductions), net_value=net, evidence_document_id=payload.evidence_document_id, notes=payload.notes, prepared_by=principal.user.full_name)
    project = entity_project(db, contract); db.add(row); db.flush(); audit(db, principal, "commercial.valuation.created", "client_valuation", row.id, project=project, detail={"number": row.valuation_number, "net_value": str(row.net_value)}); commit(db)
    return row_dict(row)


@router.post("/valuations/{valuation_id:int}/submit")
def submit_valuation(valuation_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = db.get(ClientValuation, valuation_id)
    if not row or row.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Client valuation not found")
    contract = contract_or_404(db, principal, row.contract_id, "commercial.manage")
    if row.status not in {"draft", "rejected"}: raise HTTPException(status_code=409, detail="Only draft/rejected valuations can be submitted")
    if policy(db, row.company_id)["evidence_required_for_submission"] and not row.evidence_document_id: raise HTTPException(status_code=409, detail="Controlled valuation evidence is required before submission")
    project = entity_project(db, contract); request = make_approval(db, principal, code="CLIENT_VALUATION", entity_type="client_valuation", entity_id=row.id, title=f"Client valuation {row.valuation_number}", project=project, amount=row.net_value)
    row.status, row.approval_request_id = "submitted", request.id; audit(db, principal, "commercial.valuation.submitted", "client_valuation", row.id, project=project, detail={"approval_request_id": request.id}); commit(db)
    return row_dict(request)


@router.post("/valuations/{valuation_id:int}/invoices", status_code=201)
def create_invoice(valuation_id: int, payload: InvoiceInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    valuation = db.get(ClientValuation, valuation_id)
    if not valuation or valuation.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Client valuation not found")
    contract = contract_or_404(db, principal, valuation.contract_id, "commercial.manage")
    if valuation.status != "approved": raise HTTPException(status_code=409, detail="Only an approved valuation can become a client invoice")
    ensure_document(db, valuation.company_id, payload.invoice_document_id)
    row = ClientInvoice(company_id=valuation.company_id, contract_id=contract.id, valuation_id=valuation.id, invoice_number=issue_reference(db, valuation.company_id, "CLIENT_INVOICE", "CLI"), invoice_date=payload.invoice_date, due_date=payload.due_date, gross_amount=valuation.gross_value, retention_amount=valuation.retention_deduction, net_amount=valuation.net_value, invoice_document_id=payload.invoice_document_id, notes=payload.notes, created_by=principal.user.full_name)
    project = entity_project(db, contract); db.add(row); db.flush(); audit(db, principal, "commercial.invoice.created", "client_invoice", row.id, project=project, detail={"number": row.invoice_number, "net_amount": str(row.net_amount)}); commit(db, "An invoice already exists for this valuation")
    return row_dict(row)


@router.post("/invoices/{invoice_id:int}/submit")
def submit_invoice(invoice_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = db.get(ClientInvoice, invoice_id)
    if not row or row.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Client invoice not found")
    contract = contract_or_404(db, principal, row.contract_id, "commercial.manage")
    if row.status not in {"draft", "rejected"}: raise HTTPException(status_code=409, detail="Only draft/rejected invoices can be submitted")
    if policy(db, row.company_id)["evidence_required_for_submission"] and not row.invoice_document_id: raise HTTPException(status_code=409, detail="A controlled client invoice document is required before submission")
    project = entity_project(db, contract); request = make_approval(db, principal, code="CLIENT_INVOICE", entity_type="client_invoice", entity_id=row.id, title=f"Client invoice {row.invoice_number}", project=project, amount=row.net_amount)
    row.status, row.approval_request_id = "submitted", request.id; audit(db, principal, "commercial.invoice.submitted", "client_invoice", row.id, project=project, detail={"approval_request_id": request.id}); commit(db)
    return row_dict(request)


@router.post("/invoices/{invoice_id:int}/receipts", status_code=201)
def record_receipt(invoice_id: int, payload: ReceiptInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    invoice = db.get(ClientInvoice, invoice_id)
    if not invoice or invoice.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Client invoice not found")
    contract = contract_or_404(db, principal, invoice.contract_id, "commercial.receive")
    if invoice.status not in {"issued", "part_paid"}: raise HTTPException(status_code=409, detail="Only an issued client invoice can have payment evidence")
    ensure_document(db, invoice.company_id, payload.payment_document_id)
    outstanding = money(Decimal(invoice.net_amount) - Decimal(invoice.paid_amount)); amount = money(payload.amount)
    if amount > outstanding: raise HTTPException(status_code=409, detail=f"Receipt exceeds the outstanding invoice value of {outstanding}")
    row = ClientReceipt(company_id=invoice.company_id, invoice_id=invoice.id, receipt_reference=payload.receipt_reference, receipt_date=payload.receipt_date, amount=amount, payment_document_id=payload.payment_document_id, notes=payload.notes, recorded_by=principal.user.full_name)
    invoice.paid_amount = money(Decimal(invoice.paid_amount) + amount); invoice.status = "paid" if invoice.paid_amount >= invoice.net_amount else "part_paid"
    project = entity_project(db, contract); db.add(row); db.flush(); audit(db, principal, "commercial.receipt.recorded", "client_receipt", row.id, project=project, detail={"invoice": invoice.invoice_number, "amount": str(amount)}); commit(db, "Receipt reference already exists")
    return row_dict(row)


@router.get("/claims")
def claims(project_id: int | None = None, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    require_anywhere(principal, "commercial.view")
    rows = db.scalars(select(ClientClaim).where(ClientClaim.company_id == principal.user.company_id).order_by(ClientClaim.created_at.desc())).all()
    return [row_dict(row) for row in rows if (project_id is None or row.project_id == project_id) and principal.can("commercial.view", branch_id=row.branch_id, site_id=row.site_id)]


@router.post("/claims", status_code=201)
def create_claim(payload: ClaimInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    project = project_or_404(db, principal, payload.project_id, "commercial.manage")
    contract = None
    if payload.contract_id is not None:
        contract = contract_or_404(db, principal, payload.contract_id, "commercial.manage")
        if contract.project_id != project.id: raise HTTPException(status_code=422, detail="Client claim contract does not belong to the selected project")
    ensure_document(db, project.company_id, payload.document_id)
    row = ClientClaim(company_id=project.company_id, branch_id=project.branch_id, site_id=project.primary_site_id, project_id=project.id, contract_id=contract.id if contract else None, claim_number=issue_reference(db, project.company_id, "CLIENT_CLAIM", "CLC"), claim_type=payload.claim_type, title=payload.title, basis=payload.basis, claimed_amount=money(payload.claimed_amount), notice_date=payload.notice_date, response_due_date=payload.response_due_date, document_id=payload.document_id, notes=payload.notes, created_by=principal.user.full_name)
    db.add(row); db.flush(); audit(db, principal, "commercial.claim.created", "client_claim", row.id, project=project, detail={"number": row.claim_number, "amount": str(row.claimed_amount)}); commit(db)
    return row_dict(row)


@router.post("/claims/{claim_id:int}/submit")
def submit_claim(claim_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = db.get(ClientClaim, claim_id)
    if not row or row.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Client claim not found")
    project = project_or_404(db, principal, row.project_id, "commercial.manage")
    if row.status not in {"draft", "rejected"}: raise HTTPException(status_code=409, detail="Only draft/rejected claims can be submitted")
    if policy(db, row.company_id)["evidence_required_for_submission"] and not row.document_id: raise HTTPException(status_code=409, detail="A controlled claim document is required before submission")
    request = make_approval(db, principal, code="CLIENT_CLAIM", entity_type="client_claim", entity_id=row.id, title=f"Client claim {row.claim_number}: {row.title}", project=project, amount=row.claimed_amount)
    row.status, row.approval_request_id = "submitted", request.id; audit(db, principal, "commercial.claim.submitted", "client_claim", row.id, project=project, detail={"approval_request_id": request.id}); commit(db)
    return row_dict(request)


@router.post("/claims/{claim_id:int}/resolve")
def resolve_claim(claim_id: int, payload: ClaimResolutionInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = db.get(ClientClaim, claim_id)
    if not row or row.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Client claim not found")
    project = project_or_404(db, principal, row.project_id, "commercial.manage")
    if row.status not in {"submitted", "under_review"}: raise HTTPException(status_code=409, detail="Only submitted/under-review claims can be resolved")
    row.status, row.assessed_amount, row.notes, row.resolved_at = payload.status, money(payload.assessed_amount) if payload.assessed_amount is not None else None, payload.notes or row.notes, utcnow()
    audit(db, principal, "commercial.claim.resolved", "client_claim", row.id, project=project, detail={"status": row.status, "assessed_amount": str(row.assessed_amount) if row.assessed_amount is not None else None}); commit(db)
    return row_dict(row)


@router.get("/cash-flow")
def cash_flow(project_id: int | None = None, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    require_anywhere(principal, "commercial.view")
    rows = db.scalars(select(ProjectCashFlowForecast).where(ProjectCashFlowForecast.company_id == principal.user.company_id).order_by(ProjectCashFlowForecast.forecast_month)).all()
    return [row_dict(row) for row in rows if (project_id is None or row.project_id == project_id) and (project := db.get(Project, row.project_id)) and principal.can("commercial.view", branch_id=project.branch_id, site_id=project.primary_site_id)]


@router.post("/cash-flow", status_code=201)
def create_forecast(payload: ForecastInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    project = project_or_404(db, principal, payload.project_id, "commercial.manage")
    if payload.forecast_month.day != 1: raise HTTPException(status_code=422, detail="Cash-flow forecast month must be the first day of its month")
    row = ProjectCashFlowForecast(company_id=project.company_id, project_id=project.id, forecast_month=payload.forecast_month, expected_inflow=money(payload.expected_inflow), expected_outflow=money(payload.expected_outflow), net_cash=money(payload.expected_inflow - payload.expected_outflow), source=payload.source, notes=payload.notes, prepared_by=principal.user.full_name)
    db.add(row); db.flush(); audit(db, principal, "commercial.cashflow.created", "project_cash_flow_forecast", row.id, project=project, detail={"month": row.forecast_month.isoformat(), "net": str(row.net_cash)}); commit(db, "A cash-flow forecast already exists for this project and month")
    return row_dict(row)


@router.post("/approvals/{request_id:int}/decision")
def decide_approval(request_id: int, payload: ApprovalInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    request = db.get(ApprovalRequest, request_id)
    mapping = {"client_contract": (ClientContract, "submitted"), "client_variation": (ClientVariation, "submitted"), "client_valuation": (ClientValuation, "submitted"), "client_invoice": (ClientInvoice, "submitted"), "client_claim": (ClientClaim, "submitted")}
    if not request or request.company_id != principal.user.company_id or request.entity_type not in mapping: raise HTTPException(status_code=404, detail="Commercial approval request not found")
    model, expected = mapping[request.entity_type]; entity = db.get(model, int(request.entity_id))
    if not entity: raise HTTPException(status_code=404, detail="Commercial approval entity not found")
    project = entity_project(db, entity); require_scope(principal, "commercial.approve", project.branch_id, project.primary_site_id)
    if request.status != "pending" or entity.status != expected: raise HTTPException(status_code=409, detail="Commercial approval request is not pending")
    step = db.scalar(select(ApprovalStep).where(ApprovalStep.workflow_id == request.workflow_id, ApprovalStep.step_order == request.current_step_order))
    if not step or not assignment_authorised(db, principal, step.role_id, project.branch_id, project.primary_site_id): raise HTTPException(status_code=403, detail="Your active role assignment is not authorised for this approval step")
    if request.requested_by == principal.user.full_name and not allow_self_approval(db, principal.user.company_id): raise HTTPException(status_code=422, detail="Self-approval is disabled by company policy")
    db.add(ApprovalAction(request_id=request.id, step_order=step.step_order, role_id=step.role_id, actor_name=principal.user.full_name, action=payload.decision, comment=payload.comment))
    if payload.decision == "reject":
        request.status, request.completed_at, entity.status = "rejected", utcnow(), "rejected"
    else:
        approved = (db.scalar(select(func.count()).select_from(ApprovalAction).where(ApprovalAction.request_id == request.id, ApprovalAction.step_order == step.step_order, ApprovalAction.action == "approve")) or 0) + 1
        if approved >= step.required_approvals:
            next_step = db.scalar(select(ApprovalStep).where(ApprovalStep.workflow_id == request.workflow_id, ApprovalStep.step_order > step.step_order).order_by(ApprovalStep.step_order).limit(1))
            if next_step: request.current_step_order = next_step.step_order
            else:
                request.status, request.completed_at = "approved", utcnow()
                if isinstance(entity, ClientContract): entity.status, entity.approved_at, entity.approved_snapshot = "active", utcnow(), {"contract": row_dict(entity), "approved_at": utcnow().isoformat()}
                elif isinstance(entity, ClientVariation): entity.status, entity.approved_at = "approved", utcnow()
                elif isinstance(entity, ClientValuation): entity.status, entity.approved_at = "approved", utcnow()
                elif isinstance(entity, ClientInvoice): entity.status, entity.issued_at = "issued", utcnow()
                elif isinstance(entity, ClientClaim): entity.status, entity.submitted_at = "submitted", utcnow()
    audit(db, principal, f"commercial.approval.{payload.decision}", "approval_request", request.id, project=project, detail={"entity_type": request.entity_type, "status": request.status, "step": step.step_order}); commit(db)
    return row_dict(request)


@router.get("/dashboard/projects/{project_id:int}")
def project_dashboard(project_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    project = project_or_404(db, principal, project_id)
    contract = db.scalar(select(ClientContract).where(ClientContract.project_id == project.id))
    budget, actual = latest_budget(db, project), cost_actual_total(db, project.id)
    po_commitment, sc_commitment = procurement_commitment(db, project.id), subcontract_commitment(db, project.id)
    commitment = money(po_commitment + sc_commitment); revenue = current_contract_sum(db, contract) if contract else money(project.contract_amount)
    valuations = approved_valuation_total(db, contract.id) if contract else Decimal("0")
    invoices = db.scalars(select(ClientInvoice).where(ClientInvoice.contract_id == contract.id)).all() if contract else []
    invoiced = money(sum((Decimal(row.net_amount) for row in invoices if row.status in {"issued", "part_paid", "paid"}), Decimal("0")))
    receipts = money(sum((Decimal(row.paid_amount) for row in invoices), Decimal("0")))
    forecast = [row_dict(row) for row in db.scalars(select(ProjectCashFlowForecast).where(ProjectCashFlowForecast.project_id == project.id).order_by(ProjectCashFlowForecast.forecast_month)).all()]
    return {"project": row_dict(project), "client_contract": row_dict(contract) if contract else None, "budget": str(budget), "actual_cost": str(actual), "purchase_order_commitment": str(po_commitment), "subcontract_commitment": str(sc_commitment), "total_commitment": str(commitment), "cost_to_complete_exposure": str(money(actual + commitment)), "budget_remaining_after_exposure": str(money(budget - actual - commitment)), "current_revenue": str(revenue), "approved_valuations": str(valuations), "invoiced": str(invoiced), "receipts": str(receipts), "receivable": str(money(invoiced - receipts)), "forecast_gross_margin": str(money(revenue - actual - commitment)), "cash_flow": forecast}


@router.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_anywhere(principal, "commercial.view")
    projects = [row for row in db.scalars(select(Project).where(Project.company_id == principal.user.company_id)).all() if principal.can("commercial.view", branch_id=row.branch_id, site_id=row.primary_site_id)]
    contracts = [row for row in db.scalars(select(ClientContract).where(ClientContract.company_id == principal.user.company_id)).all() if principal.can("commercial.view", branch_id=row.branch_id, site_id=row.site_id)]
    invoices = [row for row in db.scalars(select(ClientInvoice).where(ClientInvoice.company_id == principal.user.company_id)).all() if (contract := db.get(ClientContract, row.contract_id)) and principal.can("commercial.view", branch_id=contract.branch_id, site_id=contract.site_id)]
    claims = [row for row in db.scalars(select(ClientClaim).where(ClientClaim.company_id == principal.user.company_id)).all() if principal.can("commercial.view", branch_id=row.branch_id, site_id=row.site_id)]
    return {"projects": len(projects), "active_client_contracts": sum(row.status == "active" for row in contracts), "current_contract_value": str(money(sum((current_contract_sum(db, row) for row in contracts if row.status in {"submitted", "active", "completed"}), Decimal("0")))), "invoiced": str(money(sum((Decimal(row.net_amount) for row in invoices if row.status in {"issued", "part_paid", "paid"}), Decimal("0")))), "receipts": str(money(sum((Decimal(row.paid_amount) for row in invoices), Decimal("0")))), "open_claims": sum(row.status in {"draft", "submitted", "under_review"} for row in claims), "actual_cost": str(money(sum((cost_actual_total(db, row.id) for row in projects), Decimal("0")))), "commitments": str(money(sum((procurement_commitment(db, row.id) + subcontract_commitment(db, row.id) for row in projects), Decimal("0"))))}


@router.get("/dashboard/alerts")
def dashboard_alerts(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    require_anywhere(principal, "commercial.view")
    result: list[dict[str, Any]] = []; cfg = policy(db, principal.user.company_id); today = date.today()
    for project in db.scalars(select(Project).where(Project.company_id == principal.user.company_id)).all():
        if not principal.can("commercial.view", branch_id=project.branch_id, site_id=project.primary_site_id): continue
        budget, exposure = latest_budget(db, project), money(cost_actual_total(db, project.id) + procurement_commitment(db, project.id) + subcontract_commitment(db, project.id))
        if budget > 0 and exposure > budget * (Decimal("1") + Decimal(str(cfg["cost_variance_warning_pct"])) / Decimal("100")):
            result.append({"type": "cost_exposure", "severity": "critical", "project_id": project.id, "reference": project.project_number, "message": f"Actual and committed exposure {exposure} exceeds budget {budget}"})
    for invoice in db.scalars(select(ClientInvoice).where(ClientInvoice.company_id == principal.user.company_id, ClientInvoice.status.in_(("issued", "part_paid")), ClientInvoice.due_date.is_not(None))).all():
        contract = db.get(ClientContract, invoice.contract_id)
        if contract and principal.can("commercial.view", branch_id=contract.branch_id, site_id=contract.site_id) and invoice.due_date <= today:
            result.append({"type": "invoice_overdue", "severity": "critical" if invoice.due_date < today else "warning", "reference": invoice.invoice_number, "message": f"Client invoice due {invoice.due_date.isoformat()}"})
    for claim in db.scalars(select(ClientClaim).where(ClientClaim.company_id == principal.user.company_id, ClientClaim.status.in_(("draft", "submitted", "under_review")), ClientClaim.response_due_date.is_not(None))).all():
        if claim.response_due_date <= today and principal.can("commercial.view", branch_id=claim.branch_id, site_id=claim.site_id): result.append({"type": "claim_due", "severity": "critical" if claim.response_due_date < today else "warning", "reference": claim.claim_number, "message": f"Claim response due {claim.response_due_date.isoformat()}"})
    return result


@router.get("/exports/project-commercial.csv")
def export_project_commercial(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> StreamingResponse:
    require_anywhere(principal, "commercial.export")
    output = io.StringIO(); writer = csv.writer(output); writer.writerow(["Project", "Budget", "Actual Cost", "PO Commitment", "Subcontract Commitment", "Revenue", "Approved Valuations", "Invoiced", "Receipts", "Forecast Gross Margin"])
    for project in db.scalars(select(Project).where(Project.company_id == principal.user.company_id).order_by(Project.project_number)).all():
        if not principal.can("commercial.export", branch_id=project.branch_id, site_id=project.primary_site_id): continue
        contract = db.scalar(select(ClientContract).where(ClientContract.project_id == project.id)); budget, actual = latest_budget(db, project), cost_actual_total(db, project.id); po, subcontract = procurement_commitment(db, project.id), subcontract_commitment(db, project.id); revenue = current_contract_sum(db, contract) if contract else money(project.contract_amount); valuations = approved_valuation_total(db, contract.id) if contract else Decimal("0"); invoices = db.scalars(select(ClientInvoice).where(ClientInvoice.contract_id == contract.id)).all() if contract else []; invoiced = money(sum((Decimal(row.net_amount) for row in invoices if row.status in {"issued", "part_paid", "paid"}), Decimal("0"))); receipts = money(sum((Decimal(row.paid_amount) for row in invoices), Decimal("0"))); writer.writerow([project.project_number, budget, actual, po, subcontract, revenue, valuations, invoiced, receipts, money(revenue - actual - po - subcontract)])
    return StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=buildtrack-project-commercial.csv"})


@router.get("/audit/events")
def audit_events(limit: int = Query(default=250, ge=1, le=1000), db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    require_anywhere(principal, "commercial.view")
    return [row_dict(row) for row in db.scalars(select(CommercialAuditEvent).where(CommercialAuditEvent.company_id == principal.user.company_id).order_by(CommercialAuditEvent.occurred_at.desc()).limit(limit)).all() if row.branch_id is None or principal.can("commercial.view", branch_id=row.branch_id, site_id=row.site_id)]
