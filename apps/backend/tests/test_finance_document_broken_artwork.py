"""Regression tests: malformed optional branding must not prevent PDF rendering."""
from io import BytesIO
from unittest.mock import patch

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.services import finance_documents


def test_broken_header_image_uses_branded_fallback():
    pdf = BytesIO()
    c = canvas.Canvas(pdf, pagesize=A4)
    with patch.object(finance_documents, "ImageReader", side_effect=OSError("cannot identify image")):
        height = finance_documents._header(c, *A4)
    assert height > 0
    c.showPage()
    c.save()
    assert pdf.getvalue().startswith(b"%PDF")


def test_missing_header_image_uses_branded_fallback():
    pdf = BytesIO()
    c = canvas.Canvas(pdf, pagesize=A4)
    with patch.object(type(finance_documents._HEADER_PATH), "is_file", return_value=False):
        finance_documents._header(c, *A4)
    c.save()
    assert pdf.getvalue().startswith(b"%PDF")


def test_broken_signature_image_does_not_block_document():
    pdf = BytesIO()
    c = canvas.Canvas(pdf, pagesize=A4)
    with patch.object(finance_documents, "ImageReader", side_effect=OSError("cannot identify image")):
        finance_documents._signature(c, 60, 140)
    c.save()
    assert pdf.getvalue().startswith(b"%PDF")
