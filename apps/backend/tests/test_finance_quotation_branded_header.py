from io import BytesIO
from unittest.mock import patch

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

from app.services import finance_documents


def test_quotation_uses_dedicated_branded_header(tmp_path):
    banner = tmp_path / "header.jpg"
    banner.write_bytes(b"valid header placeholder")
    result = BytesIO()
    canvas = Canvas(result, pagesize=A4)
    with patch.object(finance_documents, "_QUOTATION_HEADER_PATH", banner), patch.object(
        finance_documents, "ImageReader", return_value="image"
    ) as image_reader, patch.object(canvas, "drawImage") as draw:
        height = finance_documents._header(canvas, *A4, quotation=True)
    image_reader.assert_called_once_with(str(banner))
    assert height == A4[0] * 600 / 2048
    draw.assert_called_once()


def test_missing_quotation_header_falls_back_without_crashing(tmp_path):
    result = BytesIO()
    canvas = Canvas(result, pagesize=A4)
    with patch.object(finance_documents, "_QUOTATION_HEADER_PATH", tmp_path / "missing.jpg"):
        height = finance_documents._header(canvas, *A4, quotation=True)
    canvas.save()
    assert height > 0
    assert result.getvalue().startswith(b"%PDF")


def test_invoice_header_dimensions_unchanged():
    result = BytesIO()
    canvas = Canvas(result, pagesize=A4)
    with patch.object(finance_documents, "_HEADER_PATH") as header:
        header.is_file.return_value = False
        height = finance_documents._header(canvas, *A4)
    assert height == A4[0] * 270 / 1103
