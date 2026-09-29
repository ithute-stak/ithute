from datetime import datetime, timezone
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from app.models import FinanceInvoice
from app.services.finance_invoices import (
    AUTHORISED_NAME,
    AUTHORISED_TITLE,
    BANK_ACCOUNT_NAME,
    BANK_ACCOUNT_NUMBER,
    BANK_NAME,
    COMPANY_LOCATION,
    COMPANY_WEBSITE,
    FINANCE_SENDER,
    build_email_html,
    finance_tenant_id,
    money,
)
from app.services.transactional_mail import send_message

NAVY = HexColor("#062D63")
GREEN = HexColor("#087743")
DARK_GREEN = HexColor("#075135")
GOLD = HexColor("#D5A62F")
MUTED = HexColor("#667A96")
TEXT = HexColor("#102E59")
LINE = HexColor("#C8DCEC")
PALE_BLUE = HexColor("#F1F7FC")
PALE_GREEN = HexColor("#EFF8E6")

_ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"
_HEADER_PATH = _ASSET_DIR / "finance_invoice_header.jpg"
_SIGNATURE_PATH = _ASSET_DIR / "koetlisi_theko_mofoka_signature.png"


def _asset(path: Path) -> ImageReader:
    if not path.is_file():
        raise RuntimeError(f"Required invoice artwork is missing: {path.name}")
    return ImageReader(str(path))


def _fit_text(c: canvas.Canvas, text: str, font: str, size: float, max_width: float, min_size: float = 6.5) -> float:
    value = size
    while value > min_size and c.stringWidth(text, font, value) > max_width:
        value -= 0.25
    return value


def _draw_person_icon(c: canvas.Canvas, cx: float, cy: float) -> None:
    c.saveState()
    c.setFillColor(HexColor("#E6F2FB"))
    c.circle(cx, cy, 16, fill=1, stroke=0)
    c.setStrokeColor(NAVY)
    c.setLineWidth(1.2)
    c.circle(cx, cy + 4, 3.4, fill=0, stroke=1)
    c.roundRect(cx - 6, cy - 7, 12, 7, 3, fill=0, stroke=1)
    c.restoreState()


def _draw_payment_icon(c: canvas.Canvas, cx: float, cy: float) -> None:
    c.saveState()
    c.setFillColor(HexColor("#EAF8E8"))
    c.circle(cx, cy, 16, fill=1, stroke=0)
    c.setStrokeColor(GREEN)
    c.setLineWidth(1.4)
    c.line(cx - 8, cy - 2, cx + 8, cy - 2)
    c.line(cx - 7, cy - 9, cx + 7, cy - 9)
    c.line(cx - 7, cy + 2, cx, cy + 8)
    c.line(cx, cy + 8, cx + 7, cy + 2)
    for dx in (-5, 0, 5):
        c.line(cx + dx, cy - 2, cx + dx, cy - 9)
    c.restoreState()


def _draw_note_icon(c: canvas.Canvas, cx: float, cy: float) -> None:
    c.saveState()
    c.setFillColor(HexColor("#E6F2FB"))
    c.circle(cx, cy, 16, fill=1, stroke=0)
    c.setStrokeColor(NAVY)
    c.setLineWidth(1.2)
    c.roundRect(cx - 7, cy - 7, 13, 14, 3, fill=0, stroke=1)
    c.line(cx - 4, cy + 2, cx + 3, cy + 2)
    c.line(cx - 4, cy - 2, cx + 2, cy - 2)
    c.restoreState()


def _draw_footer_icon(c: canvas.Canvas, x: float, y: float, kind: str) -> None:
    c.saveState()
    c.setStrokeColor(NAVY)
    c.setFillColor(NAVY)
    c.setLineWidth(1)
    if kind == "web":
        c.circle(x + 5, y + 5, 5, fill=0, stroke=1)
        c.line(x, y + 5, x + 10, y + 5)
        c.ellipse(x + 3, y, x + 7, y + 10, fill=0, stroke=1)
    elif kind == "mail":
        c.rect(x, y + 1, 11, 8, fill=0, stroke=1)
        c.line(x, y + 9, x + 5.5, y + 4)
        c.line(x + 11, y + 9, x + 5.5, y + 4)
    else:
        c.circle(x + 5, y + 6, 4, fill=0, stroke=1)
        c.circle(x + 5, y + 6, 1.2, fill=1, stroke=0)
        c.line(x + 2, y + 3, x + 5, y - 1)
        c.line(x + 8, y + 3, x + 5, y - 1)
    c.restoreState()


