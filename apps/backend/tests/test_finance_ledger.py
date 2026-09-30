from datetime import date, datetime, timezone

from app.models import FinanceCreditNote, FinanceInvoice, FinancePayment
from app.services.finance_ledger import adjusted_total_minor, credited_minor, effective_invoice_status, paid_minor, sync_invoice_payment_status


def invoice(total=18500, status="sent", due=date(2026, 9, 20)):
    row = FinanceInvoice(
        invoice_number="IM-2026-TEST",
        client_name="Test Client",
        recipient_email="accounts@example.com",
        client_address="Maseru",
        description="Service",
        details="",
        service_period="September 2026",
        quantity=1,
        rate_minor=total,
        tax_minor=0,
        subtotal_minor=total,
        total_minor=total,
        currency="LSL",
        due_date=due,
        status=status,
        email_subject="Invoice",
        email_body="Body",
    )
    row.payments = []
    row.credit_notes = []
    row.items = []
    return row


def payment(amount):
    return FinancePayment(
        amount_minor=amount,
        payment_date=date(2026, 9, 21),
        method="bank_transfer",
        reference="REF",
        note="",
        created_at=datetime(2026, 9, 21, tzinfo=timezone.utc),
    )


def credit(amount):
    return FinanceCreditNote(
        credit_number="CN-2026-TEST",
        amount_minor=amount,
        reason="Service adjustment",
        created_at=datetime(2026, 9, 22, tzinfo=timezone.utc),
    )


def test_partial_and_full_payment_status():
    row = invoice()
    row.payments.append(payment(5000))
    assert paid_minor(row) == 5000
    sync_invoice_payment_status(row)
    assert row.status == "partial"
    assert effective_invoice_status(row, today=date(2026, 9, 30)) == "partial"

    row.payments.append(payment(13500))
    sync_invoice_payment_status(row)
    assert row.status == "paid"
    assert effective_invoice_status(row, today=date(2026, 9, 30)) == "paid"


def test_credit_note_reduces_collectable_balance():
    row = invoice(total=18500)
    row.credit_notes.append(credit(3500))
    assert credited_minor(row) == 3500
    assert adjusted_total_minor(row) == 15000
    row.payments.append(payment(15000))
    sync_invoice_payment_status(row)
    assert row.status == "paid"


def test_full_credit_marks_invoice_credited():
    row = invoice(total=18500)
    row.credit_notes.append(credit(18500))
    sync_invoice_payment_status(row)
    assert adjusted_total_minor(row) == 0
    assert row.status == "credited"
    assert effective_invoice_status(row, today=date(2026, 9, 30)) == "credited"


def test_unpaid_sent_invoice_becomes_overdue_for_reporting():
    row = invoice(status="sent", due=date(2026, 9, 20))
    assert effective_invoice_status(row, today=date(2026, 9, 30)) == "overdue"


def test_draft_invoice_is_not_reported_overdue():
    row = invoice(status="draft", due=date(2026, 9, 20))
    assert effective_invoice_status(row, today=date(2026, 9, 30)) == "draft"
