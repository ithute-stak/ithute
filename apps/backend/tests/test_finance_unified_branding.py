from io import BytesIO
from unittest.mock import patch

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.services import finance_branding


def test_official_document_contact_details():
    assert finance_branding.CONTACT_PHONE == "59001394"
    assert finance_branding.CONTACT_EMAIL == "thekoetlisi@ithute.co.ls"
    assert finance_branding.CONTACT_ADDRESS == "Mokorotlong Maseru 100, Victoria Hotel Room 111"
    assert finance_branding.MPESA_NUMBER == "59001394"
    assert finance_branding.MPESA_NAME == "Koetlisi Theko"


def test_missing_header_does_not_break_pdf(tmp_path):
    buffer = BytesIO()
    document = canvas.Canvas(buffer, pagesize=A4)
    with patch.object(finance_branding, "ASSET", tmp_path / "not-present.jpg"):
        assert finance_branding.draw_brand_header(document, *A4) > 0
    finance_branding.draw_contact_footer(document)
    finance_branding.draw_mpesa_note(document, 40, 65)
    document.save()
    assert buffer.getvalue().startswith(b"%PDF")


def test_shared_header_uses_approved_asset_when_present(tmp_path):
    image = tmp_path / "approved.jpg"
    image.write_bytes(b"placeholder")
    document = canvas.Canvas(BytesIO(), pagesize=A4)
    with patch.object(finance_branding, "ASSET", image), patch.object(
        finance_branding, "ImageReader", return_value="approved"
    ) as reader, patch.object(document, "drawImage") as draw:
        finance_branding.draw_brand_header(document, *A4)
    reader.assert_called_once_with(str(image))
    draw.assert_called_once()