def _draw_signature(c: canvas.Canvas, x: float, line_y: float) -> None:
    # The approved handwritten signature is required. Never silently replace it with typed text.
    c.drawImage(
        _asset(_SIGNATURE_PATH),
        x + 12,
        line_y + 5,
        width=128,
        height=55,
        preserveAspectRatio=True,
        mask="auto",
    )
    c.setStrokeColor(NAVY)
    c.setLineWidth(.75)
    c.line(x, line_y, x + 205, line_y)
    c.setFillColor(TEXT)
    c.setFont("Helvetica-Bold", 9.2)
    c.drawString(x, line_y - 15, AUTHORISED_NAME)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(x, line_y - 29, AUTHORISED_TITLE)


def render_invoice_pdf(invoice: FinanceInvoice, *, include_stamp: bool = False) -> bytes:
    """Render the owner-approved Ithute/iMail invoice design."""
    from io import BytesIO

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    left, right = 30, width - 30
    c.setTitle(f"Invoice {invoice.invoice_number}")
    c.setFillColor(colors.white)
    c.rect(0, 0, width, height, fill=1, stroke=0)

    # Use the approved banner itself instead of approximating/redrawing its logos.
    header_h = width * 270 / 1103
    c.drawImage(_asset(_HEADER_PATH), 0, height - header_h, width=width, height=header_h, preserveAspectRatio=False)

    title_y = height - header_h - 38
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 31)
    c.drawString(left, title_y, "INVOICE")
    c.setStrokeColor(HexColor("#0E65B5")); c.setLineWidth(2); c.line(left, title_y - 11, left + 110, title_y - 11)
    c.setStrokeColor(GREEN); c.line(left + 110, title_y - 11, left + 182, title_y - 11)
    c.setStrokeColor(GOLD); c.line(left + 182, title_y - 11, left + 226, title_y - 11)
    c.setFillColor(MUTED); c.setFont("Helvetica", 9.8)
    c.drawString(left, title_y - 29, "Professional Email Solutions for Your Business")

    meta_w, meta_h = 210, 82
    meta_x, meta_y = right - meta_w, title_y - 45
    c.setFillColor(PALE_BLUE); c.setStrokeColor(HexColor("#BDD4E7")); c.setLineWidth(.7)
    c.roundRect(meta_x, meta_y, meta_w, meta_h, 8, fill=1, stroke=1)
    issue_date = invoice.created_at.strftime("%d %B %Y") if invoice.created_at else datetime.now(timezone.utc).strftime("%d %B %Y")
    meta = [("Invoice No.", invoice.invoice_number), ("Issue Date", issue_date), ("Due Date", invoice.due_date.strftime("%d %B %Y"))]
    my = meta_y + meta_h - 22
    for index, (label, value) in enumerate(meta):
        c.setFillColor(MUTED); c.setFont("Helvetica-Bold", 8.6); c.drawString(meta_x + 15, my, label)
        c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 9.4); c.drawRightString(meta_x + meta_w - 15, my, value)
        if index < 2:
            c.setStrokeColor(LINE); c.setLineWidth(.5); c.line(meta_x + 15, my - 9, meta_x + meta_w - 15, my - 9)
        my -= 24

    bill_y = title_y - 126
    _draw_person_icon(c, left + 16, bill_y + 5)
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 9.2); c.drawString(left + 50, bill_y + 13, "BILLED TO")
    client_size = _fit_text(c, invoice.client_name, "Helvetica-Bold", 11.5, 265)
    c.setFillColor(TEXT); c.setFont("Helvetica-Bold", client_size); c.drawString(left + 50, bill_y - 7, invoice.client_name)
    c.setFillColor(MUTED); c.setFont("Helvetica", 9.3); c.drawString(left + 50, bill_y - 25, invoice.recipient_email)
    if invoice.client_address:
        c.drawString(left + 50, bill_y - 43, invoice.client_address[:75])

    table_top, table_h = bill_y - 78, 77
    table_w = right - left
    c.setFillColor(colors.white); c.setStrokeColor(HexColor("#BBD4E7")); c.setLineWidth(.8)
    c.roundRect(left, table_top - table_h, table_w, table_h, 7, fill=1, stroke=1)
    c.setFillColor(PALE_BLUE); c.roundRect(left, table_top - 29, table_w, 29, 7, fill=1, stroke=0); c.rect(left, table_top - 29, table_w, 8, fill=1, stroke=0)
    x_qty, x_rate, x_amount = 339, 430, 526
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 8.5)
    c.drawString(left + 15, table_top - 18, "DESCRIPTION")
    c.drawCentredString(x_qty, table_top - 18, "QTY")
    c.drawCentredString(x_rate, table_top - 18, "RATE (M)")
    c.drawCentredString(x_amount, table_top - 18, "AMOUNT (M)")
    c.setStrokeColor(LINE)
    for vx in (310, 365, 467):
        c.line(vx, table_top, vx, table_top - table_h)
    desc_size = _fit_text(c, invoice.description, "Helvetica-Bold", 9.7, 255)
    c.setFillColor(TEXT); c.setFont("Helvetica-Bold", desc_size); c.drawString(left + 15, table_top - 49, invoice.description)
    detail = invoice.details or invoice.service_period
    if detail:
        detail_size = _fit_text(c, detail, "Helvetica", 7.9, 260)
        c.setFillColor(MUTED); c.setFont("Helvetica", detail_size); c.drawString(left + 15, table_top - 64, detail)
    c.setFillColor(TEXT); c.setFont("Helvetica", 9.2); c.drawCentredString(x_qty, table_top - 52, str(invoice.quantity))
    c.drawRightString(454, table_top - 52, money(invoice.rate_minor, invoice.currency))
    c.setFont("Helvetica-Bold", 9.2); c.drawRightString(right - 14, table_top - 52, money(invoice.subtotal_minor, invoice.currency))

    totals_w, totals_h = 260, 88
    totals_x, totals_y = right - totals_w, table_top - table_h - 92
    c.setFillColor(colors.white); c.setStrokeColor(LINE)
    c.roundRect(totals_x, totals_y, totals_w, totals_h, 7, fill=1, stroke=1)
    tax_pct = 0 if invoice.subtotal_minor <= 0 else round((invoice.tax_minor / invoice.subtotal_minor) * 100)
    for label, value, ry in (("Subtotal", money(invoice.subtotal_minor, invoice.currency), totals_y + 64), (f"Tax ({tax_pct}%)", money(invoice.tax_minor, invoice.currency), totals_y + 42)):
        c.setFillColor(MUTED); c.setFont("Helvetica", 8.8); c.drawString(totals_x + 17, ry, label)
        c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 8.8); c.drawRightString(totals_x + totals_w - 17, ry, value)
    c.setFillColor(PALE_GREEN); c.roundRect(totals_x + 1, totals_y + 1, totals_w - 2, 31, 6, fill=1, stroke=0)
    c.setFillColor(DARK_GREEN); c.setFont("Helvetica-Bold", 10.5); c.drawString(totals_x + 17, totals_y + 11, "TOTAL DUE")
    c.setFont("Helvetica-Bold", 16); c.drawRightString(totals_x + totals_w - 17, totals_y + 9, money(invoice.total_minor, invoice.currency))

    card_y, card_h, gap = totals_y - 126, 108, 14
    card_w = (table_w - gap) / 2
    note_x = left + card_w + gap
    c.setFillColor(colors.white); c.setStrokeColor(LINE)
    c.roundRect(left, card_y, card_w, card_h, 7, fill=1, stroke=1)
    c.roundRect(note_x, card_y, card_w, card_h, 7, fill=1, stroke=1)
    _draw_payment_icon(c, left + 28, card_y + card_h - 27)
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 9.2); c.drawString(left + 52, card_y + card_h - 25, "PAYMENT DETAILS")
    payment = [("Bank", BANK_NAME), ("Account Name", BANK_ACCOUNT_NAME), ("Account Number", BANK_ACCOUNT_NUMBER), ("Billing Email", FINANCE_SENDER)]
    py = card_y + card_h - 48
    for label, value in payment:
        c.setFillColor(MUTED); c.setFont("Helvetica", 7.8); c.drawString(left + 15, py, label)
        c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 8.3); c.drawString(left + 108, py, value)
        py -= 17
    _draw_note_icon(c, note_x + 28, card_y + card_h - 27)
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 9.2); c.drawString(note_x + 52, card_y + card_h - 25, "NOTE")
    c.setFillColor(MUTED); c.setFont("Helvetica", 8.1)
    note_lines = ["Thank you for choosing iMail by Ithute Solutions.", "Please use the invoice number or client name as the", "payment reference when making payment."]
    ny = card_y + card_h - 52
    for line in note_lines:
        c.drawString(note_x + 15, ny, line)
        ny -= 15

    # The real handwritten signature is part of the template. There is no typed fallback.
    signature_line_y = card_y - 67
    _draw_signature(c, left + 8, signature_line_y)

    if include_stamp:
        # Optional capability only; the approved default invoice does not show a stamp.
        cx, cy = right - 55, signature_line_y + 16
        c.saveState(); c.setStrokeColor(GREEN); c.setFillColor(GREEN); c.setLineWidth(1.1)
        c.circle(cx, cy, 31, fill=0, stroke=1); c.circle(cx, cy, 26, fill=0, stroke=1)
        c.setFont("Helvetica-Bold", 5); c.drawCentredString(cx, cy + 17, "ITHUTE DIGITAL SOLUTIONS")
        c.setFont("Helvetica-Bold", 6.4); c.drawCentredString(cx, cy + 2, "AUTHORISED"); c.drawCentredString(cx, cy - 8, "FINANCE")
        c.setFont("Helvetica", 4.5); c.drawCentredString(cx, cy - 19, invoice.invoice_number)
        c.restoreState()

    footer_line_y = 38
    c.setStrokeColor(LINE); c.setLineWidth(.7); c.line(left, footer_line_y, right, footer_line_y)
    _draw_footer_icon(c, left, 17, "web"); _draw_footer_icon(c, 154, 17, "mail"); _draw_footer_icon(c, 312, 17, "pin")
    c.setFillColor(NAVY); c.setFont("Helvetica", 7.2)
    c.drawString(left + 16, 21, COMPANY_WEBSITE); c.drawString(171, 21, FINANCE_SENDER); c.drawString(329, 21, COMPANY_LOCATION)
    c.setFillColor(HexColor("#8093AA")); c.setFont("Helvetica", 6.8); c.drawRightString(right, 21, "LEARN ANYWHERE. SUCCEED EVERYWHERE.")
    c.setFillColor(NAVY); c.rect(0, 0, width * .31, 5, fill=1, stroke=0)
    c.setFillColor(GREEN); c.rect(width * .31, 0, width * .43, 5, fill=1, stroke=0)
    c.setFillColor(GOLD); c.rect(width * .74, 0, width * .26, 5, fill=1, stroke=0)

    c.save()
    return buffer.getvalue()


def send_invoice(db: Session, invoice: FinanceInvoice) -> None:
    tenant_id = finance_tenant_id(db)
    pdf = render_invoice_pdf(invoice)
    try:
        send_message(
            db,
            tenant_id=tenant_id,
            api_key_id=None,
            sender=FINANCE_SENDER,
            recipients=[invoice.recipient_email],
            subject=invoice.email_subject,
            text_body=invoice.email_body,
            html_body=build_email_html(invoice),
            attachments=[(f"{invoice.invoice_number}.pdf", "application/pdf", pdf)],
        )
        invoice.status = "sent"
        invoice.sent_at = datetime.now(timezone.utc)
        invoice.last_error = None
    except Exception as exc:
        invoice.status = "failed"
        invoice.last_error = str(exc)[:2000]
        raise
