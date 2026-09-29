from __future__ import annotations

import calendar
import threading
import time
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, text

from app.db.session import SessionLocal
from app.models import FinanceInvoice, FinanceInvoiceSchedule
from app.services.finance_delivery import send_invoice
from app.services.finance_invoices import build_default_email_body, build_default_subject, next_invoice_number

_LOCK_ID = 29092026
_started = False
_start_lock = threading.Lock()


def effective_send_day(year: int, month: int, requested_day: int) -> int:
    """Clamp schedules such as day 31 to the last real day of shorter months."""
    return min(max(1, requested_day), calendar.monthrange(year, month)[1])


def schedule_out(row: FinanceInvoiceSchedule) -> dict:
    return {
        "id": str(row.id),
        "client_name": row.client_name,
        "recipient_email": row.recipient_email,
        "client_address": row.client_address,
        "description": row.description,
        "details": row.details,
        "quantity": row.quantity,
        "rate_minor": row.rate_minor,
        "tax_minor": row.tax_minor,
        "currency": row.currency,
        "send_day": row.send_day,
        "due_days": row.due_days,
        "enabled": row.enabled,
        "last_sent_period": row.last_sent_period,
        "last_error": row.last_error,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _make_invoice(db, schedule: FinanceInvoiceSchedule, issue_date: date) -> FinanceInvoice:
    subtotal = schedule.quantity * schedule.rate_minor
    total = subtotal + schedule.tax_minor
    number = next_invoice_number(db)
    due_date = issue_date + timedelta(days=schedule.due_days)
    service_period = issue_date.strftime("%B %Y")
    invoice = FinanceInvoice(
        invoice_number=number,
        client_name=schedule.client_name,
        recipient_email=schedule.recipient_email,
        client_address=schedule.client_address,
        description=schedule.description,
        details=schedule.details,
        service_period=service_period,
        quantity=schedule.quantity,
        rate_minor=schedule.rate_minor,
        tax_minor=schedule.tax_minor,
        subtotal_minor=subtotal,
        total_minor=total,
        currency=schedule.currency,
        due_date=due_date,
        status="draft",
        email_subject=build_default_subject(number, schedule.client_name),
        email_body=build_default_email_body(
            invoice_number=number,
            client_name=schedule.client_name,
            description=schedule.description,
            total_minor=total,
            currency=schedule.currency,
            due_date=due_date,
        ),
        created_by_user_id=schedule.created_by_user_id,
    )
    db.add(invoice)
    db.flush()
    return invoice


def process_due_finance_schedules(now: datetime | None = None) -> int:
    """Generate and send each due monthly schedule once per calendar month.

    A PostgreSQL advisory lock makes this safe when more than one API worker is
    running. If the service was offline on the configured day, the schedule is
    caught up on the next check in the same month. Failed deliveries remain due
    and are retried on a later scheduler pass.
    """
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    today = current.date()
    period = today.strftime("%Y-%m")
    db = SessionLocal()
    locked = False
    sent = 0
    try:
        locked = bool(db.execute(text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": _LOCK_ID}).scalar())
        if not locked:
            return 0
        schedules = db.scalars(
            select(FinanceInvoiceSchedule)
            .where(FinanceInvoiceSchedule.enabled.is_(True))
            .order_by(FinanceInvoiceSchedule.created_at)
        ).all()
        for schedule in schedules:
            if schedule.last_sent_period == period:
                continue
            if today.day < effective_send_day(today.year, today.month, schedule.send_day):
                continue
            schedule_id = schedule.id
            try:
                invoice = _make_invoice(db, schedule, today)
                send_invoice(db, invoice)
                schedule.last_sent_period = period
                schedule.last_error = None
                db.commit()
                sent += 1
            except Exception as exc:
                db.rollback()
                failed_schedule = db.get(FinanceInvoiceSchedule, schedule_id)
                if failed_schedule is not None:
                    failed_schedule.last_error = str(exc)[:2000]
                    db.commit()
        return sent
    finally:
        if locked:
            try:
                db.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": _LOCK_ID})
            except Exception:
                pass
        db.close()


def _scheduler_loop() -> None:
    # Give migrations and the application a moment to become ready after boot.
    time.sleep(20)
    while True:
        try:
            process_due_finance_schedules()
        except Exception:
            # The next hourly pass retries; scheduler failures must never stop the API.
            pass
        time.sleep(3600)


def install_finance_recurring_scheduler() -> None:
    global _started
    with _start_lock:
        if _started:
            return
        _started = True
        threading.Thread(target=_scheduler_loop, name="finance-recurring", daemon=True).start()
