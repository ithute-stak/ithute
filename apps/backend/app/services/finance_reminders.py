from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import SessionLocal
from app.models import FinanceInvoice
from app.services.finance_audit import finance_action_exists, log_finance_action
from app.services.finance_invoice_multi import render_invoice_pdf
from app.services.finance_ledger import adjusted_total_minor, paid_minor
from app.services.finance_mail import send_finance_message
from app.services.finance_preferences import client_reminders_enabled


def _reminder_key(invoice: FinanceInvoice, today: date) -> tuple[str, str] | None:
    delta = (invoice.due_date - today).days
    if delta == 3:
        return "pre_due_3", "Payment reminder"
    if delta == 0:
        return "due_today", "Invoice due today"
    if delta in {-3, -7, -14, -30}:
        days = abs(delta)
        return f"overdue_{days}", f"Invoice overdue by {days} days"
    return None


def _money(minor: int) -> str:
    return f"M {minor / 100:,.2f}"


def process_due_payment_reminders(now: datetime | None = None) -> int:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    today = current.date()
    db = SessionLocal()
    sent = 0
    try:
        invoices = db.scalars(
            select(FinanceInvoice)
            .options(selectinload(FinanceInvoice.payments), selectinload(FinanceInvoice.credit_notes), selectinload(FinanceInvoice.items))
            .where(FinanceInvoice.status.notin_(["draft", "failed", "cancelled", "paid", "credited"]))
            .order_by(FinanceInvoice.due_date)
        ).all()
        for invoice in invoices:
            if not client_reminders_enabled(db, invoice.client_id):
                continue
            outstanding = max(0, adjusted_total_minor(invoice) - paid_minor(invoice))
            if outstanding <= 0:
                continue
            reminder = _reminder_key(invoice, today)
            if reminder is None:
                continue
            key, heading = reminder
            action = f"finance.reminder.{key}.sent"
            if finance_action_exists(db, action=action, resource_type="finance_invoice", resource_id=invoice.id):
                continue
            subject = f"{heading}: {invoice.invoice_number}"
            text = (
                f"Dear {invoice.client_name},\n\n"
                f"This is a reminder for invoice {invoice.invoice_number}. "
                f"The outstanding balance is {_money(outstanding)} and the due date is {invoice.due_date:%d %B %Y}.\n\n"
                "Please use the invoice number or client name as the payment reference.\n\n"
                "Regards,\nIthute Digital Solutions"
            )
            html = (
                f"<p>Dear {invoice.client_name},</p>"
                f"<p>This is a reminder for invoice <strong>{invoice.invoice_number}</strong>. "
                f"The outstanding balance is <strong>{_money(outstanding)}</strong> and the due date is "
                f"<strong>{invoice.due_date:%d %B %Y}</strong>.</p>"
                "<p>Please use the invoice number or client name as the payment reference.</p>"
                "<p>Regards,<br><strong>Ithute Digital Solutions</strong></p>"
            )
            try:
                send_finance_message(
                    db,
                    recipient=invoice.recipient_email,
                    subject=subject,
                    text_body=text,
                    html_body=html,
                    attachment_filename=f"{invoice.invoice_number}.pdf",
                    attachment_data=render_invoice_pdf(invoice),
                )
                log_finance_action(
                    db,
                    action=action,
                    resource_type="finance_invoice",
                    resource_id=invoice.id,
                    metadata={"recipient": invoice.recipient_email, "outstanding_minor": outstanding, "due_date": invoice.due_date.isoformat()},
                )
                db.commit()
                sent += 1
            except Exception as exc:
                db.rollback()
                log_finance_action(
                    db,
                    action=f"finance.reminder.{key}.failed",
                    resource_type="finance_invoice",
                    resource_id=invoice.id,
                    metadata={"error": str(exc)[:500], "recipient": invoice.recipient_email},
                )
                db.commit()
        return sent
    finally:
        db.close()
