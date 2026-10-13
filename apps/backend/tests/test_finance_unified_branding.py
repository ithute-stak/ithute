from io import BytesIO
from unittest.mock import patch, MagicMock

import pytest

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.services import finance_branding


def test_official_document_contact_details():
    assert finance_branding.CONTACT_PHONE == "59001394"
    assert finance_branding.CONTACT_EMAIL == "thekoetlisi@ithute.co.ls"
    assert finance_branding.CONTACT_ADDRESS == "Mokorotlong Maseru 100, Victorial Hotel Room 111"
    assert finance_branding.MPESA_NUMBER == "59001394"
    assert finance_branding.MPESA_NAME == "Koetlisi Theko"


def test_missing_header_blocks_pdf_instead_of_using_plain_banner(tmp_path):
    document = canvas.Canvas(BytesIO(), pagesize=A4)
    with patch.object(finance_branding, "ASSET", tmp_path / "not-present.jpg"):
        with pytest.raises(ValueError, match="approved Ithute/iMail header image"):
            finance_branding.draw_brand_header(document, *A4)


def test_shared_header_uses_approved_asset_when_present(tmp_path):
    image = tmp_path / "approved.jpg"
    image.write_bytes(b"placeholder")
    document = canvas.Canvas(BytesIO(), pagesize=A4)
    with patch.object(finance_branding, "ASSET", image), patch.object(
        finance_branding, "ImageReader", return_value=MagicMock()
    ) as reader, patch.object(document, "drawImage") as draw:
        finance_branding.draw_brand_header(document, *A4)
    reader.assert_called_once_with(str(image))
    draw.assert_called_once()


def test_original_approved_header_is_packaged_with_exact_bytes():
    from hashlib import sha256
    from reportlab.lib.utils import ImageReader

    assert finance_branding.ASSET.is_file()
    assert sha256(finance_branding.ASSET.read_bytes()).hexdigest() == (
        "36396920cb7ece9688751e51e4636512cd35764bf294e7be06bfc06e307d7531"
    )
    assert ImageReader(str(finance_branding.ASSET)).getSize() == (2048, 600)
