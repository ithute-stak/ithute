from __future__ import annotations

import csv
import io
from datetime import date, datetime, timezone
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
    GoodsReceipt,
    GoodsReceiptLine,
    NumberSequence,
    Permission,
    ProcurementAuditEvent,
    ProcurementRequisition,
    ProcurementRequisitionLine,
    Project,
    PurchaseOrder,
    PurchaseOrderLine,
    Role,
    RolePermission,
    Site,
    SiteMaterialEntry,
    StockBalance,
    StockItem,
    StockMovement,
    StockTransfer,
    StockTransferLine,
    StoreLocation,
    Supplier,
    SupplierQuotation,
    SupplierQuotationLine,
    UserRoleAssignment,
)
from app.security.access import Principal, current_principal

router = APIRouter(prefix="/procurement", tags=["Phase 8 - Procurement & Stores"])
MONEY = Decimal("0.01")
QTY = Decimal("0.001")
COST = Decimal("0.0001")

PERMISSION_ACTIONS = {
    "procurement.view": ("procurement", "view", "View requisitions, quotations and purchase orders"),
    "procurement.manage": ("procurement", "manage", "Create and manage procurement transactions"),
    "procurement.approve": ("procurement", "approve", "Approve requisitions and purchase orders"),
    "procurement.export": ("procurement", "export", "Export procurement evidence"),
    "suppliers.view": ("suppliers", "view", "View supplier records"),
    "suppliers.manage": ("suppliers", "manage", "Create and maintain supplier records"),
    "stores.view": ("stores", "view", "View stores, stock and movements"),
    "stores.manage": ("stores", "manage", "Maintain store locations and stock master data"),
    "stores.issue": ("stores", "issue", "Issue and return stock"),
    "stores.transfer": ("stores", "transfer", "Transfer stock between stores"),
    "stores.adjust": ("stores", "adjust", "Post controlled stock adjustments"),
    "stores.export": ("stores", "export", "Export stock and movement evidence"),
}

