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

from app.api.v1.procurement import allow_self_approval, assignment_authorised, commit, ensure_document, issue_reference, money, row_dict, utcnow
from app.db.session import get_db
from app.models import (
    ApprovalAction, ApprovalRequest, ApprovalStep, ApprovalWorkflow, Branch, ChartOfAccount,
    ClientContract, ClientInvoice, CompanySetting, CostCentre, FinanceAuditEvent, FinanceJournal,
    FinanceJournalLine, FinancialPeriod, NumberSequence, Permission, Project, PurchaseOrder,
    Role, RolePermission, Site, Supplier, SupplierInvoice, SupplierPayment,
)
from app.security.access import Principal, current_principal


router = APIRouter(prefix="/finance", tags=["Phase 18 - Finance & Cash Control"])

PERMISSIONS = {
    "finance.view": ("finance", "view", "View financial periods, journals, payables and cash controls"),
    "finance.manage": ("finance", "manage", "Prepare finance records, journals and supplier invoices"),
    "finance.approve": ("finance", "approve", "Independently approve finance records"),
    "finance.post": ("finance", "post", "Post independently approved journals and close financial periods"),
    "finance.pay": ("finance", "pay", "Record supplied supplier-payment evidence after approval"),
    "finance.export": ("finance", "export", "Export controlled finance registers"),
}

POLICY_DEFAULT = {
    "require_invoice_evidence": True,
    "require_payment_evidence": True,
    "require_journal_evidence": True,
    "minimum_journal_lines": 2,
}

DEFAULT_ACCOUNTS = (
    ("1000", "Cash and bank", "asset"),
    ("1100", "Accounts receivable", "asset"),
    ("1200", "Retention receivable", "asset"),
    ("1300", "Inventory and materials", "asset"),
    ("2000", "Accounts payable", "liability"),
    ("2100", "Retention payable", "liability"),
    ("3000", "Equity", "equity"),
    ("4000", "Contract revenue", "revenue"),
    ("5000", "Direct project cost", "expense"),
    ("6000", "Overheads", "expense"),
)


def anywhere(principal: Principal, permission: str) -> None:
    if not principal.has_permission_anywhere(permission):
        raise HTTPException(status_code=403, detail=f"Permission required: {permission}")


def scope(principal: Principal, permission: str, branch_id: int, site_id: int | None = None) -> None:
    if not principal.can(permission, branch_id=branch_id, site_id=site_id):
        raise HTTPException(status_code=403, detail=f"Permission required in this branch/site: {permission}")


def finance_policy(db: Session, company_id: int) -> dict[str, Any]:
    setting = db.scalar(select(CompanySetting).where(CompanySetting.company_id == company_id, CompanySetting.key == "finance_policy"))
    return {**POLICY_DEFAULT, **(setting.value if setting and isinstance(setting.value, dict) else {})}


def audit(db: Session, principal: Principal, action: str, entity: Any, *, branch_id: int | None, site_id: int | None = None, project_id: int | None = None, detail: dict[str, Any] | None = None) -> None:
    db.add(FinanceAuditEvent(company_id=principal.user.company_id, branch_id=branch_id, site_id=site_id, project_id=project_id, actor=principal.user.full_name, action=action, entity_type=entity.__tablename__, entity_id=str(entity.id), detail=detail or {}))


