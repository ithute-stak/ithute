from datetime import date

from app.models import FinanceInvoice
from app.services.finance_reminders import _reminder_key


def invoice(due: date) -> FinanceInvoice:
    return FinanceInvoice(
        invoice_number="IM-2026-TEST",
        client_name="Test Client",
        recipient_email="accounts@example.com",
        client_address="Maseru",
        description="Service",
        details="",
        service_period="September 2026",
        quantity=1,
        rate_minor=18500,
        tax_minor=0,
        subtotal_minor=18500,
        total_minor=18500,
        currency="LSL",
        due_date=due,
        status="sent",
        email_subject="Invoice",
        email_body="Body",
    )


def test_pre_due_and_due_day_reminders():
    today = date(2026, 9, 30)
    assert _reminder_key(invoice(date(2026, 10, 3)), today) == ("pre_due_3", "Payment reminder")
    assert _reminder_key(invoice(today), today) == ("due_today", "Invoice due today")


def test_overdue_reminder_cadence_is_not_daily_spam():
    today = date(2026, 9, 30)
    assert _reminder_key(invoice(date(2026, 9, 27)), today) == ("overdue_3", "Invoice overdue by 3 days")
    assert _reminder_key(invoice(date(2026, 9, 23)), today) == ("overdue_7", "Invoice overdue by 7 days")
    assert _reminder_key(invoice(date(2026, 9, 16)), today) == ("overdue_14", "Invoice overdue by 14 days")
    assert _reminder_key(invoice(date(2026, 8, 31)), today) == ("overdue_30", "Invoice overdue by 30 days")
    assert _reminder_key(invoice(date(2026, 9, 29)), today) is None
