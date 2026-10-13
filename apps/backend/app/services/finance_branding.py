"""Single source of truth for Ithute finance PDF branding."""
from pathlib import Path
import os
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader

CONTACT_PHONE = "59001394"
CONTACT_EMAIL = "thekoetlisi@ithute.co.ls"
CONTACT_ADDRESS = "Mokorotlong Maseru 100, Victorial Hotel Room 111"
MPESA_NUMBER = "59001394"
MPESA_NAME = "Koetlisi Theko"
ASSET = Path(__file__).resolve().parents[1] / "assets" / "ithute_imail_quotation_header.jpg"


def draw_brand_header(c, width, height):
    """Shared header for quotations, invoices, receipts and credit notes.

    Always keep PDF generation functional when a raster file is missing or
    damaged, but never represent a fallback as the actual approved artwork.
    """
    banner_height = width * 600 / 2048
    configured_header = os.environ.get("ITHUTE_FINANCE_HEADER_PATH") or os.environ.get("ITHUTE_QUOTATION_HEADER_PATH")
    source = Path(configured_header) if configured_header else ASSET
    try:
        if not source.is_file():
            raise FileNotFoundError(f"Approved Ithute/iMail image missing: {source}")
        reader = ImageReader(str(source))
        reader.getSize()
        c.drawImage(reader, 0, height-banner_height, width=width, height=banner_height)
    except (OSError, ValueError) as exc:
        raise ValueError(
            "The approved Ithute/iMail header image is not installed or is unreadable. "
            "PDF generation has been blocked to prevent an unbranded document. "
            "Install apps/backend/app/assets/ithute_imail_quotation_header.jpg "
            "or configure ITHUTE_FINANCE_HEADER_PATH."
        ) from exc
    return banner_height


def draw_contact_footer(c, left=35, right=560, y=25):
    """Two tidy contact lines; mask legacy footers without overlapping text."""
    c.saveState()
    width, _ = c._pagesize
    c.setFillColor(HexColor("#FFFFFF"))
    c.rect(0, 9, width, 40, stroke=0, fill=1)
    c.setFillColor(HexColor("#092F58"))
    c.setFont("Helvetica-Bold", 7.2)
    c.drawString(left, y + 12, f"Tel: {CONTACT_PHONE}  |  {CONTACT_EMAIL}")
    c.setFont("Helvetica", 7)
    c.drawString(left, y, CONTACT_ADDRESS)
    c.restoreState()


def draw_mpesa_note(c, x, y):
    """Add an explicit payment method without replacing existing bank options."""
    c.saveState()
    c.setFillColor(HexColor("#064F3B"))
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x, y, f"M-Pesa: {MPESA_NUMBER}  |  {MPESA_NAME}")
    c.restoreState()

# Signature is an issuance requirement: never emit an unsigned finance PDF.
SIGNATURE_ASSET = Path(__file__).resolve().parents[1] / "assets" / "koetlisi_theko_mofoka_signature.png"
SIGNATORY_NAME = "Koetlisi Theko Mofoka"
SIGNATORY_TITLE = "CEO, Ithute Digital Solutions"


def verified_signature():
    """Return approved artwork, or stop rendering instead of silently omitting it."""
    source = Path(os.environ.get("ITHUTE_FINANCE_SIGNATURE_PATH") or SIGNATURE_ASSET)
    try:
        if not source.is_file():
            raise ValueError("Approved signature image is missing")
        img = ImageReader(str(source))
        img.getSize()  # fail eagerly on corrupt image
        return img
    except Exception as exc:
        raise ValueError("Approved finance signature is unavailable; signed PDF cannot be issued") from exc


def draw_authorized_signature(c, x, line_y):
    """Signed block for finance documents that have no signature region."""
    c.drawImage(verified_signature(), x + 10, line_y + 5, width=110, height=44, preserveAspectRatio=True, mask="auto")
    c.saveState()
    c.setStrokeColor(HexColor("#082E63"))
    c.line(x, line_y, x + 195, line_y)
    c.setFillColor(HexColor("#082E63"))
    c.setFont("Helvetica-Bold", 8.4)
    c.drawString(x, line_y - 13, SIGNATORY_NAME)
    c.setFont("Helvetica", 7.5)
    c.drawString(x, line_y - 25, SIGNATORY_TITLE)
    c.restoreState()
