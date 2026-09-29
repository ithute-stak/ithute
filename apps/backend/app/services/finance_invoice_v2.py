import base64
from datetime import datetime, timezone
from io import BytesIO

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
    COMPANY_NAME,
    COMPANY_WEBSITE,
    FINANCE_SENDER,
    _SIGNATURE_PNG_B64,
    build_email_html,
    finance_tenant_id,
    money,
)
from app.services.transactional_mail import send_message

NAVY = HexColor("#082B58")
BLUE = HexColor("#0E65B5")
GREEN = HexColor("#087743")
DARK_GREEN = HexColor("#075135")
GOLD = HexColor("#D5A62F")
MUTED = HexColor("#66778C")
TEXT = HexColor("#142D50")
LINE = HexColor("#D9E4EC")
PALE_BLUE = HexColor("#F4F8FC")
PALE_GREEN = HexColor("#EFF8E8")
STAMP_GREEN = HexColor("#0A7444")


def _draw_brand_sweep(c: canvas.Canvas, width: float, height: float) -> None:
    c.saveState()
    c.setFillColor(colors.white)
    c.rect(0, height - 150, width, 150, fill=1, stroke=0)

    c.setStrokeColor(HexColor("#E8F4DD"))
    c.setLineWidth(20)
    c.bezier(-20, height - 42, width * .28, height - 126, width * .68, height - 18, width + 30, height - 72)

    c.setStrokeColor(BLUE)
    c.setLineWidth(4.5)
    c.bezier(54, height - 67, width * .33, height - 28, width * .52, height - 138, width - 38, height - 72)

    c.setStrokeColor(GREEN)
    c.setLineWidth(5)
    c.bezier(58, height - 74, width * .34, height - 38, width * .52, height - 145, width - 34, height - 82)

    c.setStrokeColor(GOLD)
    c.setLineWidth(2)
    c.bezier(62, height - 80, width * .35, height - 47, width * .53, height - 148, width - 30, height - 89)

    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 27)
    c.drawString(55, height - 69, "IDS")
    c.setFont("Helvetica-Bold", 20)
    c.drawString(47, height - 97, "Ithute")
    c.setFillColor(GREEN)
    c.setFont("Helvetica-Bold", 7.7)
    c.drawString(49, height - 110, "S O L U T I O N S")
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 6.2)
    c.drawString(48, height - 122, "Learn Anywhere. Succeed Everywhere.")

    x = width - 187
    c.setFillColor(DARK_GREEN)
    c.roundRect(x, height - 105, 43, 34, 7, fill=1, stroke=0)
    c.setStrokeColor(colors.white)
    c.setLineWidth(2)
    c.line(x + 4, height - 79, x + 21.5, height - 92)
    c.line(x + 39, height - 79, x + 21.5, height - 92)
    c.setFillColor(GOLD)
    c.circle(x + 21.5, height - 64, 4.5, fill=1, stroke=0)
    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 28)
    c.drawString(x + 45, height - 96, "i")
    c.setFillColor(DARK_GREEN)
    c.drawString(x + 57, height - 96, "Mail")
    c.setFillColor(GREEN)
    c.setFont("Helvetica", 7)
    c.drawString(x + 62, height - 108, "i t h u t e   m a i l")
    c.restoreState()


def _draw_company_stamp(c: canvas.Canvas, cx: float, cy: float, invoice_number: str) -> None:
    """Generate a clean vector Ithute Digital Solutions stamp on every invoice."""
    c.saveState()
    c.setStrokeColor(STAMP_GREEN)
    c.setFillColor(STAMP_GREEN)
    c.setLineWidth(1.35)
    c.circle(cx, cy, 39, fill=0, stroke=1)
    c.circle(cx, cy, 33, fill=0, stroke=1)
    c.setFont("Helvetica-Bold", 5.5)
    c.drawCentredString(cx, cy + 24, "ITHUTE DIGITAL SOLUTIONS")
    c.setFont("Helvetica-Bold", 6.8)
    c.drawCentredString(cx, cy + 5, "AUTHORISED")
    c.setFont("Helvetica-Bold", 7.6)
    c.drawCentredString(cx, cy - 6, "FINANCE")
    c.setFont("Helvetica", 5)
    c.drawCentredString(cx, cy - 20, "MASERU - LESOTHO")
    c.setFont("Helvetica", 4.5)
    c.drawCentredString(cx, cy - 28, invoice_number)
    c.restoreState()


