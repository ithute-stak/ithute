from io import BytesIO
from unittest.mock import patch

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.services.finance_branding import draw_authorized_signature, verified_signature


def test_missing_signature_blocks_signed_document(tmp_path):
    with patch("app.services.finance_branding.SIGNATURE_ASSET", tmp_path / "missing.png"):
        with pytest.raises(ValueError, match="signature is unavailable"):
            verified_signature()


def test_corrupt_signature_blocks_signed_document(tmp_path):
    signature = tmp_path / "signature.png"
    signature.write_bytes(b"not a valid png")
    with patch("app.services.finance_branding.SIGNATURE_ASSET", signature):
        with pytest.raises(ValueError, match="signature is unavailable"):
            verified_signature()


def test_signature_block_contains_approved_artwork():
    document = canvas.Canvas(BytesIO(), pagesize=A4)
    with patch("app.services.finance_branding.verified_signature", return_value="image") as verified, patch.object(document, "drawImage") as draw:
        draw_authorized_signature(document, 42, 140)
    verified.assert_called_once()
    draw.assert_called_once()