def period_or_404(db: Session, principal: Principal, period_id: int) -> FinancialPeriod:
    row = db.get(FinancialPeriod, period_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Financial period not found")
    return row


def require_open_period(period: FinancialPeriod, transaction_date: date) -> None:
    if period.status != "open":
        raise HTTPException(status_code=409, detail="The selected financial period is closed")
    if transaction_date < period.start_date or transaction_date > period.end_date:
        raise HTTPException(status_code=422, detail="Transaction date is outside the selected financial period")


def journal_or_404(db: Session, principal: Principal, journal_id: int, permission: str = "finance.view") -> FinanceJournal:
    row = db.get(FinanceJournal, journal_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Finance journal not found")
    scope(principal, permission, row.branch_id, row.site_id)
    return row


def invoice_or_404(db: Session, principal: Principal, invoice_id: int, permission: str = "finance.view") -> SupplierInvoice:
    row = db.get(SupplierInvoice, invoice_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Supplier invoice not found")
    scope(principal, permission, row.branch_id, row.site_id)
    return row


def payment_or_404(db: Session, principal: Principal, payment_id: int, permission: str = "finance.view") -> SupplierPayment:
    row = db.get(SupplierPayment, payment_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Supplier payment request not found")
    scope(principal, permission, row.branch_id, row.site_id)
    return row


def account_or_404(db: Session, principal: Principal, account_id: int) -> ChartOfAccount:
    row = db.get(ChartOfAccount, account_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=422, detail="Chart-of-account record does not belong to this company")
    if not row.is_active:
        raise HTTPException(status_code=409, detail="Inactive chart-of-account records cannot be used")
    return row


def validate_scope_data(db: Session, principal: Principal, *, branch_id: int, site_id: int | None, project_id: int | None, cost_centre_id: int | None) -> None:
    branch = db.get(Branch, branch_id)
    if not branch or branch.company_id != principal.user.company_id:
        raise HTTPException(status_code=422, detail="Branch does not belong to this company")
    if site_id is not None:
        site = db.get(Site, site_id)
        if not site or site.company_id != principal.user.company_id or site.branch_id != branch_id:
            raise HTTPException(status_code=422, detail="Site does not belong to the selected branch")
    if project_id is not None:
        project = db.get(Project, project_id)
        if not project or project.company_id != principal.user.company_id or project.branch_id != branch_id:
            raise HTTPException(status_code=422, detail="Project does not belong to the selected branch")
        if site_id is not None and project.primary_site_id != site_id:
            raise HTTPException(status_code=422, detail="Project is outside the selected site")
    if cost_centre_id is not None:
        centre = db.get(CostCentre, cost_centre_id)
        if not centre or centre.company_id != principal.user.company_id:
            raise HTTPException(status_code=422, detail="Cost centre does not belong to this company")
        if centre.branch_id is not None and centre.branch_id != branch_id:
            raise HTTPException(status_code=422, detail="Cost centre is outside the selected branch")
        if site_id is not None and centre.site_id is not None and centre.site_id != site_id:
            raise HTTPException(status_code=422, detail="Cost centre is outside the selected site")


def journal_totals(db: Session, journal_id: int) -> tuple[Decimal, Decimal, int]:
    lines = db.scalars(select(FinanceJournalLine).where(FinanceJournalLine.journal_id == journal_id).order_by(FinanceJournalLine.line_number)).all()
    debit = money(sum((Decimal(line.debit) for line in lines), Decimal("0")))
    credit = money(sum((Decimal(line.credit) for line in lines), Decimal("0")))
    return debit, credit, len(lines)


def journal_payload(db: Session, row: FinanceJournal) -> dict[str, Any]:
    payload = row_dict(row)
    debit, credit, count = journal_totals(db, row.id)
    period = db.get(FinancialPeriod, row.period_id)
    payload.update({"debit_total": str(debit), "credit_total": str(credit), "line_count": count, "period_code": period.period_code if period else ""})
    return payload


def invoice_payload(db: Session, row: SupplierInvoice) -> dict[str, Any]:
    payload = row_dict(row)
    supplier = db.get(Supplier, row.supplier_id)
    purchase_order = db.get(PurchaseOrder, row.purchase_order_id) if row.purchase_order_id else None
    payload.update({"supplier_name": supplier.name if supplier else "", "supplier_code": supplier.supplier_code if supplier else "", "purchase_order_number": purchase_order.purchase_order_number if purchase_order else "", "outstanding_amount": str(money(Decimal(row.amount) - Decimal(row.paid_amount)))})
    return payload


def workflow(db: Session, company_id: int, code: str) -> ApprovalWorkflow:
    row = db.scalar(select(ApprovalWorkflow).where(ApprovalWorkflow.company_id == company_id, ApprovalWorkflow.code == code, ApprovalWorkflow.is_active.is_(True)))
    if not row or not db.scalar(select(func.count()).select_from(ApprovalStep).where(ApprovalStep.workflow_id == row.id)):
        raise HTTPException(status_code=409, detail=f"Finance approval workflow {code} is not configured")
    return row


def approval_request(db: Session, principal: Principal, *, code: str, entity_type: str, entity_id: int, title: str, amount: Decimal, branch_id: int, site_id: int | None) -> ApprovalRequest:
    selected = workflow(db, principal.user.company_id, code)
    row = ApprovalRequest(company_id=principal.user.company_id, workflow_id=selected.id, branch_id=branch_id, site_id=site_id, entity_type=entity_type, entity_id=str(entity_id), reference=issue_reference(db, principal.user.company_id, "FINANCE_APPROVAL", "FAP"), title=title, amount=money(amount), status="pending", current_step_order=1, requested_by=principal.user.full_name)
    db.add(row)
    db.flush()
    return row


def bootstrap_data(db: Session, company_id: int) -> None:
    permissions: dict[str, Permission] = {}
    for code, (module, action, description) in PERMISSIONS.items():
        row = db.scalar(select(Permission).where(Permission.code == code))
        if not row:
            row = Permission(code=code, module=module, action=action, description=description)
            db.add(row)
            db.flush()
        permissions[code] = row
    roles = {row.code: row for row in db.scalars(select(Role).where(Role.company_id == company_id)).all()}
    for code, name, scope_level in (("FINANCE_MANAGER", "Finance Manager", "company"), ("FINANCE_OFFICER", "Finance Officer", "branch"), ("FINANCE_REVIEWER", "Finance Reviewer", "company")):
        if code not in roles:
            row = Role(company_id=company_id, code=code, name=name, scope_level=scope_level, description=f"Phase 18 {name.lower()} role", is_system=True, is_active=True)
            db.add(row)
            db.flush()
            roles[code] = row
    grants = {
        "SYSTEM_ADMIN": set(PERMISSIONS), "HQ_EXECUTIVE": set(PERMISSIONS),
        "BRANCH_MANAGER": {"finance.view", "finance.manage", "finance.approve", "finance.export"},
        "PROJECT_MANAGER": {"finance.view"}, "SITE_MANAGER": {"finance.view"},
        "APPROVER": {"finance.approve"}, "AUDITOR": {"finance.view", "finance.export"},
        "FINANCE_MANAGER": set(PERMISSIONS), "FINANCE_OFFICER": {"finance.view", "finance.manage"},
        "FINANCE_REVIEWER": {"finance.view", "finance.approve", "finance.post", "finance.pay", "finance.export"},
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
    for code, name, prefix in (("FINANCE_JOURNAL", "Finance Journal", "FJN"), ("SUPPLIER_INVOICE", "Supplier Invoice", "SIN"), ("SUPPLIER_PAYMENT", "Supplier Payment", "SPY"), ("FINANCE_APPROVAL", "Finance Approval", "FAP")):
        if not db.scalar(select(NumberSequence).where(NumberSequence.company_id == company_id, NumberSequence.code == code)):
            db.add(NumberSequence(company_id=company_id, code=code, name=name, prefix=prefix, next_number=1, padding=5, reset_period="yearly"))
    for account_code, name, account_type in DEFAULT_ACCOUNTS:
        if not db.scalar(select(ChartOfAccount).where(ChartOfAccount.company_id == company_id, ChartOfAccount.account_code == account_code)):
            db.add(ChartOfAccount(company_id=company_id, account_code=account_code, name=name, account_type=account_type, is_system=True, is_active=True, created_by="finance-bootstrap"))
    branch, hq = roles.get("BRANCH_MANAGER"), roles.get("HQ_EXECUTIVE")
    if not branch or not hq:
        raise HTTPException(status_code=409, detail="Branch Manager and HQ Executive roles are required for Phase 18")
    for code, name in (("FINANCE_JOURNAL", "Finance Journal Approval"), ("SUPPLIER_INVOICE", "Supplier Invoice Approval"), ("SUPPLIER_PAYMENT", "Supplier Payment Approval")):
        row = db.scalar(select(ApprovalWorkflow).where(ApprovalWorkflow.company_id == company_id, ApprovalWorkflow.code == code))
        if not row:
            row = ApprovalWorkflow(company_id=company_id, code=code, name=name, module="finance", description=f"Controlled {name.lower()}", min_amount=Decimal("0"), is_active=True)
            db.add(row)
            db.flush()
        if not db.scalar(select(func.count()).select_from(ApprovalStep).where(ApprovalStep.workflow_id == row.id)):
            db.add_all([ApprovalStep(workflow_id=row.id, step_order=1, name="Branch Finance Review", role_id=branch.id, required_approvals=1, escalation_hours=24), ApprovalStep(workflow_id=row.id, step_order=2, name="Head Office Finance Approval", role_id=hq.id, required_approvals=1, escalation_hours=48)])
    if not db.scalar(select(CompanySetting).where(CompanySetting.company_id == company_id, CompanySetting.key == "finance_policy")):
        db.add(CompanySetting(company_id=company_id, key="finance_policy", value=dict(POLICY_DEFAULT), description="Phase 18 finance governance"))


class PeriodInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period_code: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=2, max_length=160)
    start_date: date
    end_date: date
    notes: str | None = Field(default=None, max_length=2000)


class AccountInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_code: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=2, max_length=180)
    account_type: Literal["asset", "liability", "equity", "revenue", "expense"]
    parent_account_id: int | None = None
    notes: str | None = Field(default=None, max_length=2000)


class JournalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch_id: int
    site_id: int | None = None
    project_id: int | None = None
    cost_centre_id: int | None = None
    period_id: int
    journal_date: date
    description: str = Field(min_length=2, max_length=300)
    source_type: str | None = Field(default=None, max_length=64)
    source_reference: str | None = Field(default=None, max_length=160)
    supporting_document_id: int | None = None
    notes: str | None = Field(default=None, max_length=4000)


class JournalLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: int
    description: str | None = Field(default=None, max_length=300)
    debit: Decimal = Field(default=Decimal("0"), ge=0)
    credit: Decimal = Field(default=Decimal("0"), ge=0)


class SupplierInvoiceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch_id: int
    site_id: int | None = None
    project_id: int | None = None
    cost_centre_id: int | None = None
    supplier_id: int
    purchase_order_id: int | None = None
    supplier_invoice_reference: str = Field(min_length=2, max_length=160)
    invoice_date: date
    due_date: date | None = None
    amount: Decimal = Field(gt=0)
    invoice_document_id: int | None = None
    notes: str | None = Field(default=None, max_length=4000)


class PaymentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requested_date: date
    amount: Decimal = Field(gt=0)
    payment_reference: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=4000)


class PaymentRecordInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payment_document_id: int | None = None
    payment_reference: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=4000)


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]
    comment: str | None = Field(default=None, max_length=2000)