POLICY_DEFAULT = {
    "minimum_quotes": 3,
    "low_value_quote_waiver": 5000,
    "po_overrun_tolerance_pct": 0,
    "reorder_alert_enabled": True,
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def qty(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(QTY, rounding=ROUND_HALF_UP)


def unit_cost(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(COST, rounding=ROUND_HALF_UP)


def json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def row_dict(row: Any) -> dict[str, Any]:
    return {column.name: json_value(getattr(row, column.name)) for column in row.__table__.columns}


def commit(db: Session, detail: str = "The procurement record conflicts with existing data") -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=detail) from error


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
    db.add(ProcurementAuditEvent(
        company_id=principal.user.company_id,
        branch_id=branch_id,
        site_id=site_id,
        actor=principal.user.full_name,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        detail=detail or {},
    ))


def issue_reference(db: Session, company_id: int, code: str, prefix: str) -> str:
    sequence = db.scalar(select(NumberSequence).where(NumberSequence.company_id == company_id, NumberSequence.code == code))
    if not sequence:
        sequence = NumberSequence(company_id=company_id, code=code, name=code.replace("_", " ").title(), prefix=prefix, next_number=1, padding=5, reset_period="yearly")
        db.add(sequence); db.flush()
    now = utcnow()
    reset_key = str(now.year) if sequence.reset_period == "yearly" else (now.strftime("%Y-%m") if sequence.reset_period == "monthly" else "never")
    if sequence.reset_period != "never" and sequence.last_reset_key != reset_key:
        sequence.next_number = 1; sequence.last_reset_key = reset_key
    number = sequence.next_number; sequence.next_number += 1
    suffix = f"-{reset_key}" if sequence.reset_period == "yearly" else (f"-{reset_key.replace('-', '')}" if sequence.reset_period == "monthly" else "")
    return f"{sequence.prefix}{suffix}-{number:0{sequence.padding}d}"


def policy(db: Session, company_id: int) -> dict[str, Any]:
    row = db.scalar(select(CompanySetting).where(CompanySetting.company_id == company_id, CompanySetting.key == "procurement_policy"))
    return {**POLICY_DEFAULT, **(row.value if row and isinstance(row.value, dict) else {})}


def allow_self_approval(db: Session, company_id: int) -> bool:
    row = db.scalar(select(CompanySetting).where(CompanySetting.company_id == company_id, CompanySetting.key == "approval_control"))
    return bool(row and isinstance(row.value, dict) and row.value.get("allow_self_approval", False))


def ensure_document(db: Session, company_id: int, document_id: int | None) -> Document | None:
    if document_id is None:
        return None
    row = db.get(Document, document_id)
    if not row or row.company_id != company_id or row.status != "active":
        raise HTTPException(status_code=422, detail="Document is not an active company document")
    return row


def ensure_scope(db: Session, company_id: int, branch_id: int, site_id: int | None = None, project_id: int | None = None, cost_centre_id: int | None = None) -> None:
    branch = db.get(Branch, branch_id)
    if not branch or branch.company_id != company_id:
        raise HTTPException(status_code=422, detail="Branch does not belong to the company")
    if site_id is not None:
        site = db.get(Site, site_id)
        if not site or site.company_id != company_id or site.branch_id != branch_id:
            raise HTTPException(status_code=422, detail="Site does not belong to the selected branch")
    if project_id is not None:
        project = db.get(Project, project_id)
        if not project or project.company_id != company_id or project.branch_id != branch_id:
            raise HTTPException(status_code=422, detail="Project does not belong to the selected branch")
        if site_id is not None and project.primary_site_id != site_id and not db.scalar(select(func.count()).select_from(Site).where(Site.id == site_id, Site.company_id == company_id)):
            raise HTTPException(status_code=422, detail="Project/site scope is invalid")
    if cost_centre_id is not None:
        centre = db.get(CostCentre, cost_centre_id)
        if not centre or centre.company_id != company_id:
            raise HTTPException(status_code=422, detail="Cost centre does not belong to the company")
        if centre.branch_id is not None and centre.branch_id != branch_id:
            raise HTTPException(status_code=422, detail="Cost centre is outside the selected branch")
        if site_id is not None and centre.site_id is not None and centre.site_id != site_id:
            raise HTTPException(status_code=422, detail="Cost centre is outside the selected site")


def location_or_404(db: Session, principal: Principal, location_id: int, permission: str = "stores.view") -> StoreLocation:
    row = db.get(StoreLocation, location_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Store location not found")
    require_scope(principal, permission, row.branch_id, row.site_id)
    return row


def requisition_or_404(db: Session, principal: Principal, requisition_id: int, permission: str = "procurement.view") -> ProcurementRequisition:
    row = db.get(ProcurementRequisition, requisition_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Procurement requisition not found")
    require_scope(principal, permission, row.branch_id, row.site_id)
    return row


def po_or_404(db: Session, principal: Principal, purchase_order_id: int, permission: str = "procurement.view") -> PurchaseOrder:
    row = db.get(PurchaseOrder, purchase_order_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    require_scope(principal, permission, row.branch_id, row.site_id)
    return row


def balance_for(db: Session, company_id: int, location_id: int, stock_item_id: int) -> StockBalance:
    row = db.scalar(select(StockBalance).where(StockBalance.location_id == location_id, StockBalance.stock_item_id == stock_item_id))
    if not row:
        row = StockBalance(company_id=company_id, location_id=location_id, stock_item_id=stock_item_id, quantity_on_hand=Decimal("0"), quantity_reserved=Decimal("0"), average_unit_cost=Decimal("0"))
        db.add(row); db.flush()
    return row


def apply_stock(db: Session, principal: Principal, *, location: StoreLocation, item: StockItem, delta: Decimal, movement_type: str, cost: Decimal | None = None, project_id: int | None = None, site_id: int | None = None, cost_centre_id: int | None = None, site_material_entry_id: int | None = None, reference_type: str | None = None, reference_id: str | int | None = None, reason: str | None = None) -> StockMovement:
    delta = qty(delta)
    if delta == 0:
        raise HTTPException(status_code=422, detail="Stock movement quantity cannot be zero")
    balance = balance_for(db, principal.user.company_id, location.id, item.id)
    old_qty = Decimal(balance.quantity_on_hand or 0)
    old_avg = Decimal(balance.average_unit_cost or 0)
    new_qty = old_qty + delta
    if new_qty < 0:
        raise HTTPException(status_code=409, detail=f"Insufficient stock for {item.sku}: available {old_qty}")
    movement_cost = unit_cost(cost if cost is not None else old_avg)
    if delta > 0:
        if new_qty > 0:
            balance.average_unit_cost = unit_cost(((old_qty * old_avg) + (delta * movement_cost)) / new_qty)
    balance.quantity_on_hand = qty(new_qty)
    movement = StockMovement(
        company_id=principal.user.company_id,
        location_id=location.id,
        stock_item_id=item.id,
        project_id=project_id,
        site_id=site_id,
        cost_centre_id=cost_centre_id,
        site_material_entry_id=site_material_entry_id,
        movement_type=movement_type,
        quantity=delta,
        unit_cost=movement_cost,
        total_cost=money(abs(delta) * movement_cost),
        reference_type=reference_type,
        reference_id=str(reference_id) if reference_id is not None else None,
        reason=reason,
        recorded_by=principal.user.full_name,
    )
    db.add(movement); db.flush()
    return movement


def recalc_requisition(db: Session, req: ProcurementRequisition) -> None:
    total = db.scalar(select(func.coalesce(func.sum(ProcurementRequisitionLine.estimated_total), 0)).where(ProcurementRequisitionLine.requisition_id == req.id)) or Decimal("0")
    req.estimated_total = money(total)


def workflow(db: Session, company_id: int, code: str) -> ApprovalWorkflow:
    row = db.scalar(select(ApprovalWorkflow).where(ApprovalWorkflow.company_id == company_id, ApprovalWorkflow.code == code, ApprovalWorkflow.is_active.is_(True)))
    if not row:
        raise HTTPException(status_code=409, detail=f"Approval workflow {code} is not configured")
    if not db.scalar(select(func.count()).select_from(ApprovalStep).where(ApprovalStep.workflow_id == row.id)):
        raise HTTPException(status_code=409, detail=f"Approval workflow {code} has no steps")
    return row


def create_approval(db: Session, principal: Principal, *, code: str, entity_type: str, entity_id: int, title: str, branch_id: int, site_id: int | None, amount: Decimal | None) -> ApprovalRequest:
    selected = workflow(db, principal.user.company_id, code)
    row = ApprovalRequest(
        company_id=principal.user.company_id, workflow_id=selected.id, branch_id=branch_id, site_id=site_id,
        entity_type=entity_type, entity_id=str(entity_id), reference=issue_reference(db, principal.user.company_id, "APPROVAL", "APR"),
        title=title, amount=amount, status="pending", current_step_order=1, requested_by=principal.user.full_name,
    )
    db.add(row); db.flush(); return row


def assignment_authorised(db: Session, principal: Principal, role_id: int, branch_id: int, site_id: int | None) -> bool:
    role = db.get(Role, role_id)
    if not role:
        return False
    now = utcnow()
    rows = db.scalars(select(UserRoleAssignment).where(UserRoleAssignment.user_id == principal.user.id, UserRoleAssignment.role_id == role_id)).all()
    for assignment in rows:
        if assignment.valid_from and assignment.valid_from > now:
            continue
        if assignment.valid_until and assignment.valid_until < now:
            continue
        if role.scope_level == "company":
            return True
        if role.scope_level == "branch" and assignment.branch_id == branch_id:
            return True
        if role.scope_level == "site" and site_id is not None and assignment.site_id == site_id:
            return True
    return False


class SupplierInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=240)
    registration_number: str | None = Field(default=None, max_length=120)
    tax_number: str | None = Field(default=None, max_length=120)
    contact_name: str | None = Field(default=None, max_length=180)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    address: str | None = None
    categories: list[str] = Field(default_factory=list, max_length=50)
    payment_terms_days: int = Field(default=30, ge=0, le=365)
    status: Literal["active", "suspended", "blacklisted"] = "active"
    compliance_document_id: int | None = None
    notes: str | None = None


class LocationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch_id: int
    site_id: int | None = None
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=2, max_length=200)
    location_type: Literal["head_office_store", "branch_store", "site_store", "yard", "temporary_store"] = "branch_store"
    responsible_employee_id: int | None = None
    notes: str | None = None


class StockItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=2, max_length=300)
    category: str | None = Field(default=None, max_length=100)
    unit: str = Field(min_length=1, max_length=40)
    reorder_level: Decimal = Field(default=0, ge=0)
    max_level: Decimal | None = Field(default=None, ge=0)
    default_unit_cost: Decimal = Field(default=0, ge=0)
    stock_controlled: bool = True
    notes: str | None = None


class RequisitionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch_id: int
    site_id: int | None = None
    project_id: int | None = None
    cost_centre_id: int | None = None
    title: str = Field(min_length=2, max_length=240)
    required_by: date
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    notes: str | None = None


class RequisitionLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stock_item_id: int | None = None
    description: str = Field(min_length=2, max_length=300)
    specification: str | None = None
    quantity: Decimal = Field(gt=0)
    unit: str = Field(min_length=1, max_length=40)
    estimated_unit_cost: Decimal = Field(default=0, ge=0)
    notes: str | None = None


class QuoteLineInput(BaseModel):
    requisition_line_id: int
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    notes: str | None = None


class QuotationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supplier_id: int
    quote_reference: str = Field(min_length=1, max_length=120)
    quote_date: date
    valid_until: date | None = None
    delivery_days: int | None = Field(default=None, ge=0, le=3650)
    tax_amount: Decimal = Field(default=0, ge=0)
    document_id: int | None = None
    notes: str | None = None
    lines: list[QuoteLineInput] = Field(min_length=1, max_length=500)


class POInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requisition_id: int
    quotation_id: int
    delivery_location_id: int
    order_date: date
    expected_delivery_date: date | None = None
    terms: str | None = None
    document_id: int | None = None


class ReceiptLineInput(BaseModel):
    purchase_order_line_id: int
    quantity_received: Decimal = Field(gt=0)
    quantity_accepted: Decimal = Field(ge=0)
    quantity_rejected: Decimal = Field(default=0, ge=0)
    notes: str | None = None


class ReceiptInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receipt_date: date
    delivery_reference: str | None = Field(default=None, max_length=160)
    document_id: int | None = None
    notes: str | None = None
    lines: list[ReceiptLineInput] = Field(min_length=1, max_length=500)


class StockIssueInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    location_id: int
    stock_item_id: int
    quantity: Decimal = Field(gt=0)
    project_id: int | None = None
    site_id: int | None = None
    cost_centre_id: int | None = None
    site_material_entry_id: int | None = None
    reason: str = Field(min_length=2)


class StockReturnInput(StockIssueInput):
    unit_cost: Decimal | None = Field(default=None, ge=0)


class StockAdjustmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    location_id: int
    stock_item_id: int
    quantity_delta: Decimal
    unit_cost: Decimal | None = Field(default=None, ge=0)
    reason: str = Field(min_length=5)


class TransferLineInput(BaseModel):
    stock_item_id: int
    quantity: Decimal = Field(gt=0)


class TransferInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_location_id: int
    to_location_id: int
    notes: str | None = None
    lines: list[TransferLineInput] = Field(min_length=1, max_length=500)


class ApprovalDecisionInput(BaseModel):
    decision: Literal["approve", "reject"]
    comment: str | None = None


class PolicyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    minimum_quotes: int = Field(default=3, ge=1, le=10)
    low_value_quote_waiver: Decimal = Field(default=5000, ge=0)
    po_overrun_tolerance_pct: Decimal = Field(default=0, ge=0, le=100)
    reorder_alert_enabled: bool = True


def bootstrap_permissions(db: Session, company_id: int) -> None:
    permissions: dict[str, Permission] = {}
    for code, (module, action, description) in PERMISSION_ACTIONS.items():
        row = db.scalar(select(Permission).where(Permission.code == code))
        if not row:
            row = Permission(code=code, module=module, action=action, description=description); db.add(row); db.flush()
        permissions[code] = row
    roles = {row.code: row for row in db.scalars(select(Role).where(Role.company_id == company_id)).all()}
    for code, name, scope in (
        ("PROCUREMENT_MANAGER", "Procurement Manager", "company"),
        ("PROCUREMENT_OFFICER", "Procurement Officer", "branch"),
        ("STOREKEEPER", "Storekeeper", "branch"),
    ):
        if code not in roles:
            role = Role(company_id=company_id, code=code, name=name, scope_level=scope, description=f"Phase 8 {name.lower()} role", is_system=True, is_active=True)
            db.add(role); db.flush(); roles[code] = role
    grants = {
        "SYSTEM_ADMIN": set(PERMISSION_ACTIONS),
        "HQ_EXECUTIVE": {"procurement.view", "procurement.approve", "procurement.export", "suppliers.view", "stores.view", "stores.export"},
        "BRANCH_MANAGER": {"procurement.view", "procurement.manage", "procurement.approve", "procurement.export", "suppliers.view", "stores.view", "stores.manage", "stores.issue", "stores.transfer", "stores.export"},
        "SITE_MANAGER": {"procurement.view", "procurement.manage", "suppliers.view", "stores.view", "stores.issue", "stores.transfer"},
        "APPROVER": {"procurement.approve"},
        "AUDITOR": {"procurement.view", "procurement.export", "suppliers.view", "stores.view", "stores.export"},
        "PROCUREMENT_MANAGER": {"procurement.view", "procurement.manage", "procurement.approve", "procurement.export", "suppliers.view", "suppliers.manage", "stores.view", "stores.manage", "stores.issue", "stores.transfer", "stores.adjust", "stores.export"},
        "PROCUREMENT_OFFICER": {"procurement.view", "procurement.manage", "procurement.export", "suppliers.view", "stores.view"},
        "STOREKEEPER": {"procurement.view", "suppliers.view", "stores.view", "stores.manage", "stores.issue", "stores.transfer", "stores.export"},
    }
    for role_code, codes in grants.items():
        role = roles.get(role_code)
        if not role:
            continue
        existing = set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id == role.id)).all())
        for code in codes:
            permission = permissions[code]
            if permission.id not in existing:
                db.add(RolePermission(role_id=role.id, permission_id=permission.id)); existing.add(permission.id)
    for sequence_code, name, prefix in (
        ("SUPPLIER", "Supplier Number", "SUP"), ("REQUISITION", "Procurement Requisition", "PR"),
        ("PURCHASE_ORDER", "Purchase Order", "PO"), ("GOODS_RECEIPT", "Goods Receipt", "GRN"),
        ("STOCK_TRANSFER", "Stock Transfer", "TRF"),
    ):
        if not db.scalar(select(NumberSequence).where(NumberSequence.company_id == company_id, NumberSequence.code == sequence_code)):
            db.add(NumberSequence(company_id=company_id, code=sequence_code, name=name, prefix=prefix, next_number=1, padding=5, reset_period="yearly"))
    for code, name in (("PROCUREMENT_REQUISITION", "Procurement Requisition Approval"), ("PURCHASE_ORDER", "Purchase Order Approval")):
        wf = db.scalar(select(ApprovalWorkflow).where(ApprovalWorkflow.company_id == company_id, ApprovalWorkflow.code == code))
        if not wf:
            wf = ApprovalWorkflow(company_id=company_id, code=code, name=name, module="procurement", description=f"Controlled {name.lower()}", min_amount=Decimal("0"), is_active=True)
            db.add(wf); db.flush()
        if not db.scalar(select(func.count()).select_from(ApprovalStep).where(ApprovalStep.workflow_id == wf.id)):
            branch = roles.get("BRANCH_MANAGER"); hq = roles.get("HQ_EXECUTIVE")
            if not branch or not hq:
                raise HTTPException(status_code=409, detail="Branch Manager and HQ Executive roles are required")
            db.add_all([
                ApprovalStep(workflow_id=wf.id, step_order=1, name="Branch Procurement Review", role_id=branch.id, required_approvals=1, escalation_hours=24),
                ApprovalStep(workflow_id=wf.id, step_order=2, name="Head Office Approval", role_id=hq.id, required_approvals=1, escalation_hours=48),
            ])
    if not db.scalar(select(CompanySetting).where(CompanySetting.company_id == company_id, CompanySetting.key == "procurement_policy")):
        db.add(CompanySetting(company_id=company_id, key="procurement_policy", value=dict(POLICY_DEFAULT), description="Phase 8 procurement and stores governance"))


