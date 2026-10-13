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
            raise OSError("Approved header is missing")
        c.drawImage(ImageReader(str(source)), 0, height-banner_height, width=width, height=banner_height)
    except (OSError, ValueError):
        c.saveState()
        c.setFillColor(HexColor("#082E63"))
        c.rect(0, height-banner_height, width, banner_height, fill=1, stroke=0)
        c.setFillColor(HexColor("#FFFFFF"))
        c.setFont("Helvetica-Bold", 25)
        c.drawString(40, height-65, "ITHUTE SOLUTIONS")
        c.setFont("Helvetica", 12)
        c.drawString(40, height-88, "iMail")
        c.restoreState()
    return banner_height


def draw_contact_footer(c, left=35, right=560, y=25):
    """Accessible single-line contact footer, preserving document page geometry."""
    c.saveState()
    # Replace legacy footer labels without covering the bottom brand stripe.\n    c.setFillColor(HexColor("#FFFFFF"))\n    c.rect(0, 9, 595, 37, stroke=0, fill=1)\n    c.setFillColor(HexColor("#092F58"))\n    c.setFont("Helvetica-Bold", 7)
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
