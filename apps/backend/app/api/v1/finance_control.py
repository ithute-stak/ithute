from __future__ import annotations

from calendar import monthrange
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_platform_owner
from app.db.session import get_db
from app.models import FinanceAccountingPeriod, FinanceInvoice, FinancePayment, FinanceRefund, FinanceTaxRate, User
from app.services.finance_audit import log_finance_action
from app.services.finance_delivery import send_invoice
from app.services.finance_ledger import invoice_financial_out, payment_refunded_minor, sync_invoice_payment_status
from app.services.finance_periods import ensure_period_open, lock_period, period_out, reopen_period

router = APIRouter(prefix="/finance/control", tags=["finance-control"])


class PeriodAction(BaseModel):
    note: str = Field(default="", max_length=1000)


class TaxRateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    rate_percent: float = Field(ge=0, le=100)
    inclusive: bool = False
    active: bool = True
    effective_from: date | None = None
    effective_to: date | None = None


class RefundCreate(BaseModel):
    payment_id: UUID
    amount_minor: int = Field(gt=0, le=2_000_000_000)
    refund_date: date
    method: str = Field(default="bank_transfer", min_length=2, max_length=80)
    reference: str = Field(default="", max_length=180)
    reason: str = Field(min_length=2, max_length=1000)


class BulkSendRequest(BaseModel):
    invoice_ids: list[UUID] = Field(min_length=1, max_length=100)
    resend: bool = False


def _tax_out(row: FinanceTaxRate) -> dict:
    return {
        "id": str(row.id), "name": row.name,
        "rate_basis_points": row.rate_basis_points,
        "rate_percent": row.rate_basis_points / 100,
        "inclusive": row.inclusive, "active": row.active,
        "effective_from": row.effective_from.isoformat() if row.effective_from else None,
        "effective_to": row.effective_to.isoformat() if row.effective_to else None,
    }


def _refund_out(row: FinanceRefund) -> dict:
    return {
        "id": str(row.id), "invoice_id": str(row.invoice_id), "payment_id": str(row.payment_id),
        "amount_minor": row.amount_minor, "refund_date": row.refund_date.isoformat(),
        "method": row.method, "reference": row.reference, "reason": row.reason, "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/periods")
