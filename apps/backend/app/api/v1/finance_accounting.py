from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_platform_owner
from app.db.session import get_db
from app.models import FinanceClient, FinanceInvoice, FinanceInvoiceSchedule, FinancePayment, IthuteProduct, User
from app.models.finance_accounting import FinanceBankTransaction, FinanceExpense, FinanceServiceBillingLink
from app.services.finance_audit import log_finance_action
from app.services.finance_ledger import invoice_financial_out, sync_invoice_payment_status

router = APIRouter(prefix="/finance/accounting", tags=["finance-accounting"])


class ExpenseCreate(BaseModel):
    expense_date: date
    vendor: str = Field(min_length=1, max_length=180)
    category: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    amount_minor: int = Field(ge=0)
    tax_minor: int = Field(default=0, ge=0)
    payment_method: str = Field(default="bank_transfer", max_length=80)
    reference: str = Field(default="", max_length=180)
    recurring: bool = False


class BankRow(BaseModel):
    transaction_date: date
    amount_minor: int
    description: str = Field(default="", max_length=1000)
    reference: str = Field(default="", max_length=255)


class BankImport(BaseModel):
    source_name: str = Field(default="LPB", max_length=120)
    import_batch: str = Field(default="manual", max_length=120)
    rows: list[BankRow] = Field(min_length=1, max_length=5000)


class ReconcilePayload(BaseModel):
    invoice_id: UUID


class ServiceLinkCreate(BaseModel):
    client_id: UUID
    source_type: str = Field(default="ithute_product", max_length=80)
    source_ref: str = Field(min_length=1, max_length=255)
    service_label: str = Field(min_length=1, max_length=500)
    details: str = Field(default="", max_length=1200)
    quantity: int = Field(default=1, ge=1, le=100000)
    rate_minor: int = Field(ge=0)
    tax_minor: int = Field(default=0, ge=0)
    send_day: int = Field(default=1, ge=1, le=31)
    due_days: int = Field(default=7, ge=0, le=365)
    enabled: bool = True


