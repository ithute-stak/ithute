from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.corporate_quotation import pack_metadata, render_corporate_quote_pdf, unpack_metadata


def test_corporate_quote_metadata_round_trip():
    raw = pack_metadata({"mailbox_count": 20, "storage_gb": 50, "recipient_cc": ["support@example.co.ls"]}, "Client note")
    data = unpack_metadata(raw)
    assert data["mailbox_count"] == 20
    assert data["storage_gb"] == 50
    assert data["recipient_cc"] == ["support@example.co.ls"]
    assert data["notes"] == "Client note"


def test_corporate_quote_pdf_is_two_page_document():
    notes = pack_metadata({
        "mailbox_count": 20,
        "storage_gb": 50,
        "retail_monthly_minor": 800000,
        "monthly_total_minor": 700000,
        "quarterly_total_minor": 1950000,
        "annual_total_minor": 7200000,
        "validity_days": 30,
        "recipient_cc": ["support@example.co.ls"],
        "prepared_by": "Koetlisi Theko",
        "prepared_email": "thekoetlisi@ithute.co.ls",
        "prepared_phone": "+266 5900 1394",
    })
    document = SimpleNamespace(
        notes=notes,
        recipient_email="letebele@example.co.ls",
        document_number="QT-2026-0001",
        client_name="Global IT",
        created_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        total_minor=7200000,
    )
    pdf = render_corporate_quote_pdf(document)
    assert pdf.startswith(b"%PDF")
    assert b"/Count 2" in pdf