def list_periods(
    year: int | None = Query(default=None, ge=2000, le=2100),
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    del current
    stmt = select(FinanceAccountingPeriod).order_by(FinanceAccountingPeriod.year.desc(), FinanceAccountingPeriod.month.desc())
    if year is not None:
        stmt = stmt.where(FinanceAccountingPeriod.year == year)
    return {"items": [period_out(row) for row in db.scalars(stmt).all()]}


@router.post("/periods/{year}/{month}/lock")
def close_period(
    year: int,
    month: int,
    payload: PeriodAction,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    if year < 2000 or year > 2100 or month < 1 or month > 12:
        raise HTTPException(status_code=422, detail="Invalid accounting period")
    row = db.scalar(select(FinanceAccountingPeriod).where(FinanceAccountingPeriod.year == year, FinanceAccountingPeriod.month == month))
    if row is None:
        row = FinanceAccountingPeriod(year=year, month=month, status="open")
        db.add(row); db.flush()
    if row.status == "locked":
        return period_out(row)
    lock_period(row, user_id=current.id, note=payload.note)
    log_finance_action(db, action="finance.period.locked", resource_type="finance_accounting_period", resource_id=row.id, actor_user_id=current.id, metadata={"period": f"{year:04d}-{month:02d}", "note": payload.note})
    db.commit(); db.refresh(row)
    return period_out(row)


@router.post("/periods/{year}/{month}/reopen")
def open_period(
    year: int,
    month: int,
    payload: PeriodAction,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    row = db.scalar(select(FinanceAccountingPeriod).where(FinanceAccountingPeriod.year == year, FinanceAccountingPeriod.month == month))
    if row is None:
        raise HTTPException(status_code=404, detail="Accounting period not found")
    reopen_period(row, note=payload.note)
    log_finance_action(db, action="finance.period.reopened", resource_type="finance_accounting_period", resource_id=row.id, actor_user_id=current.id, metadata={"period": f"{year:04d}-{month:02d}", "note": payload.note})
    db.commit(); db.refresh(row)
    return period_out(row)


@router.get("/periods/{year}/{month}/summary")
def period_close_summary(year: int, month: int, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    if month < 1 or month > 12:
        raise HTTPException(status_code=422, detail="Invalid month")
    start = date(year, month, 1); end = date(year, month, monthrange(year, month)[1])
    invoices = db.scalars(select(FinanceInvoice).options(selectinload(FinanceInvoice.payments), selectinload(FinanceInvoice.credit_notes), selectinload(FinanceInvoice.items)).where(FinanceInvoice.created_at >= start, FinanceInvoice.created_at < date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1))).all()
    rows = [invoice_financial_out(row) for row in invoices if row.status != "cancelled"]
    payments = db.scalars(select(FinancePayment).where(FinancePayment.payment_date >= start, FinancePayment.payment_date <= end)).all()
    refunds = db.scalars(select(FinanceRefund).where(FinanceRefund.refund_date >= start, FinanceRefund.refund_date <= end)).all()
    gross_collected = sum(p.amount_minor for p in payments)
    refunded = sum(r.amount_minor for r in refunds)
    return {
        "period": f"{year:04d}-{month:02d}", "invoice_count": len(rows),
        "gross_invoiced_minor": sum(r["total_minor"] for r in rows),
        "net_invoiced_minor": sum(r["adjusted_total_minor"] for r in rows),
        "gross_collected_minor": gross_collected, "refunded_minor": refunded,
        "net_collected_minor": max(0, gross_collected - refunded),
        "outstanding_minor": sum(r["outstanding_minor"] for r in rows),
        "unsettled_invoice_count": sum(1 for r in rows if r["outstanding_minor"] > 0),
    }


@router.get("/tax-rates")
def list_tax_rates(db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    rows = db.scalars(select(FinanceTaxRate).order_by(FinanceTaxRate.active.desc(), FinanceTaxRate.name.asc())).all()
    return {"items": [_tax_out(row) for row in rows]}


@router.post("/tax-rates", status_code=201)
def create_tax_rate(payload: TaxRateCreate, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    if payload.effective_from and payload.effective_to and payload.effective_to < payload.effective_from:
        raise HTTPException(status_code=422, detail="Tax effective-to date must be on or after effective-from date")
    row = FinanceTaxRate(
        name=payload.name.strip(), rate_basis_points=round(payload.rate_percent * 100),
        inclusive=payload.inclusive, active=payload.active, effective_from=payload.effective_from,
        effective_to=payload.effective_to, created_by_user_id=current.id,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback(); raise HTTPException(status_code=409, detail="A tax rate with that name already exists") from exc
    db.refresh(row)
    return _tax_out(row)


@router.post("/tax-rates/{tax_rate_id}/calculate")
def calculate_tax(tax_rate_id: UUID, subtotal_minor: int = Query(ge=0, le=2_000_000_000), db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    row = db.get(FinanceTaxRate, tax_rate_id)
    if row is None or not row.active:
        raise HTTPException(status_code=404, detail="Active tax rate not found")
    if row.inclusive:
        tax_minor = round(subtotal_minor * row.rate_basis_points / (10000 + row.rate_basis_points)) if row.rate_basis_points else 0
        net_minor = subtotal_minor - tax_minor
        total_minor = subtotal_minor
    else:
        tax_minor = round(subtotal_minor * row.rate_basis_points / 10000)
        net_minor = subtotal_minor
        total_minor = subtotal_minor + tax_minor
    return {"tax_rate": _tax_out(row), "net_minor": net_minor, "tax_minor": tax_minor, "total_minor": total_minor}


@router.get("/refunds")
def list_refunds(db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    rows = db.scalars(select(FinanceRefund).order_by(FinanceRefund.refund_date.desc(), FinanceRefund.created_at.desc())).all()
    return {"items": [_refund_out(row) for row in rows]}


@router.post("/refunds", status_code=201)
def create_refund(payload: RefundCreate, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    payment = db.get(FinancePayment, payload.payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    try:
        ensure_period_open(db, payload.refund_date, operation="recording a refund")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    already_refunded = payment_refunded_minor(payment)
    available = max(0, payment.amount_minor - already_refunded)
    if payload.amount_minor > available:
        raise HTTPException(status_code=422, detail=f"Refund exceeds refundable payment balance of {available} minor units")
    row = FinanceRefund(
        invoice_id=payment.invoice_id, payment_id=payment.id, amount_minor=payload.amount_minor,
        refund_date=payload.refund_date, method=payload.method.strip().lower(), reference=payload.reference.strip(),
        reason=payload.reason.strip(), created_by_user_id=current.id,
    )
    db.add(row); db.flush()
    invoice = db.scalar(select(FinanceInvoice).options(selectinload(FinanceInvoice.payments), selectinload(FinanceInvoice.credit_notes), selectinload(FinanceInvoice.items)).where(FinanceInvoice.id == payment.invoice_id))
    sync_invoice_payment_status(invoice)
    log_finance_action(db, action="finance.refund.processed", resource_type="finance_invoice", resource_id=invoice.id, actor_user_id=current.id, metadata={"payment_id": str(payment.id), "refund_id": str(row.id), "amount_minor": row.amount_minor, "reason": row.reason})
    db.commit(); db.refresh(row)
    return {"refund": _refund_out(row), "invoice": invoice_financial_out(invoice)}


@router.post("/bulk/invoices/send")
def bulk_send_invoices(payload: BulkSendRequest, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    sent = []; failed = []
    for invoice_id in payload.invoice_ids:
        invoice = db.scalar(select(FinanceInvoice).where(FinanceInvoice.id == invoice_id))
        if invoice is None:
            failed.append({"invoice_id": str(invoice_id), "error": "Invoice not found"}); continue
        if invoice.status in {"paid", "cancelled", "credited"}:
            failed.append({"invoice_id": str(invoice_id), "error": f"Invoice is {invoice.status}"}); continue
        if invoice.status == "sent" and not payload.resend:
            failed.append({"invoice_id": str(invoice_id), "error": "Already sent"}); continue
        try:
            send_invoice(db, invoice); db.commit(); sent.append(str(invoice_id))
        except Exception as exc:
            db.rollback(); failed.append({"invoice_id": str(invoice_id), "error": str(exc)[:300]})
    log_finance_action(db, action="finance.bulk.invoice_send", resource_type="finance_bulk", resource_id="invoice-send", actor_user_id=current.id, metadata={"requested": len(payload.invoice_ids), "sent": len(sent), "failed": len(failed), "resend": payload.resend})
    db.commit()
    return {"sent": sent, "failed": failed}
