from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from reportlab.lib.utils import ImageReader

from app.services.finance_invoice_v2 import render_invoice_pdf as render_invoice_pdf_v2
from app.services.finance_invoices import (
    BANK_ACCOUNT_NUMBER,
    FINANCE_SENDER,
    build_default_email_body,
    build_default_subject,
    render_invoice_pdf,
)


def sample_invoice():
    return SimpleNamespace(
        invoice_number="IM-2026-0001",
        client_name="Sample Client (Pty) Ltd",
        recipient_email="client@example.com",
        client_address="Maseru, Lesotho",
        description="iMail Professional Business Email Service",
        details="Monthly managed iMail service and business mailbox access",
        service_period="September 2026",
        quantity=1,
        rate_minor=18500,
        tax_minor=0,
        subtotal_minor=18500,
        total_minor=18500,
        currency="LSL",
        due_date=date(2026, 10, 7),
        created_at=datetime(2026, 9, 29, tzinfo=timezone.utc),
        email_subject="Ithute Invoice IM-2026-0001 - Sample Client (Pty) Ltd",
        email_body="Sample body",
    )


def test_default_invoice_email_is_specific_and_payment_ready():
    subject = build_default_subject("IM-2026-0001", "Sample Client (Pty) Ltd")
    body = build_default_email_body(
        invoice_number="IM-2026-0001",
        client_name="Sample Client (Pty) Ltd",
        description="iMail Professional Business Email Service",
        total_minor=18500,
        currency="LSL",
        due_date=date(2026, 10, 7),
    )
    assert subject == "Ithute Invoice IM-2026-0001 - Sample Client (Pty) Ltd"
    assert "M 185.00" in body
    assert "07 October 2026" in body
    assert BANK_ACCOUNT_NUMBER in body
    assert FINANCE_SENDER in body
    assert "IM-2026-0001" in body


def test_invoice_pdf_is_a_real_pdf_and_contains_multiple_objects():
    pdf = render_invoice_pdf(sample_invoice())
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 5000
    assert b"%%EOF" in pdf


def test_live_v2_header_asset_is_decodable():
    asset = Path(__file__).resolve().parents[1] / "app" / "assets" / "finance_invoice_header.jpg"
    reader = ImageReader(str(asset))
    width, height = reader.getSize()
    assert width > 0
    assert height > 0


def test_live_v2_invoice_pdf_renders_successfully():
    pdf = render_invoice_pdf_v2(sample_invoice())
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 5000
    assert b"%%EOF" in pdf
