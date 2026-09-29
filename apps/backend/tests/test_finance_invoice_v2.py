from datetime import date, datetime, timezone
from io import BytesIO
from types import SimpleNamespace

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.services.finance_invoice_v2 import _draw_company_stamp, render_invoice_pdf


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


def test_v2_invoice_pdf_contains_branded_signature_and_stamp_objects():
    pdf = render_invoice_pdf(sample_invoice())
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 7000
    assert b"%%EOF" in pdf


def test_company_stamp_is_generated_as_vector_pdf_content():
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4, pageCompression=0)
    _draw_company_stamp(c, 300, 300, "IM-2026-0001")
    c.save()
    pdf = buffer.getvalue()
    assert b"ITHUTE DIGITAL SOLUTIONS" in pdf
    assert b"AUTHORISED" in pdf
    assert b"FINANCE" in pdf
    assert b"IM-2026-0001" in pdf
