from io import BytesIO
from unittest.mock import patch

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

from app.services.finance_branding import draw_brand_header, draw_contact_footer


def test_footer_renders_both_contacts_without_literal_escape_artifacts():
    buffer = BytesIO()
    c = Canvas(buffer, pagesize=A4, pageCompression=0)
    draw_contact_footer(c)
    c.save()
    data = buffer.getvalue()
    assert data.startswith(b"%PDF")
    assert b"59001394" in data
    assert b"thekoetlisi@ithute.co.ls" in data
    assert b"Victorial Hotel Room 111" in data


def test_branded_header_draws_approved_art_when_provisioned(tmp_path):
    asset = tmp_path / "banner.jpg"
    asset.write_bytes(b"test placeholder")
    c = Canvas(BytesIO(), pagesize=A4)
    with patch("app.services.finance_branding.ASSET", asset), patch("app.services.finance_branding.ImageReader", return_value="approved") as reader, patch.object(c, "drawImage") as draw:
        draw_brand_header(c, *A4)
    reader.assert_called_once_with(str(asset))
    draw.assert_called_once()