def _expense_out(row: FinanceExpense) -> dict:
    return {
        "id": str(row.id), "expense_date": row.expense_date.isoformat(), "vendor": row.vendor,
        "category": row.category, "description": row.description, "amount_minor": row.amount_minor,
        "tax_minor": row.tax_minor, "payment_method": row.payment_method, "reference": row.reference,
        "recurring": row.recurring, "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _invoice_options():
    return (
        selectinload(FinanceInvoice.payments),
        selectinload(FinanceInvoice.credit_notes),
        selectinload(FinanceInvoice.items),
    )


def _bank_out(db: Session, row: FinanceBankTransaction) -> dict:
    suggestion = None
    if row.status == "unmatched" and row.amount_minor > 0:
        invoices = db.scalars(select(FinanceInvoice).options(*_invoice_options()).where(
            FinanceInvoice.status.notin_(["cancelled", "paid", "credited"])
        )).all()
        text = f"{row.reference} {row.description}".lower()
        exact = [invoice for invoice in invoices if invoice.invoice_number.lower() in text and invoice_financial_out(invoice)["outstanding_minor"] > 0]
        if len(exact) == 1:
            suggestion = {"reason": "invoice_number", "invoice": invoice_financial_out(exact[0])}
        else:
            same_amount = [invoice for invoice in invoices if invoice_financial_out(invoice)["outstanding_minor"] == row.amount_minor]
            if len(same_amount) == 1:
                suggestion = {"reason": "unique_outstanding_amount", "invoice": invoice_financial_out(same_amount[0])}
    return {
        "id": str(row.id), "transaction_date": row.transaction_date.isoformat(), "amount_minor": row.amount_minor,
        "description": row.description, "reference": row.reference, "source_name": row.source_name,
        "import_batch": row.import_batch, "status": row.status,
        "matched_invoice_id": str(row.matched_invoice_id) if row.matched_invoice_id else None,
        "matched_payment_id": str(row.matched_payment_id) if row.matched_payment_id else None,
        "suggestion": suggestion,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _service_link_out(row: FinanceServiceBillingLink) -> dict:
    return {
        "id": str(row.id), "client_id": str(row.client_id), "source_type": row.source_type,
        "source_ref": row.source_ref, "service_label": row.service_label, "details": row.details,
        "quantity": row.quantity, "rate_minor": row.rate_minor, "tax_minor": row.tax_minor,
        "send_day": row.send_day, "due_days": row.due_days, "enabled": row.enabled,
        "schedule_id": str(row.schedule_id) if row.schedule_id else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/expenses")
def list_expenses(
    status: str | None = None,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    del current
    stmt = select(FinanceExpense).order_by(FinanceExpense.expense_date.desc(), FinanceExpense.created_at.desc())
    if status:
        stmt = stmt.where(FinanceExpense.status == status)
    return {"items": [_expense_out(row) for row in db.scalars(stmt).all()]}


@router.post("/expenses")
def create_expense(payload: ExpenseCreate, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    row = FinanceExpense(**payload.model_dump(), created_by_user_id=current.id)
    db.add(row)
    db.flush()
    log_finance_action(db, action="finance.expense.created", resource_type="finance_expense", resource_id=row.id, actor_user_id=current.id, metadata={"amount_minor": row.amount_minor, "vendor": row.vendor})
    db.commit(); db.refresh(row)
    return _expense_out(row)


@router.patch("/expenses/{expense_id}/void")
def void_expense(expense_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    row = db.get(FinanceExpense, expense_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Expense not found")
    row.status = "void"
    log_finance_action(db, action="finance.expense.voided", resource_type="finance_expense", resource_id=row.id, actor_user_id=current.id)
    db.commit(); db.refresh(row)
    return _expense_out(row)


@router.post("/bank/import")
def import_bank_rows(payload: BankImport, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    imported = duplicates = 0
    for item in payload.rows:
        raw = f"{payload.source_name}|{item.transaction_date.isoformat()}|{item.amount_minor}|{item.reference.strip()}|{item.description.strip()}"
        fingerprint = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        if db.scalar(select(FinanceBankTransaction.id).where(FinanceBankTransaction.fingerprint == fingerprint)):
            duplicates += 1
            continue
        db.add(FinanceBankTransaction(
            transaction_date=item.transaction_date, amount_minor=item.amount_minor, description=item.description.strip(),
            reference=item.reference.strip(), source_name=payload.source_name.strip() or "LPB",
            import_batch=payload.import_batch.strip() or "manual", fingerprint=fingerprint, created_by_user_id=current.id,
        ))
        imported += 1
    log_finance_action(db, action="finance.bank.imported", resource_type="finance_bank_import", resource_id=payload.import_batch, actor_user_id=current.id, metadata={"imported": imported, "duplicates": duplicates, "source_name": payload.source_name})
    db.commit()
    return {"imported": imported, "duplicates": duplicates}


@router.get("/bank")
def list_bank_rows(
    status: str = Query(default="unmatched"),
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    del current
    stmt = select(FinanceBankTransaction).order_by(FinanceBankTransaction.transaction_date.desc(), FinanceBankTransaction.created_at.desc())
    if status != "all":
        stmt = stmt.where(FinanceBankTransaction.status == status)
    return {"items": [_bank_out(db, row) for row in db.scalars(stmt).all()]}


@router.post("/bank/{transaction_id}/reconcile")
def reconcile_bank_row(transaction_id: UUID, payload: ReconcilePayload, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    row = db.get(FinanceBankTransaction, transaction_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Bank transaction not found")
    if row.status == "matched":
        raise HTTPException(status_code=409, detail="Transaction already reconciled")
    if row.amount_minor <= 0:
        raise HTTPException(status_code=400, detail="Only positive bank credits can be reconciled to invoices")
    invoice = db.scalar(select(FinanceInvoice).options(*_invoice_options()).where(FinanceInvoice.id == payload.invoice_id))
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    financial = invoice_financial_out(invoice)
    outstanding = financial["outstanding_minor"]
    if outstanding <= 0:
        raise HTTPException(status_code=409, detail="Invoice has no outstanding balance")
    amount = min(row.amount_minor, outstanding)
    payment = FinancePayment(
        invoice_id=invoice.id, amount_minor=amount, payment_date=row.transaction_date,
        method="bank_transfer", reference=row.reference or row.description[:180],
        note=f"Reconciled from {row.source_name} import {row.import_batch}", recorded_by_user_id=current.id,
    )
    db.add(payment); db.flush()
    row.status = "matched"; row.matched_invoice_id = invoice.id; row.matched_payment_id = payment.id; row.reconciled_at = datetime.now(timezone.utc)
    sync_invoice_payment_status(invoice)
    log_finance_action(db, action="finance.bank.reconciled", resource_type="finance_invoice", resource_id=invoice.id, actor_user_id=current.id, metadata={"transaction_id": str(row.id), "payment_id": str(payment.id), "amount_minor": amount})
    db.commit()
    return {"transaction": _bank_out(db, row), "invoice": invoice_financial_out(invoice)}


@router.patch("/bank/{transaction_id}/ignore")
def ignore_bank_row(transaction_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    row = db.get(FinanceBankTransaction, transaction_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Bank transaction not found")
    if row.status == "matched":
        raise HTTPException(status_code=409, detail="Matched transactions cannot be ignored")
    row.status = "ignored"
    log_finance_action(db, action="finance.bank.ignored", resource_type="finance_bank_transaction", resource_id=row.id, actor_user_id=current.id)
    db.commit(); db.refresh(row)
    return _bank_out(db, row)


@router.get("/pnl")
def management_pnl(
    start: date,
    end: date,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    del current
    if end < start:
        raise HTTPException(status_code=400, detail="End date must be on or after start date")
    invoices = db.scalars(select(FinanceInvoice).options(*_invoice_options()).where(FinanceInvoice.created_at >= datetime.combine(start, datetime.min.time()), FinanceInvoice.created_at < datetime.combine(end, datetime.max.time()))).all()
    revenue = sum(invoice_financial_out(invoice).get("adjusted_total_minor", invoice.total_minor) for invoice in invoices if invoice.status != "cancelled")
    expenses = db.scalars(select(FinanceExpense).where(FinanceExpense.expense_date >= start, FinanceExpense.expense_date <= end, FinanceExpense.status == "posted")).all()
    expense_total = sum(row.amount_minor + row.tax_minor for row in expenses)
    by_category: dict[str, int] = {}
    for row in expenses:
        by_category[row.category] = by_category.get(row.category, 0) + row.amount_minor + row.tax_minor
    return {"start": start.isoformat(), "end": end.isoformat(), "revenue_minor": revenue, "expense_minor": expense_total, "net_profit_minor": revenue - expense_total, "expense_by_category": by_category, "basis": "management_accrual"}


@router.get("/service-links")
def list_service_links(db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    return {"items": [_service_link_out(row) for row in db.scalars(select(FinanceServiceBillingLink).order_by(FinanceServiceBillingLink.created_at.desc())).all()]}


@router.post("/service-links")
def create_service_link(payload: ServiceLinkCreate, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    client = db.get(FinanceClient, payload.client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Finance client not found")
    if payload.source_type == "ithute_product" and db.get(IthuteProduct, payload.source_ref) is None:
        raise HTTPException(status_code=404, detail="Ithute product not found")
    duplicate = db.scalar(select(FinanceServiceBillingLink.id).where(
        FinanceServiceBillingLink.client_id == payload.client_id,
        FinanceServiceBillingLink.source_type == payload.source_type,
        FinanceServiceBillingLink.source_ref == payload.source_ref,
    ))
    if duplicate:
        raise HTTPException(status_code=409, detail="This service is already linked to the client")
    schedule = FinanceInvoiceSchedule(
        client_id=client.id, client_name=client.name, recipient_email=client.email, client_address=client.address,
        description=payload.service_label, details=payload.details, quantity=payload.quantity,
        rate_minor=payload.rate_minor, tax_minor=payload.tax_minor, send_day=payload.send_day,
        due_days=payload.due_days, enabled=payload.enabled, created_by_user_id=current.id,
    )
    db.add(schedule); db.flush()
    row = FinanceServiceBillingLink(**payload.model_dump(), schedule_id=schedule.id, created_by_user_id=current.id)
    db.add(row); db.flush()
    log_finance_action(db, action="finance.service_link.created", resource_type="finance_client", resource_id=client.id, actor_user_id=current.id, metadata={"source_type": row.source_type, "source_ref": row.source_ref, "schedule_id": str(schedule.id)})
    db.commit(); db.refresh(row)
    return _service_link_out(row)


@router.patch("/service-links/{link_id}/toggle")
def toggle_service_link(link_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    row = db.get(FinanceServiceBillingLink, link_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Service billing link not found")
    row.enabled = not row.enabled
    if row.schedule_id:
        schedule = db.get(FinanceInvoiceSchedule, row.schedule_id)
        if schedule:
            schedule.enabled = row.enabled
    log_finance_action(db, action="finance.service_link.toggled", resource_type="finance_client", resource_id=row.client_id, actor_user_id=current.id, metadata={"link_id": str(row.id), "enabled": row.enabled})
    db.commit(); db.refresh(row)
    return _service_link_out(row)