@router.post("/bootstrap")
def bootstrap(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if not principal.has_company_permission("company.manage") and not principal.has_company_permission("finance.manage"):
        raise HTTPException(status_code=403, detail="Company administration is required to initialise Phase 18")
    bootstrap_data(db, principal.user.company_id)
    commit(db)
    return {"phase": 18, "status": "ready"}


@router.get("/catalog")
def catalog(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    anywhere(principal, "finance.view")
    branches = [row_dict(row) for row in db.scalars(select(Branch).where(Branch.company_id == principal.user.company_id, Branch.is_active.is_(True)).order_by(Branch.name)).all() if principal.can("finance.view", branch_id=row.id)]
    suppliers = [row_dict(row) for row in db.scalars(select(Supplier).where(Supplier.company_id == principal.user.company_id, Supplier.status == "active").order_by(Supplier.name)).all()]
    projects = [row_dict(row) for row in db.scalars(select(Project).where(Project.company_id == principal.user.company_id, Project.status != "closed").order_by(Project.name)).all() if principal.can("finance.view", branch_id=row.branch_id, site_id=row.primary_site_id)]
    purchase_orders = [row_dict(row) for row in db.scalars(select(PurchaseOrder).where(PurchaseOrder.company_id == principal.user.company_id, PurchaseOrder.status.in_(("approved", "issued", "part_received", "received"))).order_by(PurchaseOrder.id.desc())).all() if principal.can("finance.view", branch_id=row.branch_id, site_id=row.site_id)]
    return {"branches": branches, "suppliers": suppliers, "projects": projects, "purchase_orders": purchase_orders, "permissions": [code for code in PERMISSIONS if principal.has_permission_anywhere(code)]}


@router.get("/periods")
def periods(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    anywhere(principal, "finance.view")
    return [row_dict(row) for row in db.scalars(select(FinancialPeriod).where(FinancialPeriod.company_id == principal.user.company_id).order_by(FinancialPeriod.start_date.desc())).all()]


@router.post("/periods", status_code=201)
def create_period(payload: PeriodInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if not principal.has_company_permission("finance.manage"):
        raise HTTPException(status_code=403, detail="Company-level finance.manage permission is required to create a financial period")
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=422, detail="Financial period end date cannot precede start date")
    overlap = db.scalar(select(FinancialPeriod).where(FinancialPeriod.company_id == principal.user.company_id, FinancialPeriod.start_date <= payload.end_date, FinancialPeriod.end_date >= payload.start_date))
    if overlap:
        raise HTTPException(status_code=409, detail="Financial periods cannot overlap")
    row = FinancialPeriod(company_id=principal.user.company_id, period_code=payload.period_code.upper().strip(), name=payload.name.strip(), start_date=payload.start_date, end_date=payload.end_date, status="open", notes=payload.notes, created_by=principal.user.full_name)
    db.add(row)
    db.flush()
    audit(db, principal, "finance.period.created", row, branch_id=None, detail={"period_code": row.period_code})
    commit(db)
    return row_dict(row)


@router.post("/periods/{period_id:int}/close")
def close_period(period_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if not principal.has_company_permission("finance.post"):
        raise HTTPException(status_code=403, detail="Company-level finance.post permission is required to close a financial period")
    row = period_or_404(db, principal, period_id)
    if row.status != "open":
        raise HTTPException(status_code=409, detail="Only open financial periods can be closed")
    pending = db.scalar(select(func.count()).select_from(FinanceJournal).where(FinanceJournal.period_id == row.id, FinanceJournal.status.in_(("draft", "submitted", "approved", "rejected")))) or 0
    if pending:
        raise HTTPException(status_code=409, detail="All finance journals in this period must be posted before the period can close")
    row.status, row.closed_by, row.closed_at = "closed", principal.user.full_name, utcnow()
    audit(db, principal, "finance.period.closed", row, branch_id=None)
    commit(db)
    return row_dict(row)


@router.get("/accounts")
def accounts(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    anywhere(principal, "finance.view")
    return [row_dict(row) for row in db.scalars(select(ChartOfAccount).where(ChartOfAccount.company_id == principal.user.company_id).order_by(ChartOfAccount.account_code)).all()]


@router.post("/accounts", status_code=201)
def create_account(payload: AccountInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if not principal.has_company_permission("finance.manage"):
        raise HTTPException(status_code=403, detail="Company-level finance.manage permission is required to add a chart account")
    parent = account_or_404(db, principal, payload.parent_account_id) if payload.parent_account_id else None
    if parent and parent.account_type != payload.account_type:
        raise HTTPException(status_code=422, detail="A chart account must use the same type as its parent account")
    row = ChartOfAccount(company_id=principal.user.company_id, account_code=payload.account_code.upper().strip(), name=payload.name.strip(), account_type=payload.account_type, parent_account_id=payload.parent_account_id, is_system=False, is_active=True, notes=payload.notes, created_by=principal.user.full_name)
    db.add(row)
    db.flush()
    audit(db, principal, "finance.account.created", row, branch_id=None, detail={"account_code": row.account_code})
    commit(db)
    return row_dict(row)


@router.get("/journals")
def journals(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    anywhere(principal, "finance.view")
    rows = db.scalars(select(FinanceJournal).where(FinanceJournal.company_id == principal.user.company_id).order_by(FinanceJournal.journal_date.desc(), FinanceJournal.id.desc())).all()
    return [journal_payload(db, row) for row in rows if principal.can("finance.view", branch_id=row.branch_id, site_id=row.site_id)]


@router.post("/journals", status_code=201)
def create_journal(payload: JournalInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    validate_scope_data(db, principal, branch_id=payload.branch_id, site_id=payload.site_id, project_id=payload.project_id, cost_centre_id=payload.cost_centre_id)
    scope(principal, "finance.manage", payload.branch_id, payload.site_id)
    period = period_or_404(db, principal, payload.period_id)
    require_open_period(period, payload.journal_date)
    ensure_document(db, principal.user.company_id, payload.supporting_document_id)
    row = FinanceJournal(company_id=principal.user.company_id, branch_id=payload.branch_id, site_id=payload.site_id, project_id=payload.project_id, cost_centre_id=payload.cost_centre_id, period_id=period.id, journal_number=issue_reference(db, principal.user.company_id, "FINANCE_JOURNAL", "FJN"), journal_date=payload.journal_date, description=payload.description, source_type=payload.source_type, source_reference=payload.source_reference, supporting_document_id=payload.supporting_document_id, status="draft", notes=payload.notes, prepared_by=principal.user.full_name)
    db.add(row)
    db.flush()
    audit(db, principal, "finance.journal.created", row, branch_id=row.branch_id, site_id=row.site_id, project_id=row.project_id)
    commit(db)
    return journal_payload(db, row)


@router.get("/journals/{journal_id:int}")
def journal_detail(journal_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = journal_or_404(db, principal, journal_id)
    payload = journal_payload(db, row)
    lines = []
    for line in db.scalars(select(FinanceJournalLine).where(FinanceJournalLine.journal_id == row.id).order_by(FinanceJournalLine.line_number)).all():
        line_payload = row_dict(line)
        account = db.get(ChartOfAccount, line.account_id)
        line_payload.update({"account_code": account.account_code if account else "", "account_name": account.name if account else ""})
        lines.append(line_payload)
    payload["lines"] = lines
    return payload


@router.post("/journals/{journal_id:int}/lines", status_code=201)
def add_journal_line(journal_id: int, payload: JournalLineInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    journal = journal_or_404(db, principal, journal_id, "finance.manage")
    if journal.status not in {"draft", "rejected"}:
        raise HTTPException(status_code=409, detail="Journal lines are frozen while approval is active or after posting")
    if (payload.debit <= 0 and payload.credit <= 0) or (payload.debit > 0 and payload.credit > 0):
        raise HTTPException(status_code=422, detail="Each finance journal line must contain either one positive debit or one positive credit")
    account_or_404(db, principal, payload.account_id)
    next_line = (db.scalar(select(func.max(FinanceJournalLine.line_number)).where(FinanceJournalLine.journal_id == journal.id)) or 0) + 1
    line = FinanceJournalLine(company_id=journal.company_id, journal_id=journal.id, line_number=next_line, account_id=payload.account_id, description=payload.description, debit=money(payload.debit), credit=money(payload.credit))
    db.add(line)
    db.flush()
    audit(db, principal, "finance.journal.line.added", line, branch_id=journal.branch_id, site_id=journal.site_id, project_id=journal.project_id, detail={"journal_id": journal.id})
    commit(db)
    return row_dict(line)


@router.delete("/journals/{journal_id:int}/lines/{line_id:int}")
def delete_journal_line(journal_id: int, line_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, int]:
    journal = journal_or_404(db, principal, journal_id, "finance.manage")
    if journal.status not in {"draft", "rejected"}:
        raise HTTPException(status_code=409, detail="Journal lines are frozen while approval is active or after posting")
    line = db.get(FinanceJournalLine, line_id)
    if not line or line.journal_id != journal.id or line.company_id != journal.company_id:
        raise HTTPException(status_code=404, detail="Finance journal line not found")
    db.delete(line)
    db.flush()
    audit(db, principal, "finance.journal.line.deleted", journal, branch_id=journal.branch_id, site_id=journal.site_id, project_id=journal.project_id, detail={"journal_id": journal.id, "line_id": line_id})
    commit(db)
    return {"deleted_line_id": line_id}


@router.post("/journals/{journal_id:int}/submit")
def submit_journal(journal_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    journal = journal_or_404(db, principal, journal_id, "finance.manage")
    if journal.status not in {"draft", "rejected"}:
        raise HTTPException(status_code=409, detail="Only draft or rejected journals can be submitted")
    period = period_or_404(db, principal, journal.period_id)
    require_open_period(period, journal.journal_date)
    cfg = finance_policy(db, journal.company_id)
    debit, credit, count = journal_totals(db, journal.id)
    if count < int(cfg["minimum_journal_lines"]):
        raise HTTPException(status_code=409, detail="A finance journal requires at least two lines before submission")
    if debit <= 0 or debit != credit:
        raise HTTPException(status_code=409, detail="Finance journal debit and credit totals must balance exactly before approval")
    if cfg["require_journal_evidence"] and not journal.supporting_document_id:
        raise HTTPException(status_code=409, detail="Controlled supporting evidence is required before a journal can be submitted")
    request = approval_request(db, principal, code="FINANCE_JOURNAL", entity_type="finance_journal", entity_id=journal.id, title=f"Finance journal {journal.journal_number}", amount=debit, branch_id=journal.branch_id, site_id=journal.site_id)
    journal.status, journal.approval_request_id, journal.submitted_at = "submitted", request.id, utcnow()
    audit(db, principal, "finance.journal.submitted", journal, branch_id=journal.branch_id, site_id=journal.site_id, project_id=journal.project_id, detail={"approval_reference": request.reference})
    commit(db)
    return row_dict(request)


@router.post("/journals/{journal_id:int}/post")
def post_journal(journal_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    journal = journal_or_404(db, principal, journal_id, "finance.post")
    if journal.status != "approved":
        raise HTTPException(status_code=409, detail="Only independently approved finance journals can be posted")
    period = period_or_404(db, principal, journal.period_id)
    require_open_period(period, journal.journal_date)
    debit, credit, _ = journal_totals(db, journal.id)
    if debit <= 0 or debit != credit:
        raise HTTPException(status_code=409, detail="Only a balanced finance journal can be posted")
    journal.status, journal.posted_by, journal.posted_at = "posted", principal.user.full_name, utcnow()
    audit(db, principal, "finance.journal.posted", journal, branch_id=journal.branch_id, site_id=journal.site_id, project_id=journal.project_id, detail={"debit_total": str(debit)})
    commit(db)
    return journal_payload(db, journal)


@router.get("/supplier-invoices")
def supplier_invoices(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    anywhere(principal, "finance.view")
    rows = db.scalars(select(SupplierInvoice).where(SupplierInvoice.company_id == principal.user.company_id).order_by(SupplierInvoice.due_date, SupplierInvoice.id.desc())).all()
    return [invoice_payload(db, row) for row in rows if principal.can("finance.view", branch_id=row.branch_id, site_id=row.site_id)]


@router.post("/supplier-invoices", status_code=201)
def create_supplier_invoice(payload: SupplierInvoiceInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    validate_scope_data(db, principal, branch_id=payload.branch_id, site_id=payload.site_id, project_id=payload.project_id, cost_centre_id=payload.cost_centre_id)
    scope(principal, "finance.manage", payload.branch_id, payload.site_id)
    if payload.due_date and payload.due_date < payload.invoice_date:
        raise HTTPException(status_code=422, detail="Supplier invoice due date cannot precede invoice date")
    supplier = db.get(Supplier, payload.supplier_id)
    if not supplier or supplier.company_id != principal.user.company_id or supplier.status != "active":
        raise HTTPException(status_code=422, detail="Supplier must be an active company supplier")
    if payload.purchase_order_id:
        order = db.get(PurchaseOrder, payload.purchase_order_id)
        if not order or order.company_id != principal.user.company_id or order.supplier_id != supplier.id:
            raise HTTPException(status_code=422, detail="Purchase order must belong to the selected supplier")
        if order.branch_id != payload.branch_id or order.site_id != payload.site_id or order.project_id != payload.project_id:
            raise HTTPException(status_code=422, detail="Purchase order is outside the selected finance scope")
    ensure_document(db, principal.user.company_id, payload.invoice_document_id)
    row = SupplierInvoice(company_id=principal.user.company_id, branch_id=payload.branch_id, site_id=payload.site_id, project_id=payload.project_id, cost_centre_id=payload.cost_centre_id, supplier_id=supplier.id, purchase_order_id=payload.purchase_order_id, invoice_number=issue_reference(db, principal.user.company_id, "SUPPLIER_INVOICE", "SIN"), supplier_invoice_reference=payload.supplier_invoice_reference.strip(), invoice_date=payload.invoice_date, due_date=payload.due_date, amount=money(payload.amount), paid_amount=Decimal("0"), status="draft", invoice_document_id=payload.invoice_document_id, notes=payload.notes, prepared_by=principal.user.full_name)
    db.add(row)
    db.flush()
    audit(db, principal, "finance.supplier_invoice.created", row, branch_id=row.branch_id, site_id=row.site_id, project_id=row.project_id)
    commit(db)
    return invoice_payload(db, row)


@router.post("/supplier-invoices/{invoice_id:int}/submit")
def submit_supplier_invoice(invoice_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    invoice = invoice_or_404(db, principal, invoice_id, "finance.manage")
    if invoice.status not in {"draft", "rejected"}:
        raise HTTPException(status_code=409, detail="Only draft or rejected supplier invoices can be submitted")
    if finance_policy(db, invoice.company_id)["require_invoice_evidence"] and not invoice.invoice_document_id:
        raise HTTPException(status_code=409, detail="Controlled supplier invoice evidence is required before approval")
    request = approval_request(db, principal, code="SUPPLIER_INVOICE", entity_type="supplier_invoice", entity_id=invoice.id, title=f"Supplier invoice {invoice.invoice_number}", amount=Decimal(invoice.amount), branch_id=invoice.branch_id, site_id=invoice.site_id)
    invoice.status, invoice.approval_request_id, invoice.submitted_at = "submitted", request.id, utcnow()
    audit(db, principal, "finance.supplier_invoice.submitted", invoice, branch_id=invoice.branch_id, site_id=invoice.site_id, project_id=invoice.project_id, detail={"approval_reference": request.reference})
    commit(db)
    return row_dict(request)


@router.get("/supplier-payments")
def supplier_payments(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    anywhere(principal, "finance.view")
    rows = db.scalars(select(SupplierPayment).where(SupplierPayment.company_id == principal.user.company_id).order_by(SupplierPayment.requested_date.desc(), SupplierPayment.id.desc())).all()
    result: list[dict[str, Any]] = []
    for row in rows:
        if not principal.can("finance.view", branch_id=row.branch_id, site_id=row.site_id):
            continue
        payload = row_dict(row)
        invoice = db.get(SupplierInvoice, row.supplier_invoice_id)
        supplier = db.get(Supplier, invoice.supplier_id) if invoice else None
        payload.update({"supplier_invoice_number": invoice.invoice_number if invoice else "", "supplier_name": supplier.name if supplier else "", "supplier_invoice_reference": invoice.supplier_invoice_reference if invoice else ""})
        result.append(payload)
    return result


@router.post("/supplier-invoices/{invoice_id:int}/payments", status_code=201)
def create_supplier_payment(invoice_id: int, payload: PaymentInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    invoice = invoice_or_404(db, principal, invoice_id, "finance.manage")
    if invoice.status not in {"approved", "part_paid"}:
        raise HTTPException(status_code=409, detail="Only independently approved supplier invoices can receive payment requests")
    reserved = money(db.scalar(select(func.coalesce(func.sum(SupplierPayment.amount), 0)).where(SupplierPayment.supplier_invoice_id == invoice.id, SupplierPayment.status.in_(("submitted", "approved", "recorded")))) or 0)
    available = money(Decimal(invoice.amount) - Decimal(invoice.paid_amount) - reserved)
    if money(payload.amount) > available:
        raise HTTPException(status_code=409, detail="Supplier payment request exceeds the uncommitted approved invoice balance")
    row = SupplierPayment(company_id=invoice.company_id, branch_id=invoice.branch_id, site_id=invoice.site_id, supplier_invoice_id=invoice.id, payment_number=issue_reference(db, invoice.company_id, "SUPPLIER_PAYMENT", "SPY"), requested_date=payload.requested_date, amount=money(payload.amount), payment_reference=payload.payment_reference, status="draft", notes=payload.notes, requested_by=principal.user.full_name)
    db.add(row)
    db.flush()
    audit(db, principal, "finance.supplier_payment.created", row, branch_id=row.branch_id, site_id=row.site_id, project_id=invoice.project_id, detail={"supplier_invoice_id": invoice.id})
    commit(db)
    return row_dict(row)


@router.post("/supplier-payments/{payment_id:int}/submit")
def submit_supplier_payment(payment_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    payment = payment_or_404(db, principal, payment_id, "finance.manage")
    if payment.status not in {"draft", "rejected"}:
        raise HTTPException(status_code=409, detail="Only draft or rejected payment requests can be submitted")
    invoice = invoice_or_404(db, principal, payment.supplier_invoice_id, "finance.manage")
    if invoice.status not in {"approved", "part_paid"}:
        raise HTTPException(status_code=409, detail="Supplier invoice is not available for payment approval")
    request = approval_request(db, principal, code="SUPPLIER_PAYMENT", entity_type="supplier_payment", entity_id=payment.id, title=f"Supplier payment {payment.payment_number}", amount=Decimal(payment.amount), branch_id=payment.branch_id, site_id=payment.site_id)
    payment.status, payment.approval_request_id, payment.submitted_at = "submitted", request.id, utcnow()
    audit(db, principal, "finance.supplier_payment.submitted", payment, branch_id=payment.branch_id, site_id=payment.site_id, project_id=invoice.project_id, detail={"approval_reference": request.reference})
    commit(db)
    return row_dict(request)


@router.post("/supplier-payments/{payment_id:int}/record")
def record_supplier_payment(payment_id: int, payload: PaymentRecordInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    payment = payment_or_404(db, principal, payment_id, "finance.pay")
    if payment.status != "approved":
        raise HTTPException(status_code=409, detail="Only independently approved payment requests can be recorded as supplied payment evidence")
    invoice = invoice_or_404(db, principal, payment.supplier_invoice_id, "finance.pay")
    if finance_policy(db, payment.company_id)["require_payment_evidence"] and not (payload.payment_document_id or payment.payment_document_id):
        raise HTTPException(status_code=409, detail="Controlled payment evidence is required before recording a supplier payment")
    if money(Decimal(invoice.paid_amount) + Decimal(payment.amount)) > money(invoice.amount):
        raise HTTPException(status_code=409, detail="Recorded supplier payment exceeds the remaining approved invoice balance")
    ensure_document(db, payment.company_id, payload.payment_document_id)
    payment.payment_document_id = payload.payment_document_id or payment.payment_document_id
    payment.payment_reference = payload.payment_reference or payment.payment_reference
    payment.notes = payload.notes or payment.notes
    payment.status, payment.recorded_by, payment.recorded_at = "recorded", principal.user.full_name, utcnow()
    invoice.paid_amount = money(Decimal(invoice.paid_amount) + Decimal(payment.amount))
    invoice.status = "paid" if money(invoice.paid_amount) == money(invoice.amount) else "part_paid"
    audit(db, principal, "finance.supplier_payment.recorded", payment, branch_id=payment.branch_id, site_id=payment.site_id, project_id=invoice.project_id, detail={"invoice_status": invoice.status, "paid_amount": str(invoice.paid_amount)})
    commit(db)
    return row_dict(payment)


@router.get("/approvals")
def approvals(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    anywhere(principal, "finance.view")
    rows = db.scalars(select(ApprovalRequest).where(ApprovalRequest.company_id == principal.user.company_id, ApprovalRequest.entity_type.in_(("finance_journal", "supplier_invoice", "supplier_payment")), ApprovalRequest.status == "pending").order_by(ApprovalRequest.requested_at)).all()
    result: list[dict[str, Any]] = []
    for request in rows:
        if not principal.can("finance.view", branch_id=request.branch_id, site_id=request.site_id):
            continue
        payload = row_dict(request)
        entity = db.get(FinanceJournal, int(request.entity_id)) if request.entity_type == "finance_journal" else (db.get(SupplierInvoice, int(request.entity_id)) if request.entity_type == "supplier_invoice" else db.get(SupplierPayment, int(request.entity_id)))
        payload["finance_reference"] = getattr(entity, "journal_number", None) or getattr(entity, "invoice_number", None) or getattr(entity, "payment_number", "")
        result.append(payload)
    return result


@router.post("/approvals/{request_id:int}/decision")
def decide_approval(request_id: int, payload: ApprovalDecision, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    request = db.get(ApprovalRequest, request_id)
    if not request or request.company_id != principal.user.company_id or request.entity_type not in {"finance_journal", "supplier_invoice", "supplier_payment"}:
        raise HTTPException(status_code=404, detail="Finance approval request not found")
    if request.entity_type == "finance_journal":
        entity = db.get(FinanceJournal, int(request.entity_id))
        if not entity:
            raise HTTPException(status_code=404, detail="Finance approval entity is unavailable")
        branch_id, site_id, project_id, expected_status = entity.branch_id, entity.site_id, entity.project_id, "submitted"
    elif request.entity_type == "supplier_invoice":
        entity = db.get(SupplierInvoice, int(request.entity_id))
        if not entity:
            raise HTTPException(status_code=404, detail="Finance approval entity is unavailable")
        branch_id, site_id, project_id, expected_status = entity.branch_id, entity.site_id, entity.project_id, "submitted"
    else:
        entity = db.get(SupplierPayment, int(request.entity_id))
        if not entity:
            raise HTTPException(status_code=404, detail="Finance approval entity is unavailable")
        invoice = db.get(SupplierInvoice, entity.supplier_invoice_id)
        branch_id, site_id, project_id, expected_status = entity.branch_id, entity.site_id, invoice.project_id if invoice else None, "submitted"
    scope(principal, "finance.approve", branch_id, site_id)
    if request.status != "pending" or entity.status != expected_status:
        raise HTTPException(status_code=409, detail="Finance approval request is not pending")
    step = db.scalar(select(ApprovalStep).where(ApprovalStep.workflow_id == request.workflow_id, ApprovalStep.step_order == request.current_step_order))
    if not step or not assignment_authorised(db, principal, step.role_id, branch_id, site_id):
        raise HTTPException(status_code=403, detail="Your active role assignment is not authorised for this finance approval step")
    if request.requested_by == principal.user.full_name and not allow_self_approval(db, request.company_id):
        raise HTTPException(status_code=422, detail="Self-approval is disabled by company policy")
    db.add(ApprovalAction(request_id=request.id, step_order=step.step_order, role_id=step.role_id, actor_name=principal.user.full_name, action=payload.decision, comment=payload.comment))
    if payload.decision == "reject":
        request.status, request.completed_at, entity.status = "rejected", utcnow(), "rejected"
    else:
        approved = (db.scalar(select(func.count()).select_from(ApprovalAction).where(ApprovalAction.request_id == request.id, ApprovalAction.step_order == step.step_order, ApprovalAction.action == "approve")) or 0) + 1
        if approved >= step.required_approvals:
            next_step = db.scalar(select(ApprovalStep).where(ApprovalStep.workflow_id == request.workflow_id, ApprovalStep.step_order > step.step_order).order_by(ApprovalStep.step_order).limit(1))
            if next_step:
                request.current_step_order = next_step.step_order
            else:
                request.status, request.completed_at, entity.status = "approved", utcnow(), "approved"
                entity.approved_at = utcnow()
    audit(db, principal, f"finance.approval.{payload.decision}", request, branch_id=branch_id, site_id=site_id, project_id=project_id, detail={"entity_type": request.entity_type, "approval_status": request.status, "step": step.step_order})
    commit(db)
    return row_dict(request)


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    anywhere(principal, "finance.view")
    journals = [row for row in db.scalars(select(FinanceJournal).where(FinanceJournal.company_id == principal.user.company_id)).all() if principal.can("finance.view", branch_id=row.branch_id, site_id=row.site_id)]
    invoices = [row for row in db.scalars(select(SupplierInvoice).where(SupplierInvoice.company_id == principal.user.company_id)).all() if principal.can("finance.view", branch_id=row.branch_id, site_id=row.site_id)]
    payments = [row for row in db.scalars(select(SupplierPayment).where(SupplierPayment.company_id == principal.user.company_id)).all() if principal.can("finance.view", branch_id=row.branch_id, site_id=row.site_id)]
    receivables: list[ClientInvoice] = []
    for invoice in db.scalars(select(ClientInvoice).where(ClientInvoice.company_id == principal.user.company_id)).all():
        contract = db.get(ClientContract, invoice.contract_id)
        if contract and principal.can("finance.view", branch_id=contract.branch_id, site_id=contract.site_id):
            receivables.append(invoice)
    today = date.today()
    payable_outstanding = money(sum((Decimal(row.amount) - Decimal(row.paid_amount) for row in invoices if row.status in {"approved", "part_paid", "paid"}), Decimal("0")))
    receivable_outstanding = money(sum((Decimal(row.net_amount) - Decimal(row.paid_amount) for row in receivables if row.status in {"issued", "part_paid", "paid"}), Decimal("0")))
    posted = [row for row in journals if row.status == "posted"]
    posted_debits = money(sum((journal_totals(db, row.id)[0] for row in posted), Decimal("0")))
    return {"open_periods": sum(row.status == "open" for row in db.scalars(select(FinancialPeriod).where(FinancialPeriod.company_id == principal.user.company_id)).all()), "journal_drafts": sum(row.status in {"draft", "rejected"} for row in journals), "journal_pending": sum(row.status == "submitted" for row in journals), "journals_posted": len(posted), "posted_debits": str(posted_debits), "payables_outstanding": str(payable_outstanding), "payables_overdue": str(money(sum((Decimal(row.amount) - Decimal(row.paid_amount) for row in invoices if row.status in {"approved", "part_paid"} and row.due_date is not None and row.due_date < today), Decimal("0")))), "payments_pending": sum(row.status in {"draft", "submitted", "approved"} for row in payments), "receivables_outstanding": str(receivable_outstanding), "receivables_overdue": str(money(sum((Decimal(row.net_amount) - Decimal(row.paid_amount) for row in receivables if row.status in {"issued", "part_paid"} and row.due_date is not None and row.due_date < today), Decimal("0"))))}


@router.get("/exports/supplier-invoices.csv")
def export_supplier_invoices(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> StreamingResponse:
    anywhere(principal, "finance.export")
    rows = supplier_invoices(db, principal)
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=["invoice_number", "supplier_name", "supplier_invoice_reference", "invoice_date", "due_date", "amount", "paid_amount", "outstanding_amount", "status", "purchase_order_number"])
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in writer.fieldnames})
    return StreamingResponse(iter([stream.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=supplier-invoice-register.csv"})


@router.get("/audit")
def audit_events(limit: int = Query(default=250, ge=1, le=1000), db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    anywhere(principal, "finance.view")
    rows = db.scalars(select(FinanceAuditEvent).where(FinanceAuditEvent.company_id == principal.user.company_id).order_by(FinanceAuditEvent.occurred_at.desc()).limit(limit)).all()
    return [row_dict(row) for row in rows if row.branch_id is None or principal.can("finance.view", branch_id=row.branch_id, site_id=row.site_id)]