@router.get("/status")
def phase8_status(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    initialized = db.scalar(select(Permission.id).where(Permission.code == "procurement.view")) is not None
    if initialized:
        require_anywhere(principal, "procurement.view")
    elif not principal.has_company_permission("company.manage"):
        raise HTTPException(status_code=403, detail="Company administration permission required")
    return {"initialized": initialized, "phase": 8, "status": "operational" if initialized else "setup_required"}


@router.post("/bootstrap")
def bootstrap_phase8(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if not principal.has_company_permission("company.manage") and not principal.has_company_permission("procurement.manage"):
        raise HTTPException(status_code=403, detail="Company-level administration is required to initialise Phase 8")
    bootstrap_permissions(db, principal.user.company_id)
    audit(db, principal, "procurement.phase8.bootstrap", "company", principal.user.company_id, detail={"permissions": len(PERMISSION_ACTIONS)})
    commit(db)
    return {"initialized": True, "phase": 8, "message": "Procurement & Stores controls initialised"}


@router.get("/catalog")
def catalog(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_anywhere(principal, "procurement.view")
    cid = principal.user.company_id
    branches = [r for r in db.scalars(select(Branch).where(Branch.company_id == cid, Branch.is_active.is_(True)).order_by(Branch.name)).all() if principal.can("procurement.view", branch_id=r.id)]
    sites = [r for r in db.scalars(select(Site).where(Site.company_id == cid, Site.is_active.is_(True)).order_by(Site.name)).all() if principal.can("procurement.view", branch_id=r.branch_id, site_id=r.id)]
    projects = [r for r in db.scalars(select(Project).where(Project.company_id == cid).order_by(Project.project_number)).all() if principal.can("procurement.view", branch_id=r.branch_id, site_id=r.primary_site_id)]
    locations = [r for r in db.scalars(select(StoreLocation).where(StoreLocation.company_id == cid, StoreLocation.is_active.is_(True)).order_by(StoreLocation.code)).all() if principal.can("stores.view", branch_id=r.branch_id, site_id=r.site_id)]
    suppliers = db.scalars(select(Supplier).where(Supplier.company_id == cid).order_by(Supplier.name)).all() if principal.has_permission_anywhere("suppliers.view") else []
    items = db.scalars(select(StockItem).where(StockItem.company_id == cid, StockItem.is_active.is_(True)).order_by(StockItem.sku)).all() if principal.has_permission_anywhere("stores.view") else []
    documents = db.scalars(select(Document).where(Document.company_id == cid, Document.status == "active").order_by(Document.id.desc()).limit(500)).all()
    return {
        "branches": [row_dict(r) for r in branches], "sites": [row_dict(r) for r in sites],
        "projects": [row_dict(r) for r in projects], "locations": [row_dict(r) for r in locations],
        "suppliers": [row_dict(r) for r in suppliers], "items": [row_dict(r) for r in items],
        "documents": [{"id": r.id, "title": r.title, "branch_id": r.branch_id, "site_id": r.site_id, "category": r.category} for r in documents if r.branch_id is None or principal.can("procurement.view", branch_id=r.branch_id, site_id=r.site_id)],
        "permissions": sorted(code for code in principal.permission_codes if code.startswith(("procurement.", "suppliers.", "stores."))),
    }


@router.get("/policy/current")
def get_policy(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_anywhere(principal, "procurement.view"); return policy(db, principal.user.company_id)


@router.put("/policy/current")
def update_policy(payload: PolicyInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_company(principal, "procurement.manage")
    row = db.scalar(select(CompanySetting).where(CompanySetting.company_id == principal.user.company_id, CompanySetting.key == "procurement_policy"))
    if not row:
        row = CompanySetting(company_id=principal.user.company_id, key="procurement_policy", value={}); db.add(row)
    row.value = {k: json_value(v) for k, v in payload.model_dump().items()}
    audit(db, principal, "procurement.policy.updated", "company_setting", row.id, detail=row.value); commit(db); return row.value


@router.get("/suppliers")
def list_suppliers(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    require_anywhere(principal, "suppliers.view")
    return [row_dict(r) for r in db.scalars(select(Supplier).where(Supplier.company_id == principal.user.company_id).order_by(Supplier.name)).all()]


@router.post("/suppliers", status_code=201)
def create_supplier(payload: SupplierInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_company(principal, "suppliers.manage"); ensure_document(db, principal.user.company_id, payload.compliance_document_id)
    row = Supplier(company_id=principal.user.company_id, supplier_code=issue_reference(db, principal.user.company_id, "SUPPLIER", "SUP"), created_by=principal.user.full_name, approved_by=principal.user.full_name if payload.status == "active" else None, approved_at=utcnow() if payload.status == "active" else None, **payload.model_dump())
    db.add(row); db.flush(); audit(db, principal, "supplier.created", "supplier", row.id, detail={"supplier_code": row.supplier_code, "status": row.status}); commit(db, "Supplier code or details conflict with an existing supplier"); return row_dict(row)


@router.put("/suppliers/{supplier_id:int}")
def update_supplier(supplier_id: int, payload: SupplierInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_company(principal, "suppliers.manage")
    row = db.get(Supplier, supplier_id)
    if not row or row.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Supplier not found")
    ensure_document(db, row.company_id, payload.compliance_document_id)
    for key, value in payload.model_dump().items(): setattr(row, key, value)
    if row.status == "active" and not row.approved_at: row.approved_at = utcnow(); row.approved_by = principal.user.full_name
    audit(db, principal, "supplier.updated", "supplier", row.id, detail={"status": row.status}); commit(db); return row_dict(row)


@router.get("/locations")
def list_locations(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    require_anywhere(principal, "stores.view")
    rows = db.scalars(select(StoreLocation).where(StoreLocation.company_id == principal.user.company_id).order_by(StoreLocation.code)).all()
    return [row_dict(r) for r in rows if principal.can("stores.view", branch_id=r.branch_id, site_id=r.site_id)]


@router.post("/locations", status_code=201)
def create_location(payload: LocationInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    ensure_scope(db, principal.user.company_id, payload.branch_id, payload.site_id); require_scope(principal, "stores.manage", payload.branch_id, payload.site_id)
    if payload.responsible_employee_id:
        emp = db.get(Employee, payload.responsible_employee_id)
        if not emp or emp.company_id != principal.user.company_id or emp.branch_id != payload.branch_id: raise HTTPException(status_code=422, detail="Responsible employee is outside the store branch")
    row = StoreLocation(company_id=principal.user.company_id, created_by=principal.user.full_name, **payload.model_dump())
    db.add(row); db.flush(); audit(db, principal, "store.location.created", "store_location", row.id, branch_id=row.branch_id, site_id=row.site_id); commit(db, "Store location code already exists"); return row_dict(row)


@router.get("/items")
def list_items(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    require_anywhere(principal, "stores.view"); return [row_dict(r) for r in db.scalars(select(StockItem).where(StockItem.company_id == principal.user.company_id).order_by(StockItem.sku)).all()]


@router.post("/items", status_code=201)
def create_item(payload: StockItemInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_anywhere(principal, "stores.manage")
    row = StockItem(company_id=principal.user.company_id, created_by=principal.user.full_name, **payload.model_dump())
    db.add(row); db.flush(); audit(db, principal, "stock.item.created", "stock_item", row.id, detail={"sku": row.sku}); commit(db, "Stock item SKU already exists"); return row_dict(row)


@router.get("/stock")
def stock_register(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    require_anywhere(principal, "stores.view")
    result = []
    for balance in db.scalars(select(StockBalance).where(StockBalance.company_id == principal.user.company_id).order_by(StockBalance.location_id, StockBalance.stock_item_id)).all():
        location = db.get(StoreLocation, balance.location_id); item = db.get(StockItem, balance.stock_item_id)
        if not location or not item or not principal.can("stores.view", branch_id=location.branch_id, site_id=location.site_id): continue
        result.append({**row_dict(balance), "location_code": location.code, "location_name": location.name, "branch_id": location.branch_id, "site_id": location.site_id, "sku": item.sku, "description": item.description, "unit": item.unit, "reorder_level": str(item.reorder_level), "available": str(qty(Decimal(balance.quantity_on_hand) - Decimal(balance.quantity_reserved)))})
    return result


@router.get("/requisitions")
def list_requisitions(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    require_anywhere(principal, "procurement.view")
    rows = db.scalars(select(ProcurementRequisition).where(ProcurementRequisition.company_id == principal.user.company_id).order_by(ProcurementRequisition.created_at.desc())).all()
    return [row_dict(r) for r in rows if principal.can("procurement.view", branch_id=r.branch_id, site_id=r.site_id)]


@router.post("/requisitions", status_code=201)
def create_requisition(payload: RequisitionInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    ensure_scope(db, principal.user.company_id, payload.branch_id, payload.site_id, payload.project_id, payload.cost_centre_id); require_scope(principal, "procurement.manage", payload.branch_id, payload.site_id)
    row = ProcurementRequisition(company_id=principal.user.company_id, requisition_number=issue_reference(db, principal.user.company_id, "REQUISITION", "PR"), requested_by=principal.user.full_name, **payload.model_dump())
    db.add(row); db.flush(); audit(db, principal, "requisition.created", "procurement_requisition", row.id, branch_id=row.branch_id, site_id=row.site_id, detail={"number": row.requisition_number}); commit(db); return row_dict(row)


@router.get("/requisitions/{requisition_id:int}")
def requisition_detail(requisition_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    req = requisition_or_404(db, principal, requisition_id)
    lines = db.scalars(select(ProcurementRequisitionLine).where(ProcurementRequisitionLine.requisition_id == req.id).order_by(ProcurementRequisitionLine.id)).all()
    quotes = db.scalars(select(SupplierQuotation).where(SupplierQuotation.requisition_id == req.id).order_by(SupplierQuotation.total_amount)).all()
    return {"requisition": row_dict(req), "lines": [row_dict(r) for r in lines], "quotations": [row_dict(r) for r in quotes]}


@router.post("/requisitions/{requisition_id:int}/lines", status_code=201)
def add_requisition_line(requisition_id: int, payload: RequisitionLineInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    req = requisition_or_404(db, principal, requisition_id, "procurement.manage")
    if req.status not in {"draft", "rejected"}: raise HTTPException(status_code=409, detail="Only draft/rejected requisitions can be edited")
    if payload.stock_item_id:
        item = db.get(StockItem, payload.stock_item_id)
        if not item or item.company_id != req.company_id or not item.is_active: raise HTTPException(status_code=422, detail="Stock item is invalid")
    values = payload.model_dump(); values["quantity"] = qty(payload.quantity); values["estimated_unit_cost"] = unit_cost(payload.estimated_unit_cost); values["estimated_total"] = money(payload.quantity * payload.estimated_unit_cost)
    row = ProcurementRequisitionLine(company_id=req.company_id, requisition_id=req.id, **values); db.add(row); db.flush(); recalc_requisition(db, req)
    audit(db, principal, "requisition.line.added", "procurement_requisition_line", row.id, branch_id=req.branch_id, site_id=req.site_id, detail={"amount": str(row.estimated_total)}); commit(db); return row_dict(row)


@router.post("/requisitions/{requisition_id:int}/submit")
def submit_requisition(requisition_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    req = requisition_or_404(db, principal, requisition_id, "procurement.manage")
    if req.status not in {"draft", "rejected"}: raise HTTPException(status_code=409, detail="Requisition is not editable for submission")
    recalc_requisition(db, req)
    if not db.scalar(select(func.count()).select_from(ProcurementRequisitionLine).where(ProcurementRequisitionLine.requisition_id == req.id)): raise HTTPException(status_code=409, detail="At least one requisition line is required")
    if req.estimated_total <= 0: raise HTTPException(status_code=409, detail="Requisition estimated total must be positive")
    request = create_approval(db, principal, code="PROCUREMENT_REQUISITION", entity_type="procurement_requisition", entity_id=req.id, title=f"Procurement requisition {req.requisition_number}: {req.title}", branch_id=req.branch_id, site_id=req.site_id, amount=req.estimated_total)
    req.approval_request_id = request.id; req.status = "submitted"
    audit(db, principal, "requisition.submitted", "approval_request", request.id, branch_id=req.branch_id, site_id=req.site_id, detail={"amount": str(req.estimated_total)}); commit(db); return row_dict(request)


@router.post("/requisitions/{requisition_id:int}/quotations", status_code=201)
def add_quotation(requisition_id: int, payload: QuotationInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    req = requisition_or_404(db, principal, requisition_id, "procurement.manage")
    if req.status != "approved": raise HTTPException(status_code=409, detail="Quotations can only be recorded against an approved requisition")
    supplier = db.get(Supplier, payload.supplier_id)
    if not supplier or supplier.company_id != req.company_id or supplier.status != "active": raise HTTPException(status_code=422, detail="Supplier is not active")
    ensure_document(db, req.company_id, payload.document_id)
    req_lines = {r.id: r for r in db.scalars(select(ProcurementRequisitionLine).where(ProcurementRequisitionLine.requisition_id == req.id)).all()}
    if set(line.requisition_line_id for line in payload.lines) != set(req_lines): raise HTTPException(status_code=422, detail="Quotation must price every requisition line exactly once")
    subtotal = Decimal("0")
    row = SupplierQuotation(company_id=req.company_id, requisition_id=req.id, supplier_id=supplier.id, quote_reference=payload.quote_reference, quote_date=payload.quote_date, valid_until=payload.valid_until, delivery_days=payload.delivery_days, tax_amount=money(payload.tax_amount), document_id=payload.document_id, notes=payload.notes, recorded_by=principal.user.full_name, subtotal=Decimal("0"), total_amount=Decimal("0"))
    db.add(row); db.flush()
    for line in payload.lines:
        source = req_lines[line.requisition_line_id]
        if qty(line.quantity) != qty(source.quantity): raise HTTPException(status_code=422, detail=f"Quotation quantity must match requisition line {source.id}")
        total = money(line.quantity * line.unit_price); subtotal += total
        db.add(SupplierQuotationLine(company_id=req.company_id, quotation_id=row.id, requisition_line_id=source.id, stock_item_id=source.stock_item_id, quantity=qty(line.quantity), unit_price=unit_cost(line.unit_price), line_total=total, notes=line.notes))
    row.subtotal = money(subtotal); row.total_amount = money(row.subtotal + row.tax_amount)
    audit(db, principal, "quotation.recorded", "supplier_quotation", row.id, branch_id=req.branch_id, site_id=req.site_id, detail={"supplier_id": supplier.id, "total": str(row.total_amount)}); commit(db, "This supplier quotation reference already exists for the requisition"); return row_dict(row)


@router.get("/requisitions/{requisition_id:int}/quote-comparison")
def quote_comparison(requisition_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    req = requisition_or_404(db, principal, requisition_id)
    quotes = db.scalars(select(SupplierQuotation).where(SupplierQuotation.requisition_id == req.id).order_by(SupplierQuotation.total_amount)).all()
    result = []
    for quote in quotes:
        supplier = db.get(Supplier, quote.supplier_id)
        result.append({**row_dict(quote), "supplier_name": supplier.name if supplier else "", "lines": [row_dict(r) for r in db.scalars(select(SupplierQuotationLine).where(SupplierQuotationLine.quotation_id == quote.id)).all()]})
    return {"requisition": row_dict(req), "policy": policy(db, req.company_id), "quotes": result}


@router.post("/quotations/{quotation_id:int}/select")
def select_quotation(quotation_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    quote = db.get(SupplierQuotation, quotation_id)
    if not quote or quote.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Quotation not found")
    req = requisition_or_404(db, principal, quote.requisition_id, "procurement.manage")
    if req.status != "approved": raise HTTPException(status_code=409, detail="Requisition must remain approved before quote selection")
    if db.scalar(select(func.count()).select_from(PurchaseOrder).where(PurchaseOrder.requisition_id == req.id)):
        raise HTTPException(status_code=409, detail="A purchase order already exists for this requisition")
    cfg = policy(db, req.company_id); received = db.scalar(select(func.count()).select_from(SupplierQuotation).where(SupplierQuotation.requisition_id == req.id, SupplierQuotation.status.in_(["received", "selected", "not_selected"]))) or 0
    if received < int(cfg["minimum_quotes"]) and Decimal(req.estimated_total) > Decimal(str(cfg["low_value_quote_waiver"])):
        raise HTTPException(status_code=409, detail=f"At least {cfg['minimum_quotes']} quotations are required above the low-value waiver")
    for other in db.scalars(select(SupplierQuotation).where(SupplierQuotation.requisition_id == req.id)).all(): other.status = "selected" if other.id == quote.id else "not_selected"
    audit(db, principal, "quotation.selected", "supplier_quotation", quote.id, branch_id=req.branch_id, site_id=req.site_id, detail={"total": str(quote.total_amount)}); commit(db); return row_dict(quote)


@router.get("/purchase-orders")
def list_purchase_orders(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    require_anywhere(principal, "procurement.view")
    rows = db.scalars(select(PurchaseOrder).where(PurchaseOrder.company_id == principal.user.company_id).order_by(PurchaseOrder.created_at.desc())).all()
    return [row_dict(r) for r in rows if principal.can("procurement.view", branch_id=r.branch_id, site_id=r.site_id)]


@router.post("/purchase-orders", status_code=201)
def create_purchase_order(payload: POInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    req = requisition_or_404(db, principal, payload.requisition_id, "procurement.manage")
    if req.status != "approved": raise HTTPException(status_code=409, detail="Purchase order requires an approved requisition")
    if db.scalar(select(func.count()).select_from(PurchaseOrder).where(PurchaseOrder.requisition_id == req.id)): raise HTTPException(status_code=409, detail="A purchase order already exists for this requisition")
    quote = db.get(SupplierQuotation, payload.quotation_id)
    if not quote or quote.requisition_id != req.id or quote.status != "selected": raise HTTPException(status_code=422, detail="Selected quotation is invalid for this requisition")
    supplier = db.get(Supplier, quote.supplier_id)
    if not supplier or supplier.status != "active": raise HTTPException(status_code=422, detail="Selected supplier is not active")
    location = location_or_404(db, principal, payload.delivery_location_id, "stores.view")
    if location.branch_id != req.branch_id or (req.site_id is not None and location.site_id not in {None, req.site_id}): raise HTTPException(status_code=422, detail="Delivery store is outside the requisition branch/site")
    ensure_document(db, req.company_id, payload.document_id)
    po = PurchaseOrder(company_id=req.company_id, branch_id=req.branch_id, site_id=req.site_id, project_id=req.project_id, cost_centre_id=req.cost_centre_id, requisition_id=req.id, quotation_id=quote.id, supplier_id=supplier.id, delivery_location_id=location.id, purchase_order_number=issue_reference(db, req.company_id, "PURCHASE_ORDER", "PO"), order_date=payload.order_date, expected_delivery_date=payload.expected_delivery_date, subtotal=quote.subtotal, tax_amount=quote.tax_amount, total_amount=quote.total_amount, terms=payload.terms, document_id=payload.document_id, created_by=principal.user.full_name)
    db.add(po); db.flush()
    quote_lines = db.scalars(select(SupplierQuotationLine).where(SupplierQuotationLine.quotation_id == quote.id)).all()
    for qline in quote_lines:
        rline = db.get(ProcurementRequisitionLine, qline.requisition_line_id)
        db.add(PurchaseOrderLine(company_id=req.company_id, purchase_order_id=po.id, requisition_line_id=qline.requisition_line_id, stock_item_id=qline.stock_item_id, description=rline.description if rline else "Procurement line", quantity_ordered=qline.quantity, unit=rline.unit if rline else "each", unit_price=qline.unit_price, line_total=qline.line_total))
    audit(db, principal, "purchase_order.created", "purchase_order", po.id, branch_id=po.branch_id, site_id=po.site_id, detail={"number": po.purchase_order_number, "total": str(po.total_amount)}); commit(db); return row_dict(po)


@router.post("/purchase-orders/{purchase_order_id:int}/submit")
def submit_purchase_order(purchase_order_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    po = po_or_404(db, principal, purchase_order_id, "procurement.manage")
    if po.status not in {"draft", "rejected"}: raise HTTPException(status_code=409, detail="Purchase order is not available for submission")
    request = create_approval(db, principal, code="PURCHASE_ORDER", entity_type="purchase_order", entity_id=po.id, title=f"Purchase order {po.purchase_order_number}", branch_id=po.branch_id, site_id=po.site_id, amount=po.total_amount)
    po.approval_request_id = request.id; po.status = "submitted"
    audit(db, principal, "purchase_order.submitted", "approval_request", request.id, branch_id=po.branch_id, site_id=po.site_id, detail={"amount": str(po.total_amount)}); commit(db); return row_dict(request)


@router.post("/purchase-orders/{purchase_order_id:int}/receipts", status_code=201)
def post_goods_receipt(purchase_order_id: int, payload: ReceiptInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    po = po_or_404(db, principal, purchase_order_id, "procurement.manage")
    if po.status not in {"approved", "part_received"}: raise HTTPException(status_code=409, detail="Only approved purchase orders may be received")
    location = location_or_404(db, principal, po.delivery_location_id, "stores.manage")
    ensure_document(db, po.company_id, payload.document_id)
    receipt = GoodsReceipt(company_id=po.company_id, purchase_order_id=po.id, location_id=location.id, goods_receipt_number=issue_reference(db, po.company_id, "GOODS_RECEIPT", "GRN"), receipt_date=payload.receipt_date, delivery_reference=payload.delivery_reference, document_id=payload.document_id, received_by=principal.user.full_name, notes=payload.notes)
    db.add(receipt); db.flush()
    seen: set[int] = set()
    for incoming in payload.lines:
        if incoming.purchase_order_line_id in seen: raise HTTPException(status_code=422, detail="A PO line can only appear once per receipt")
        seen.add(incoming.purchase_order_line_id)
        line = db.get(PurchaseOrderLine, incoming.purchase_order_line_id)
        if not line or line.purchase_order_id != po.id: raise HTTPException(status_code=422, detail="Goods receipt line does not belong to this purchase order")
        received = qty(incoming.quantity_received); accepted = qty(incoming.quantity_accepted); rejected = qty(incoming.quantity_rejected)
        if accepted + rejected != received: raise HTTPException(status_code=422, detail="Accepted plus rejected quantity must equal received quantity")
        outstanding = qty(Decimal(line.quantity_ordered) - Decimal(line.quantity_received))
        if accepted > outstanding: raise HTTPException(status_code=409, detail=f"Accepted quantity exceeds outstanding PO quantity for line {line.id}")
        db.add(GoodsReceiptLine(company_id=po.company_id, goods_receipt_id=receipt.id, purchase_order_line_id=line.id, stock_item_id=line.stock_item_id, quantity_received=received, quantity_accepted=accepted, quantity_rejected=rejected, unit_cost=line.unit_price, notes=incoming.notes))
        line.quantity_received = qty(Decimal(line.quantity_received) + accepted)
        if line.stock_item_id and accepted > 0:
            item = db.get(StockItem, line.stock_item_id)
            if item and item.stock_controlled:
                apply_stock(db, principal, location=location, item=item, delta=accepted, movement_type="receipt", cost=line.unit_price, project_id=po.project_id, site_id=po.site_id, cost_centre_id=po.cost_centre_id, reference_type="goods_receipt", reference_id=receipt.id, reason=f"Accepted against {po.purchase_order_number}")
    lines = db.scalars(select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == po.id)).all()
    po.status = "received" if all(Decimal(r.quantity_received) >= Decimal(r.quantity_ordered) for r in lines) else "part_received"
    audit(db, principal, "goods_receipt.posted", "goods_receipt", receipt.id, branch_id=po.branch_id, site_id=po.site_id, detail={"number": receipt.goods_receipt_number, "po_status": po.status}); commit(db); return {**row_dict(receipt), "purchase_order_status": po.status}


@router.post("/stock/issues", status_code=201)
def issue_stock(payload: StockIssueInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    location = location_or_404(db, principal, payload.location_id, "stores.issue")
    item = db.get(StockItem, payload.stock_item_id)
    if not item or item.company_id != principal.user.company_id or not item.is_active: raise HTTPException(status_code=422, detail="Stock item is invalid")
    ensure_scope(db, principal.user.company_id, location.branch_id, payload.site_id, payload.project_id, payload.cost_centre_id)
    material = None
    if payload.site_material_entry_id:
        material = db.get(SiteMaterialEntry, payload.site_material_entry_id)
        if not material or material.company_id != principal.user.company_id or material.project_id != payload.project_id or material.site_id != payload.site_id: raise HTTPException(status_code=422, detail="Site material evidence does not match the stock issue scope")
    movement = apply_stock(db, principal, location=location, item=item, delta=-qty(payload.quantity), movement_type="issue", project_id=payload.project_id, site_id=payload.site_id, cost_centre_id=payload.cost_centre_id, site_material_entry_id=payload.site_material_entry_id, reference_type="site_material" if material else "manual_issue", reference_id=material.id if material else None, reason=payload.reason)
    audit(db, principal, "stock.issued", "stock_movement", movement.id, branch_id=location.branch_id, site_id=location.site_id, detail={"sku": item.sku, "quantity": str(payload.quantity)}); commit(db); return row_dict(movement)


@router.post("/stock/returns", status_code=201)
def return_stock(payload: StockReturnInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    location = location_or_404(db, principal, payload.location_id, "stores.issue")
    item = db.get(StockItem, payload.stock_item_id)
    if not item or item.company_id != principal.user.company_id: raise HTTPException(status_code=422, detail="Stock item is invalid")
    ensure_scope(db, principal.user.company_id, location.branch_id, payload.site_id, payload.project_id, payload.cost_centre_id)
    movement = apply_stock(db, principal, location=location, item=item, delta=qty(payload.quantity), movement_type="return", cost=payload.unit_cost, project_id=payload.project_id, site_id=payload.site_id, cost_centre_id=payload.cost_centre_id, site_material_entry_id=payload.site_material_entry_id, reference_type="site_return", reason=payload.reason)
    audit(db, principal, "stock.returned", "stock_movement", movement.id, branch_id=location.branch_id, site_id=location.site_id, detail={"sku": item.sku, "quantity": str(payload.quantity)}); commit(db); return row_dict(movement)


@router.post("/stock/adjustments", status_code=201)
def adjust_stock(payload: StockAdjustmentInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    location = location_or_404(db, principal, payload.location_id, "stores.adjust")
    item = db.get(StockItem, payload.stock_item_id)
    if not item or item.company_id != principal.user.company_id: raise HTTPException(status_code=422, detail="Stock item is invalid")
    movement = apply_stock(db, principal, location=location, item=item, delta=payload.quantity_delta, movement_type="adjustment", cost=payload.unit_cost, reason=payload.reason, reference_type="stock_adjustment")
    audit(db, principal, "stock.adjusted", "stock_movement", movement.id, branch_id=location.branch_id, site_id=location.site_id, detail={"sku": item.sku, "delta": str(payload.quantity_delta), "reason": payload.reason}); commit(db); return row_dict(movement)


@router.get("/transfers")
def list_transfers(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    require_anywhere(principal, "stores.view")
    result = []
    for row in db.scalars(select(StockTransfer).where(StockTransfer.company_id == principal.user.company_id).order_by(StockTransfer.requested_at.desc())).all():
        src = db.get(StoreLocation, row.from_location_id); dst = db.get(StoreLocation, row.to_location_id)
        if src and dst and (principal.can("stores.view", branch_id=src.branch_id, site_id=src.site_id) or principal.can("stores.view", branch_id=dst.branch_id, site_id=dst.site_id)):
            result.append(row_dict(row))
    return result


@router.post("/transfers", status_code=201)
def create_transfer(payload: TransferInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if payload.from_location_id == payload.to_location_id: raise HTTPException(status_code=422, detail="Source and destination stores must differ")
    src = location_or_404(db, principal, payload.from_location_id, "stores.transfer"); dst = location_or_404(db, principal, payload.to_location_id, "stores.transfer")
    seen: set[int] = set()
    transfer = StockTransfer(company_id=principal.user.company_id, from_location_id=src.id, to_location_id=dst.id, transfer_number=issue_reference(db, principal.user.company_id, "STOCK_TRANSFER", "TRF"), requested_by=principal.user.full_name, notes=payload.notes)
    db.add(transfer); db.flush()
    for line in payload.lines:
        if line.stock_item_id in seen: raise HTTPException(status_code=422, detail="Stock item may only appear once per transfer")
        seen.add(line.stock_item_id); item = db.get(StockItem, line.stock_item_id)
        if not item or item.company_id != principal.user.company_id: raise HTTPException(status_code=422, detail="Transfer stock item is invalid")
        db.add(StockTransferLine(company_id=principal.user.company_id, transfer_id=transfer.id, stock_item_id=item.id, quantity_requested=qty(line.quantity)))
    audit(db, principal, "stock.transfer.created", "stock_transfer", transfer.id, branch_id=src.branch_id, site_id=src.site_id, detail={"number": transfer.transfer_number, "to_location_id": dst.id}); commit(db); return row_dict(transfer)


@router.post("/transfers/{transfer_id:int}/ship")
def ship_transfer(transfer_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    transfer = db.get(StockTransfer, transfer_id)
    if not transfer or transfer.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Stock transfer not found")
    if transfer.status != "draft": raise HTTPException(status_code=409, detail="Only draft transfers can be shipped")
    src = location_or_404(db, principal, transfer.from_location_id, "stores.transfer")
    for line in db.scalars(select(StockTransferLine).where(StockTransferLine.transfer_id == transfer.id)).all():
        item = db.get(StockItem, line.stock_item_id); balance = balance_for(db, transfer.company_id, src.id, item.id)
        cost = Decimal(balance.average_unit_cost or 0); requested = qty(line.quantity_requested)
        apply_stock(db, principal, location=src, item=item, delta=-requested, movement_type="transfer_out", cost=cost, reference_type="stock_transfer", reference_id=transfer.id, reason=f"Transfer {transfer.transfer_number}")
        line.quantity_shipped = requested
    transfer.status = "in_transit"; transfer.shipped_by = principal.user.full_name; transfer.shipped_at = utcnow()
    audit(db, principal, "stock.transfer.shipped", "stock_transfer", transfer.id, branch_id=src.branch_id, site_id=src.site_id); commit(db); return row_dict(transfer)


@router.post("/transfers/{transfer_id:int}/receive")
def receive_transfer(transfer_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    transfer = db.get(StockTransfer, transfer_id)
    if not transfer or transfer.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Stock transfer not found")
    if transfer.status != "in_transit": raise HTTPException(status_code=409, detail="Only in-transit transfers can be received")
    dst = location_or_404(db, principal, transfer.to_location_id, "stores.transfer")
    for line in db.scalars(select(StockTransferLine).where(StockTransferLine.transfer_id == transfer.id)).all():
        item = db.get(StockItem, line.stock_item_id)
        source_move = db.scalar(select(StockMovement).where(StockMovement.reference_type == "stock_transfer", StockMovement.reference_id == str(transfer.id), StockMovement.stock_item_id == item.id, StockMovement.movement_type == "transfer_out").order_by(StockMovement.id.desc()).limit(1))
        cost = Decimal(source_move.unit_cost if source_move else item.default_unit_cost or 0); shipped = qty(line.quantity_shipped)
        apply_stock(db, principal, location=dst, item=item, delta=shipped, movement_type="transfer_in", cost=cost, reference_type="stock_transfer", reference_id=transfer.id, reason=f"Transfer {transfer.transfer_number}")
        line.quantity_received = shipped
    transfer.status = "received"; transfer.received_by = principal.user.full_name; transfer.received_at = utcnow()
    audit(db, principal, "stock.transfer.received", "stock_transfer", transfer.id, branch_id=dst.branch_id, site_id=dst.site_id); commit(db); return row_dict(transfer)


@router.post("/approvals/{request_id:int}/decision")
def decide_approval(request_id: int, payload: ApprovalDecisionInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    request = db.get(ApprovalRequest, request_id)
    if not request or request.company_id != principal.user.company_id or request.entity_type not in {"procurement_requisition", "purchase_order"}: raise HTTPException(status_code=404, detail="Procurement approval request not found")
    if request.entity_type == "procurement_requisition":
        entity = db.get(ProcurementRequisition, int(request.entity_id))
    else:
        entity = db.get(PurchaseOrder, int(request.entity_id))
    if not entity: raise HTTPException(status_code=404, detail="Procurement approval entity not found")
    require_scope(principal, "procurement.approve", entity.branch_id, entity.site_id)
    if request.status != "pending": raise HTTPException(status_code=409, detail=f"Approval request is already {request.status}")
    step = db.scalar(select(ApprovalStep).where(ApprovalStep.workflow_id == request.workflow_id, ApprovalStep.step_order == request.current_step_order))
    if not step or not assignment_authorised(db, principal, step.role_id, entity.branch_id, entity.site_id): raise HTTPException(status_code=403, detail="Your active role assignment is not authorised for this approval step")
    if request.requested_by == principal.user.full_name and not allow_self_approval(db, principal.user.company_id): raise HTTPException(status_code=422, detail="Self-approval is disabled by company approval policy")
    db.add(ApprovalAction(request_id=request.id, step_order=step.step_order, role_id=step.role_id, actor_name=principal.user.full_name, action=payload.decision, comment=payload.comment))
    if payload.decision == "reject":
        request.status = "rejected"; request.completed_at = utcnow()
    else:
        count = (db.scalar(select(func.count()).select_from(ApprovalAction).where(ApprovalAction.request_id == request.id, ApprovalAction.step_order == step.step_order, ApprovalAction.action == "approve")) or 0) + 1
        if count >= step.required_approvals:
            next_step = db.scalar(select(ApprovalStep).where(ApprovalStep.workflow_id == request.workflow_id, ApprovalStep.step_order > step.step_order).order_by(ApprovalStep.step_order).limit(1))
            if next_step: request.current_step_order = next_step.step_order
            else: request.status = "approved"; request.completed_at = utcnow()
    if request.entity_type == "procurement_requisition":
        if request.status == "approved": entity.status = "approved"
        elif request.status == "rejected": entity.status = "rejected"
    else:
        if request.status == "approved": entity.status = "approved"; entity.approved_at = utcnow(); req = db.get(ProcurementRequisition, entity.requisition_id); req.status = "ordered" if req else entity.status
        elif request.status == "rejected": entity.status = "rejected"
    audit(db, principal, f"procurement.approval.{payload.decision}", "approval_request", request.id, branch_id=entity.branch_id, site_id=entity.site_id, detail={"entity_type": request.entity_type, "status": request.status, "step": step.step_order}); commit(db); return row_dict(request)


@router.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_anywhere(principal, "procurement.view")
    cid = principal.user.company_id
    reqs = [r for r in db.scalars(select(ProcurementRequisition).where(ProcurementRequisition.company_id == cid)).all() if principal.can("procurement.view", branch_id=r.branch_id, site_id=r.site_id)]
    pos = [r for r in db.scalars(select(PurchaseOrder).where(PurchaseOrder.company_id == cid)).all() if principal.can("procurement.view", branch_id=r.branch_id, site_id=r.site_id)]
    stock_value = Decimal("0"); low = 0
    for bal in db.scalars(select(StockBalance).where(StockBalance.company_id == cid)).all():
        loc = db.get(StoreLocation, bal.location_id); item = db.get(StockItem, bal.stock_item_id)
        if loc and item and principal.can("stores.view", branch_id=loc.branch_id, site_id=loc.site_id):
            stock_value += Decimal(bal.quantity_on_hand) * Decimal(bal.average_unit_cost)
            if item.reorder_level > 0 and Decimal(bal.quantity_on_hand) <= Decimal(item.reorder_level): low += 1
    commitments = sum((Decimal(po.total_amount) for po in pos if po.status in {"approved", "part_received"}), Decimal("0"))
    return {"requisitions": len(reqs), "requisitions_pending": sum(r.status == "submitted" for r in reqs), "purchase_orders": len(pos), "po_pending": sum(r.status == "submitted" for r in pos), "open_commitments": str(money(commitments)), "stock_value": str(money(stock_value)), "low_stock_items": low}


@router.get("/dashboard/alerts")
def dashboard_alerts(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    require_anywhere(principal, "procurement.view"); cid = principal.user.company_id; result: list[dict[str, Any]] = []
    today = date.today()
    for req in db.scalars(select(ProcurementRequisition).where(ProcurementRequisition.company_id == cid, ProcurementRequisition.status.in_(["draft", "submitted", "approved"]))).all():
        if principal.can("procurement.view", branch_id=req.branch_id, site_id=req.site_id) and req.required_by <= today:
            result.append({"type": "requisition_due", "severity": "critical" if req.required_by < today else "warning", "reference": req.requisition_number, "message": f"Required by {req.required_by.isoformat()}"})
    for po in db.scalars(select(PurchaseOrder).where(PurchaseOrder.company_id == cid, PurchaseOrder.status.in_(["approved", "part_received"]), PurchaseOrder.expected_delivery_date.is_not(None))).all():
        if po.expected_delivery_date and po.expected_delivery_date < today and principal.can("procurement.view", branch_id=po.branch_id, site_id=po.site_id): result.append({"type": "po_overdue", "severity": "critical", "reference": po.purchase_order_number, "message": f"Expected delivery {po.expected_delivery_date.isoformat()}"})
    if bool(policy(db, cid).get("reorder_alert_enabled", True)):
        for bal in db.scalars(select(StockBalance).where(StockBalance.company_id == cid)).all():
            loc = db.get(StoreLocation, bal.location_id); item = db.get(StockItem, bal.stock_item_id)
            if loc and item and item.reorder_level > 0 and Decimal(bal.quantity_on_hand) <= Decimal(item.reorder_level) and principal.can("stores.view", branch_id=loc.branch_id, site_id=loc.site_id): result.append({"type": "low_stock", "severity": "warning", "reference": item.sku, "message": f"{loc.code}: {bal.quantity_on_hand} {item.unit} on hand; reorder at {item.reorder_level}"})
    return result


@router.get("/exports/stock.csv")
def export_stock(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> StreamingResponse:
    require_anywhere(principal, "stores.export"); output = io.StringIO(); writer = csv.writer(output); writer.writerow(["Location", "Branch ID", "Site ID", "SKU", "Description", "Unit", "On Hand", "Reserved", "Average Cost", "Stock Value", "Reorder Level"])
    for bal in db.scalars(select(StockBalance).where(StockBalance.company_id == principal.user.company_id).order_by(StockBalance.location_id, StockBalance.stock_item_id)).all():
        loc = db.get(StoreLocation, bal.location_id); item = db.get(StockItem, bal.stock_item_id)
        if not loc or not item or not principal.can("stores.export", branch_id=loc.branch_id, site_id=loc.site_id): continue
        writer.writerow([loc.code, loc.branch_id, loc.site_id or "", item.sku, item.description, item.unit, bal.quantity_on_hand, bal.quantity_reserved, bal.average_unit_cost, money(Decimal(bal.quantity_on_hand) * Decimal(bal.average_unit_cost)), item.reorder_level])
    return StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=buildtrack-stock-register.csv"})


@router.get("/exports/purchase-orders.csv")
def export_purchase_orders(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> StreamingResponse:
    require_anywhere(principal, "procurement.export"); output = io.StringIO(); writer = csv.writer(output); writer.writerow(["PO Number", "Supplier", "Branch ID", "Site ID", "Project ID", "Order Date", "Expected Delivery", "Status", "Total", "Requisition"])
    for po in db.scalars(select(PurchaseOrder).where(PurchaseOrder.company_id == principal.user.company_id).order_by(PurchaseOrder.order_date.desc())).all():
        if not principal.can("procurement.export", branch_id=po.branch_id, site_id=po.site_id): continue
        supplier = db.get(Supplier, po.supplier_id); req = db.get(ProcurementRequisition, po.requisition_id)
        writer.writerow([po.purchase_order_number, supplier.name if supplier else "", po.branch_id, po.site_id or "", po.project_id or "", po.order_date, po.expected_delivery_date or "", po.status, po.total_amount, req.requisition_number if req else ""])
    return StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=buildtrack-purchase-orders.csv"})


@router.get("/audit/events")
def audit_events(db: Session = Depends(get_db), principal: Principal = Depends(current_principal), limit: int = Query(default=250, ge=1, le=1000)) -> list[dict[str, Any]]:
    require_anywhere(principal, "procurement.view")
    rows = db.scalars(select(ProcurementAuditEvent).where(ProcurementAuditEvent.company_id == principal.user.company_id).order_by(ProcurementAuditEvent.occurred_at.desc()).limit(limit)).all()
    return [row_dict(r) for r in rows if r.branch_id is None or principal.can("procurement.view", branch_id=r.branch_id, site_id=r.site_id)]
