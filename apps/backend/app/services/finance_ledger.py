from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, object_session, selectinload

from app.models import FinanceClient, FinanceCreditNote, FinanceInvoice, FinancePayment
from app.services.finance_invoices import invoice_out


def client_out(row: FinanceClient) -> dict:
    return {
        "id": str(row.id), "name": row.name, "email": row.email, "address": row.address, "phone": row.phone,
        "default_service": row.default_service, "default_details": row.default_details,
        "default_quantity": row.default_quantity, "default_rate_minor": row.default_rate_minor,
        "default_tax_minor": row.default_tax_minor, "payment_terms_days": row.payment_terms_days,
        "active": row.active, "notes": row.notes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def payment_out(row: FinancePayment) -> dict:
    return {
        "id": str(row.id), "invoice_id": str(row.invoice_id), "amount_minor": row.amount_minor,
        "payment_date": row.payment_date.isoformat(), "method": row.method, "reference": row.reference,
        "note": row.note, "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def paid_minor(invoice: FinanceInvoice) -> int:
    return sum(max(0, int(payment.amount_minor)) for payment in invoice.payments)


def credited_minor(invoice: FinanceInvoice) -> int:
    return sum(max(0, int(note.amount_minor)) for note in getattr(invoice, "credit_notes", []))


def adjusted_total_minor(invoice: FinanceInvoice) -> int:
    return max(0, invoice.total_minor - credited_minor(invoice))


def effective_invoice_status(invoice: FinanceInvoice, *, today: date | None = None) -> str:
    current = today or date.today()
    paid = paid_minor(invoice)
    adjusted = adjusted_total_minor(invoice)
    if invoice.status == "cancelled": return "cancelled"
    if adjusted == 0 and credited_minor(invoice) > 0: return "credited"
    if paid >= adjusted and adjusted > 0: return "paid"
    if paid > 0: return "partial"
    if invoice.due_date < current and invoice.status not in {"draft", "failed"}: return "overdue"
    return invoice.status


def invoice_financial_out(invoice: FinanceInvoice) -> dict:
    data = invoice_out(invoice)
    paid = paid_minor(invoice)
    credited = credited_minor(invoice)
    adjusted = max(0, invoice.total_minor - credited)
    items = [
        {
            "id": str(item.id), "position": item.position, "description": item.description,
            "details": item.details, "quantity": item.quantity, "rate_minor": item.rate_minor,
            "tax_minor": item.tax_minor, "subtotal_minor": item.quantity * item.rate_minor,
            "total_minor": item.quantity * item.rate_minor + item.tax_minor,
        }
        for item in getattr(invoice, "items", [])
    ]
    data.update({
        "client_id": str(invoice.client_id) if invoice.client_id else None,
        "paid_minor": paid,
        "credited_minor": credited,
        "adjusted_total_minor": adjusted,
        "outstanding_minor": max(0, adjusted - paid),
        "status": effective_invoice_status(invoice),
        "cancelled_at": invoice.cancelled_at.isoformat() if invoice.cancelled_at else None,
        "payments": [payment_out(payment) for payment in sorted(invoice.payments, key=lambda p: (p.payment_date, p.created_at or datetime.min))],
        "credit_notes": [
            {"id": str(note.id), "credit_number": note.credit_number, "amount_minor": note.amount_minor, "reason": note.reason,
             "created_at": note.created_at.isoformat() if note.created_at else None}
            for note in sorted(getattr(invoice, "credit_notes", []), key=lambda n: n.created_at or datetime.min)
        ],
        "items": items,
    })
    return data


def _settlement_totals(invoice: FinanceInvoice) -> tuple[int, int]:
    session = object_session(invoice)
    if session is None or invoice.id is None:
        return paid_minor(invoice), credited_minor(invoice)
    paid = session.scalar(
        select(func.coalesce(func.sum(FinancePayment.amount_minor), 0)).where(FinancePayment.invoice_id == invoice.id)
    ) or 0
    credited = session.scalar(
        select(func.coalesce(func.sum(FinanceCreditNote.amount_minor), 0)).where(FinanceCreditNote.invoice_id == invoice.id)
    ) or 0
    return int(paid), int(credited)


def sync_invoice_payment_status(invoice: FinanceInvoice) -> None:
    if invoice.status == "cancelled": return
    paid, credited = _settlement_totals(invoice)
    adjusted = max(0, invoice.total_minor - credited)
    if adjusted == 0 and credited > 0: invoice.status = "credited"
    elif paid >= adjusted and adjusted > 0: invoice.status = "paid"
    elif paid > 0: invoice.status = "partial"
    elif invoice.sent_at is not None: invoice.status = "sent"
    elif invoice.status in {"paid", "partial", "credited"}: invoice.status = "draft"


def dashboard_out(db: Session) -> dict:
    invoices = db.scalars(
        select(FinanceInvoice)
        .options(selectinload(FinanceInvoice.payments), selectinload(FinanceInvoice.credit_notes))
        .order_by(FinanceInvoice.created_at.desc())
    ).all()
    clients = db.scalar(select(func.count(FinanceClient.id)).where(FinanceClient.active.is_(True))) or 0
    today = date.today(); month_start = today.replace(day=1)
    total_invoiced = collected = credits = outstanding = overdue = month_invoiced = month_collected = overdue_count = 0
    for invoice in invoices:
        if invoice.status == "cancelled": continue
        paid = paid_minor(invoice); credited = credited_minor(invoice); adjusted = max(0, invoice.total_minor - credited); balance = max(0, adjusted - paid)
        total_invoiced += invoice.total_minor; collected += paid; credits += credited; outstanding += balance
        if invoice.created_at and invoice.created_at.date() >= month_start: month_invoiced += invoice.total_minor
        for payment in invoice.payments:
            if payment.payment_date >= month_start: month_collected += payment.amount_minor
        if balance > 0 and invoice.due_date < today and invoice.status not in {"draft", "failed"}:
            overdue += balance; overdue_count += 1
    return {
        "active_clients": int(clients), "invoice_count": len(invoices), "total_invoiced_minor": total_invoiced,
        "collected_minor": collected, "credited_minor": credits, "outstanding_minor": outstanding, "overdue_minor": overdue,
        "overdue_count": overdue_count, "month_invoiced_minor": month_invoiced, "month_collected_minor": month_collected,
    }


def aging_out(invoices: list[FinanceInvoice], *, today: date | None = None) -> dict:
    current = today or date.today()
    buckets = {
        "current": {"count": 0, "amount_minor": 0},
        "1_30": {"count": 0, "amount_minor": 0},
        "31_60": {"count": 0, "amount_minor": 0},
        "61_90": {"count": 0, "amount_minor": 0},
        "90_plus": {"count": 0, "amount_minor": 0},
    }
    rows = []
    for invoice in invoices:
        if invoice.status in {"cancelled", "draft", "failed"}: continue
        balance = max(0, adjusted_total_minor(invoice) - paid_minor(invoice))
        if balance <= 0: continue
        days = (current - invoice.due_date).days
        key = "current" if days <= 0 else "1_30" if days <= 30 else "31_60" if days <= 60 else "61_90" if days <= 90 else "90_plus"
        buckets[key]["count"] += 1; buckets[key]["amount_minor"] += balance
        rows.append({"invoice": invoice_financial_out(invoice), "days_overdue": max(0, days), "bucket": key})
    return {"as_of": current.isoformat(), "buckets": buckets, "items": rows}
