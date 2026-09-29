from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.services import finance_invoice_v2 as invoice_v2
from app.services.finance_invoice_v2 import (
    _HEADER_PATH,
    _SIGNATURE_PATH,
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


def test_invoice_artwork_and_signature_assets_are_packaged():
    # The header asset is optional at runtime because the renderer has a vector
    # fallback; the real handwritten signature remains required.
    assert _HEADER_PATH.is_file()
    assert _SIGNATURE_PATH.is_file()
    assert _SIGNATURE_PATH.stat().st_size > 4_000


def test_invoice_pdf_renders_with_real_signature():
    pdf = render_invoice_pdf(sample_invoice())
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 5_000
    assert b"%%EOF" in pdf


def test_truncated_header_asset_cannot_break_invoice_generation(monkeypatch, tmp_path):
    broken_header = tmp_path / "finance_invoice_header.jpg"
    broken_header.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01truncated")
    monkeypatch.setattr(invoice_v2, "_HEADER_PATH", broken_header)

    pdf = invoice_v2.render_invoice_pdf(sample_invoice())

    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 5_000
    assert b"%%EOF" in pdf


def test_missing_header_asset_cannot_break_invoice_generation(monkeypatch, tmp_path):
    monkeypatch.setattr(invoice_v2, "_HEADER_PATH", tmp_path / "missing-header.jpg")

    pdf = invoice_v2.render_invoice_pdf(sample_invoice())

    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 5_000
    assert b"%%EOF" in pdf


def test_stamp_is_optional_and_does_not_break_renderer():
    # The approved default reference has no stamp; it remains an opt-in capability only.
    default_pdf = render_invoice_pdf(sample_invoice())
    stamped_pdf = render_invoice_pdf(sample_invoice(), include_stamp=True)
    assert stamped_pdf.startswith(b"%PDF-")
    assert len(stamped_pdf) > len(default_pdf)
