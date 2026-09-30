from datetime import date, datetime, timezone

from app.models import FinanceClient, FinanceInvoice, FinancePayment
from app.services.finance_statements import client_payment_behaviour, render_statement_pdf


def _client():
    return FinanceClient(
        name="Governance Test Client",
        email="accounts@example.com",
        address="Maseru",
        phone="",
        default_service="",
        default_details="",
        default_quantity=1,
        default_rate_minor=0,
        default_tax_minor=0,
        payment_terms_days=7,
        active=True,
        notes="",
    )


def _invoice(number: str, due: date, amount: int, payment_date: date | None = None):
    row = FinanceInvoice(
        invoice_number=number,
        client_name="Governance Test Client",
        recipient_email="accounts@example.com",
        client_address="Maseru",
        description="Service",
        details="",
        service_period="September 2026",
        quantity=1,
        rate_minor=amount,
        tax_minor=0,
        subtotal_minor=amount,
        total_minor=amount,
        currency="LSL",
        due_date=due,
        status="sent",
        email_subject="Invoice",
        email_body="Body",
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    row.items = []
    row.credit_notes = []
    row.payments = []
    if payment_date:
        row.payments.append(FinancePayment(amount_minor=amount, payment_date=payment_date, method="bank_transfer", reference="TEST", note="", created_at=datetime.combine(payment_date, datetime.min.time(), tzinfo=timezone.utc)))
        row.status = "paid"
    return row


def test_payment_behaviour_is_factual_and_balanced():
    client = _client()
    paid_on_time = _invoice("IM-TEST-1", date(2026, 9, 10), 10000, date(2026, 9, 8))
    overdue = _invoice("IM-TEST-2", date(2026, 9, 15), 20000)
    result = client_payment_behaviour(client, [paid_on_time, overdue], today=date(2026, 9, 30))
    assert result["invoice_count"] == 2
    assert result["settled_invoice_count"] == 1
    assert result["on_time_invoice_count"] == 1
    assert result["open_overdue_invoice_count"] == 1
    assert result["max_days_overdue"] == 15
    assert result["current_exposure_minor"] == 20000
    assert result["on_time_percent"] == 100.0


def test_statement_pdf_renders_with_finance_branding():
    client = _client()
    invoice = _invoice("IM-TEST-PDF", date(2026, 9, 30), 18500)
    pdf = render_statement_pdf(client, [invoice], as_of=date(2026, 9, 30))
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 5000
