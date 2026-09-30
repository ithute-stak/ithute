from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import FinanceClient, FinanceInvoice, FinancePayment
from app.services.finance_invoices import invoice_out


def client_out(row: FinanceClient) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "email": row.email,
        "address": row.address,
        "phone": row.phone,
        "default_service": row.default_service,
        "default_details": row.default_details,
        "default_quantity": row.default_quantity,
        "default_rate_minor": row.default_rate_minor,
        "default_tax_minor": row.default_tax_minor,
        "payment_terms_days": row.payment_terms_days,
        "active": row.active,
        "notes": row.notes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def payment_out(row: FinancePayment) -> dict:
    return {
        "id": str(row.id),
        "invoice_id": str(row.invoice_id),
        "amount_minor": row.amount_minor,
        "payment_date": row.payment_date.isoformat(),
        "method": row.method,
        "reference": row.reference,
        "note": row.note,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def paid_minor(invoice: FinanceInvoice) -> int:
    return sum(max(0, int(payment.amount_minor)) for payment in invoice.payments)


def effective_invoice_status(invoice: FinanceInvoice, *, today: date | None = None) -> str:
    current = today or date.today()
    paid = paid_minor(invoice)
    if invoice.status == "cancelled":
        return "cancelled"
    if paid >= invoice.total_minor and invoice.total_minor > 0:
        return "paid"
    if paid > 0:
        return "partial"
    if invoice.due_date < current and invoice.status not in {"draft", "failed"}:
        return "overdue"
    return invoice.status


def invoice_financial_out(invoice: FinanceInvoice) -> dict:
    data = invoice_out(invoice)
    paid = paid_minor(invoice)
    data.update(
        {
            "client_id": str(invoice.client_id) if invoice.client_id else None,
            "paid_minor": paid,
            "outstanding_minor": max(0, invoice.total_minor - paid),
            "status": effective_invoice_status(invoice),
            "cancelled_at": invoice.cancelled_at.isoformat() if invoice.cancelled_at else None,
            "payments": [payment_out(payment) for payment in sorted(invoice.payments, key=lambda p: (p.payment_date, p.created_at or datetime.min))],
        }
    )
    return data


def sync_invoice_payment_status(invoice: FinanceInvoice) -> None:
    if invoice.status == "cancelled":
        return
    paid = paid_minor(invoice)
    if paid >= invoice.total_minor and invoice.total_minor > 0:
        invoice.status = "paid"
    elif paid > 0:
        invoice.status = "partial"
    elif invoice.sent_at is not None:
        invoice.status = "sent"
    elif invoice.status in {"paid", "partial"}:
        invoice.status = "draft"


def dashboard_out(db: Session) -> dict:
    invoices = db.scalars(select(FinanceInvoice).order_by(FinanceInvoice.created_at.desc())).all()
    clients = db.scalar(select(func.count(FinanceClient.id)).where(FinanceClient.active.is_(True))) or 0
    today = date.today()
    month_start = today.replace(day=1)

    total_invoiced = 0
    collected = 0
    outstanding = 0
    overdue = 0
    month_invoiced = 0
    month_collected = 0
    overdue_count = 0

    for invoice in invoices:
        if invoice.status == "cancelled":
            continue
        paid = paid_minor(invoice)
        balance = max(0, invoice.total_minor - paid)
        total_invoiced += invoice.total_minor
        collected += paid
        outstanding += balance
        if invoice.created_at and invoice.created_at.date() >= month_start:
            month_invoiced += invoice.total_minor
        for payment in invoice.payments:
            if payment.payment_date >= month_start:
                month_collected += payment.amount_minor
        if balance > 0 and invoice.due_date < today and invoice.status not in {"draft", "failed"}:
            overdue += balance
            overdue_count += 1

    return {
        "active_clients": int(clients),
        "invoice_count": len(invoices),
        "total_invoiced_minor": total_invoiced,
        "collected_minor": collected,
        "outstanding_minor": outstanding,
        "overdue_minor": overdue,
        "overdue_count": overdue_count,
        "month_invoiced_minor": month_invoiced,
        "month_collected_minor": month_collected,
    }
