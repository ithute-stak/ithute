"""Actual in-memory invoice PDF rendering and signature/footer placement checks."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from reportlab.pdfgen.canvas import Canvas

from app.services.finance_invoice_v2 import render_invoice_pdf
from app.services.finance_branding import SIGNATORY_NAME, SIGNATORY_TITLE


def _sample_invoice():
    now = datetime(2026, 10, 13, tzinfo=timezone.utc)
    return SimpleNamespace(
        invoice_number="INV-TEST-0001",
        created_at=now,
        due_date=now + timedelta(days=7),
        client_name="Matebele Trading",
        recipient_email="matebeletrading@gmail.com",
        client_address="Maseru, Lesotho",
        description="iMail Professional Business Email Service",
        details="Annual Email Package, @matebeletrading.co.ls",
        service_period=None,
        quantity=1,
        rate_minor=157000,
        subtotal_minor=157000,
        tax_minor=0,
        total_minor=157000,
        currency="LSL",
    )


def test_invoice_pdf_embeds_artwork_and_keeps_signature_text_above_footer():
    drawn = []
    drawn_images = []
    real_string = Canvas.drawString
    real_image = Canvas.drawImage

    def capture_string(canvas, x, y, value, *args, **kwargs):
        drawn.append((str(value), float(y)))
        return real_string(canvas, x, y, value, *args, **kwargs)

    def capture_image(canvas, image, x, y, *args, **kwargs):
        drawn_images.append((float(x), float(y), float(kwargs.get("height", 0))))
        return real_image(canvas, image, x, y, *args, **kwargs)

    with patch.object(Canvas, "drawString", capture_string), patch.object(Canvas, "drawImage", capture_image):
        result = render_invoice_pdf(_sample_invoice())

    assert result.startswith(b"%PDF")
    assert len(result) > 10000
    assert len(drawn_images) >= 2, "Expected approved header and handwritten signature artwork"
    assert any(v == "M-PESA" for v, _ in drawn)
    assert any(v == "59001394" for v, _ in drawn)
    assert any(v == "Koetlisi Theko" for v, _ in drawn)
    assert any(v == "Tel: 59001394  |  thekoetlisi@ithute.co.ls" for v, _ in drawn)
    assert any(v == "Mokorotlong Maseru 100, Victorial Hotel Room 111" for v, _ in drawn)
    # Footer paints a white rectangle from page y=7 through y=53.
    for label in (SIGNATORY_NAME, SIGNATORY_TITLE):
        positions = [y for text, y in drawn if text == label]
        assert positions and min(positions) > 53, f"{label} would be painted over by footer"