def _draw_signature(c: canvas.Canvas, x: float, baseline_y: float) -> None:
    """Embed the approved signature automatically, with a safe text fallback."""
    c.saveState()
    try:
        signature = ImageReader(BytesIO(base64.b64decode(_SIGNATURE_PNG_B64)))
        c.drawImage(
            signature,
            x + 12,
            baseline_y + 5,
            width=122,
            height=55,
            preserveAspectRatio=True,
            mask="auto",
        )
    except Exception:
        c.setFillColor(TEXT)
        c.setFont("Helvetica-Oblique", 18)
        c.drawString(x + 14, baseline_y + 21, "Theko")
    c.setStrokeColor(NAVY)
    c.setLineWidth(.8)
    c.line(x + 8, baseline_y + 5, x + 210, baseline_y + 5)
    c.setFillColor(TEXT)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x + 8, baseline_y - 10, AUTHORISED_NAME)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(x + 8, baseline_y - 23, AUTHORISED_TITLE)
    c.restoreState()


def render_invoice_pdf(invoice: FinanceInvoice) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    left, right = 42, width - 42
    c.setTitle(f"Invoice {invoice.invoice_number}")

    _draw_brand_sweep(c, width, height)

    top_y = height - 180
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 31)
    c.drawString(left, top_y, "INVOICE")
    c.setStrokeColor(BLUE)
    c.setLineWidth(2)
    c.line(left, top_y - 10, left + 112, top_y - 10)
    c.setStrokeColor(GREEN)
    c.line(left + 112, top_y - 10, left + 180, top_y - 10)
    c.setStrokeColor(GOLD)
    c.line(left + 180, top_y - 10, left + 225, top_y - 10)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 9.5)
    c.drawString(left, top_y - 27, "Professional Email Solutions for Your Business")

    meta_w, meta_h = 210, 80
    meta_x, meta_y = right - meta_w, top_y - 42
    c.setFillColor(PALE_BLUE)
    c.setStrokeColor(HexColor("#C6D9E8"))
    c.roundRect(meta_x, meta_y, meta_w, meta_h, 8, fill=1, stroke=1)
    issue_date = invoice.created_at.strftime("%d %B %Y") if invoice.created_at else datetime.now().strftime("%d %B %Y")
    meta = [
        ("Invoice No.", invoice.invoice_number),
        ("Issue Date", issue_date),
        ("Due Date", invoice.due_date.strftime("%d %B %Y")),
    ]
    yy = meta_y + meta_h - 22
    for i, (label, value) in enumerate(meta):
        c.setFillColor(MUTED)
        c.setFont("Helvetica-Bold", 8.4)
        c.drawString(meta_x + 14, yy, label)
        c.setFillColor(TEXT)
        c.setFont("Helvetica-Bold", 9.2)
        c.drawRightString(meta_x + meta_w - 14, yy, value)
        if i < 2:
            c.setStrokeColor(LINE)
            c.setLineWidth(.5)
            c.line(meta_x + 14, yy - 8, meta_x + meta_w - 14, yy - 8)
        yy -= 23

    bill_y = top_y - 100
    c.setFillColor(PALE_BLUE)
    c.circle(left + 13, bill_y + 1, 13, fill=1, stroke=0)
    c.setStrokeColor(NAVY)
    c.setLineWidth(1)
    c.circle(left + 13, bill_y + 4, 3.2, fill=0, stroke=1)
    c.line(left + 7, bill_y - 6, left + 19, bill_y - 6)
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(left + 42, bill_y + 7, "BILLED TO")
    c.setFillColor(TEXT)
    c.setFont("Helvetica-Bold", 11.5)
    c.drawString(left + 42, bill_y - 13, invoice.client_name[:62])
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 9.5)
    c.drawString(left + 42, bill_y - 30, invoice.recipient_email[:70])
    if invoice.client_address:
        c.drawString(left + 42, bill_y - 47, invoice.client_address[:75])

    table_top = bill_y - 78
    table_h = 74
    c.setFillColor(colors.white)
    c.setStrokeColor(HexColor("#BFD5E8"))
    c.roundRect(left, table_top - table_h, right - left, table_h, 7, fill=1, stroke=1)
    c.setFillColor(PALE_BLUE)
    c.roundRect(left, table_top - 29, right - left, 29, 7, fill=1, stroke=0)
    c.rect(left, table_top - 29, right - left, 8, fill=1, stroke=0)

    qty_x, rate_x, amount_x = 335, 420, 515
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(left + 15, table_top - 18, "DESCRIPTION")
    c.drawCentredString(qty_x, table_top - 18, "QTY")
    c.drawCentredString(rate_x, table_top - 18, "RATE (M)")
    c.drawCentredString(amount_x, table_top - 18, "AMOUNT (M)")
    c.setStrokeColor(LINE)
    for x in (310, 365, 460):
        c.line(x, table_top, x, table_top - table_h)

    c.setFillColor(TEXT)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(left + 15, table_top - 49, invoice.description[:72])
    detail = invoice.details or invoice.service_period
    if detail:
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 8)
        c.drawString(left + 15, table_top - 64, detail[:86])
    c.setFillColor(TEXT)
    c.setFont("Helvetica", 9)
    c.drawCentredString(qty_x, table_top - 52, str(invoice.quantity))
    c.drawRightString(448, table_top - 52, money(invoice.rate_minor, invoice.currency))
    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(right - 14, table_top - 52, money(invoice.subtotal_minor, invoice.currency))

    totals_w, totals_h = 253, 82
    totals_x, totals_y = right - totals_w, table_top - table_h - 92
    c.setFillColor(colors.white)
    c.setStrokeColor(LINE)
    c.roundRect(totals_x, totals_y, totals_w, totals_h, 7, fill=1, stroke=1)
    tax_pct = 0 if invoice.subtotal_minor <= 0 else round((invoice.tax_minor / invoice.subtotal_minor) * 100)
    rows = [
        ("Subtotal", money(invoice.subtotal_minor, invoice.currency), totals_y + 60),
        (f"Tax ({tax_pct}%)", money(invoice.tax_minor, invoice.currency), totals_y + 40),
    ]
    for label, value, ry in rows:
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 8.5)
        c.drawString(totals_x + 15, ry, label)
        c.setFillColor(TEXT)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawRightString(totals_x + totals_w - 15, ry, value)
    c.setFillColor(PALE_GREEN)
    c.roundRect(totals_x + 1, totals_y + 1, totals_w - 2, 28, 6, fill=1, stroke=0)
    c.setFillColor(DARK_GREEN)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(totals_x + 15, totals_y + 10, "TOTAL DUE")
    c.setFont("Helvetica-Bold", 15)
    c.drawRightString(totals_x + totals_w - 15, totals_y + 8, money(invoice.total_minor, invoice.currency))

    card_y, card_h = totals_y - 126, 106
    card_gap = 14
    card_w = (right - left - card_gap) / 2
    c.setFillColor(colors.white)
    c.setStrokeColor(LINE)
    c.roundRect(left, card_y, card_w, card_h, 7, fill=1, stroke=1)
    note_x = left + card_w + card_gap
    c.roundRect(note_x, card_y, card_w, card_h, 7, fill=1, stroke=1)

    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(left + 15, card_y + card_h - 20, "PAYMENT DETAILS")
    payment = [
        ("Bank", BANK_NAME),
        ("Account Name", BANK_ACCOUNT_NAME),
        ("Account Number", BANK_ACCOUNT_NUMBER),
        ("Billing Email", FINANCE_SENDER),
    ]
    yy = card_y + card_h - 42
    for label, value in payment:
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 7.8)
        c.drawString(left + 15, yy, label)
        c.setFillColor(TEXT)
        c.setFont("Helvetica-Bold", 8.2)
        c.drawString(left + 103, yy, value)
        yy -= 17

    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(note_x + 15, card_y + card_h - 20, "NOTE")
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    note_lines = [
        "Thank you for choosing iMail by Ithute Solutions.",
        "Please use the invoice number or client name as the",
        "payment reference when making payment.",
        f"Reference: {invoice.invoice_number}",
    ]
    yy = card_y + card_h - 42
    for line in note_lines:
        c.drawString(note_x + 15, yy, line)
        yy -= 14

    signature_base = card_y - 72
    _draw_signature(c, left, signature_base)
    _draw_company_stamp(c, right - 64, signature_base + 17, invoice.invoice_number)

    footer_y = 32
    c.setStrokeColor(LINE)
    c.line(left, footer_y + 20, right, footer_y + 20)
    c.setFillColor(NAVY)
    c.setFont("Helvetica", 7.2)
    c.drawString(left, footer_y + 7, COMPANY_WEBSITE)
    c.drawString(165, footer_y + 7, FINANCE_SENDER)
    c.drawString(332, footer_y + 7, COMPANY_LOCATION)
    c.setFillColor(HexColor("#8093AA"))
    c.setFont("Helvetica", 6.8)
    c.drawRightString(right, footer_y + 7, "LEARN ANYWHERE. SUCCEED EVERYWHERE.")
    c.setFillColor(NAVY)
    c.rect(0, 0, width * .33, 5, fill=1, stroke=0)
    c.setFillColor(GREEN)
    c.rect(width * .33, 0, width * .40, 5, fill=1, stroke=0)
    c.setFillColor(GOLD)
    c.rect(width * .73, 0, width * .27, 5, fill=1, stroke=0)

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
