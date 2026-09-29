import base64
from datetime import datetime, timezone
from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Domain, DomainStatus, FinanceInvoice
from app.services.transactional_mail import send_message

FINANCE_SENDER = "invoices@ithute.co.ls"
BANK_NAME = "LPB"
BANK_ACCOUNT_NAME = "Koetlisi Theko"
BANK_ACCOUNT_NUMBER = "1035927000011"
AUTHORISED_NAME = "Koetlisi Theko Mofoka"
AUTHORISED_TITLE = "CEO, Ithute Digital Solutions"
COMPANY_NAME = "Ithute Digital Solutions"
COMPANY_LOCATION = "Maseru, Lesotho"
COMPANY_WEBSITE = "ithute.co.ls"

# Clean transparent crop of the signature supplied by Koetlisi Theko Mofoka.
_SIGNATURE_PNG_B64 = "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"

NAVY = HexColor("#082B58")
GREEN = HexColor("#087743")
DARK_GREEN = HexColor("#075135")
GOLD = HexColor("#D5A62F")
MUTED = HexColor("#66778C")
PALE_BLUE = HexColor("#F2F7FB")
PALE_GREEN = HexColor("#F1F9EB")
LINE = HexColor("#D9E4EC")
TEXT = HexColor("#142D50")


def money(minor: int, currency: str = "LSL") -> str:
    prefix = "M" if currency.upper() == "LSL" else currency.upper()
    return f"{prefix} {minor / 100:,.2f}"


def build_default_subject(invoice_number: str, client_name: str) -> str:
    return f"Ithute Invoice {invoice_number} - {client_name}"


def build_default_email_body(
    *, invoice_number: str, client_name: str, description: str, total_minor: int, currency: str, due_date
) -> str:
    return (
        f"Dear {client_name},\n\n"
        f"Please find attached invoice {invoice_number} from {COMPANY_NAME} for {description}.\n\n"
        f"Amount due: {money(total_minor, currency)}\n"
        f"Due date: {due_date.strftime('%d %B %Y')}\n\n"
        "Payment details:\n"
        f"Bank: {BANK_NAME}\n"
        f"Account Name: {BANK_ACCOUNT_NAME}\n"
        f"Account Number: {BANK_ACCOUNT_NUMBER}\n"
        f"Payment Reference: {invoice_number}\n\n"
        "Please use the invoice number as the payment reference. If you have any questions, "
        f"please reply to {FINANCE_SENDER}.\n\n"
        "Kind regards,\n"
        f"{AUTHORISED_NAME}\n"
        f"{AUTHORISED_TITLE}\n"
        f"{COMPANY_NAME}"
    )


def build_email_html(invoice: FinanceInvoice) -> str:
    paragraphs = "".join(f"<p>{escape(line)}</p>" for line in invoice.email_body.split("\n\n") if line.strip())
    return (
        '<div style="font-family:Arial,sans-serif;color:#142d50;line-height:1.55;max-width:680px">'
        '<div style="border-top:5px solid #087743;padding-top:18px">'
        f'<h2 style="color:#082b58;margin:0 0 14px">Invoice {escape(invoice.invoice_number)}</h2>'
        f"{paragraphs}"
        '<p style="font-size:12px;color:#66778c;margin-top:24px">'
        "Ithute Digital Solutions · iMail · ithute.co.ls</p></div></div>"
    )


def finance_tenant_id(db: Session):
    domain = db.scalar(
        select(Domain).where(
            Domain.ascii_name == "ithute.co.ls",
            Domain.status == DomainStatus.verified,
            Domain.mail_enabled.is_(True),
        )
    )
    if domain is None:
        raise ValueError("ithute.co.ls must be verified and mail-enabled before Finance can send invoices")
    return domain.tenant_id


def next_invoice_number(db: Session) -> str:
    year = datetime.now(timezone.utc).year
    prefix = f"IM-{year}-"
    latest = db.scalar(
        select(FinanceInvoice.invoice_number)
        .where(FinanceInvoice.invoice_number.like(f"{prefix}%"))
        .order_by(FinanceInvoice.invoice_number.desc())
        .limit(1)
    )
    sequence = 1
    if latest:
        try:
            sequence = int(latest.rsplit("-", 1)[1]) + 1
        except (ValueError, IndexError):
            sequence = 1
    return f"{prefix}{sequence:04d}"


def invoice_out(row: FinanceInvoice) -> dict:
    return {
        "id": str(row.id),
        "invoice_number": row.invoice_number,
        "client_name": row.client_name,
        "recipient_email": row.recipient_email,
        "client_address": row.client_address,
        "description": row.description,
        "details": row.details,
        "service_period": row.service_period,
        "quantity": row.quantity,
        "rate_minor": row.rate_minor,
        "tax_minor": row.tax_minor,
        "subtotal_minor": row.subtotal_minor,
        "total_minor": row.total_minor,
        "currency": row.currency,
        "due_date": row.due_date.isoformat(),
        "status": row.status,
        "email_subject": row.email_subject,
        "email_body": row.email_body,
        "sent_at": row.sent_at.isoformat() if row.sent_at else None,
        "last_error": row.last_error,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _draw_header(c: canvas.Canvas, width: float, height: float) -> float:
    # Light brand sweep inspired by the approved Ithute + iMail banner.
    c.setFillColor(colors.white)
    c.rect(0, height - 145, width, 145, fill=1, stroke=0)
    c.setStrokeColor(HexColor("#EAF5E4")); c.setLineWidth(22)
    c.bezier(0, height - 45, width * .34, height - 120, width * .62, height - 10, width, height - 62)
    c.setStrokeColor(HexColor("#0E65B5")); c.setLineWidth(4)
    c.bezier(48, height - 65, width * .35, height - 20, width * .48, height - 132, width - 45, height - 72)
    c.setStrokeColor(GREEN); c.setLineWidth(5)
    c.bezier(55, height - 72, width * .35, height - 35, width * .49, height - 140, width - 40, height - 82)
    c.setStrokeColor(GOLD); c.setLineWidth(2)
    c.bezier(58, height - 78, width * .35, height - 45, width * .50, height - 145, width - 36, height - 88)

    # Left brand lock-up.
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 28); c.drawString(58, height - 72, "IDS")
    c.setFont("Helvetica-Bold", 19); c.drawString(48, height - 98, "Ithute")
    c.setFillColor(GREEN); c.setFont("Helvetica-Bold", 8); c.drawString(49, height - 111, "S O L U T I O N S")
    c.setFillColor(MUTED); c.setFont("Helvetica", 6.5); c.drawString(49, height - 122, "Learn Anywhere. Succeed Everywhere.")

    # Right iMail mark.
    x = width - 185
    c.setFillColor(DARK_GREEN); c.roundRect(x, height - 105, 42, 34, 7, fill=1, stroke=0)
    c.setStrokeColor(colors.white); c.setLineWidth(2)
    c.line(x + 3, height - 78, x + 21, height - 92); c.line(x + 39, height - 78, x + 21, height - 92)
    c.setFillColor(GOLD); c.circle(x + 21, height - 64, 4.5, fill=1, stroke=0)
    c.setFillColor(DARK_GREEN); c.setFont("Helvetica-Bold", 28); c.drawString(x + 50, height - 96, "Mail")
    c.setFillColor(GOLD); c.setFont("Helvetica-Bold", 28); c.drawString(x + 42, height - 96, "i")
    c.setFillColor(GREEN); c.setFont("Helvetica", 7); c.drawString(x + 63, height - 108, "i t h u t e   m a i l")
    return height - 150


def render_invoice_pdf(invoice: FinanceInvoice) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    c.setTitle(f"Invoice {invoice.invoice_number}")
    y = _draw_header(c, width, height)

    # Invoice title and metadata.
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 31); c.drawString(42, y - 38, "INVOICE")
    c.setStrokeColor(GREEN); c.setLineWidth(2); c.line(42, y - 46, 155, y - 46)
    c.setStrokeColor(GOLD); c.line(155, y - 46, 226, y - 46)
    c.setFillColor(MUTED); c.setFont("Helvetica", 9.5)
    c.drawString(42, y - 63, "Professional Email Solutions for Your Business")

    meta_x, meta_y, meta_w, meta_h = width - 252, y - 85, 210, 78
    c.setFillColor(PALE_BLUE); c.setStrokeColor(LINE)
    c.roundRect(meta_x, meta_y, meta_w, meta_h, 8, fill=1, stroke=1)
    meta = [
        ("Invoice No.", invoice.invoice_number),
        ("Issue Date", invoice.created_at.strftime("%d %B %Y") if invoice.created_at else datetime.now().strftime("%d %B %Y")),
        ("Due Date", invoice.due_date.strftime("%d %B %Y")),
    ]
    yy = meta_y + meta_h - 22
    for i, (label, value) in enumerate(meta):
        c.setFillColor(MUTED); c.setFont("Helvetica-Bold", 8.5); c.drawString(meta_x + 14, yy, label)
        c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 9); c.drawRightString(meta_x + meta_w - 14, yy, value)
        if i < 2:
            c.setStrokeColor(LINE); c.setLineWidth(.5); c.line(meta_x + 14, yy - 8, meta_x + meta_w - 14, yy - 8)
        yy -= 23

    # Billed-to block.
    bill_y = y - 123
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 9); c.drawString(72, bill_y, "BILLED TO")
    c.setFillColor(PALE_BLUE); c.circle(53, bill_y + 1, 13, fill=1, stroke=0)
    c.setFillColor(NAVY); c.circle(53, bill_y + 4, 3.5, fill=0, stroke=1)
    c.line(47, bill_y - 6, 59, bill_y - 6)
    c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 11.5); c.drawString(72, bill_y - 20, invoice.client_name)
    c.setFillColor(MUTED); c.setFont("Helvetica", 9.5); c.drawString(72, bill_y - 36, invoice.recipient_email)
    if invoice.client_address:
        c.drawString(72, bill_y - 52, invoice.client_address[:75])

    # Item table.
    table_y = bill_y - 88
    left, right = 42, width - 42
    c.setFillColor(PALE_BLUE); c.setStrokeColor(HexColor("#BFD5E8"))
    c.roundRect(left, table_y - 70, right - left, 70, 7, fill=1, stroke=1)
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 8.5)
    c.drawString(left + 15, table_y - 18, "DESCRIPTION")
    c.drawCentredString(335, table_y - 18, "QTY")
    c.drawCentredString(420, table_y - 18, "RATE (M)")
    c.drawCentredString(515, table_y - 18, "AMOUNT (M)")
    c.setStrokeColor(HexColor("#D4E1EB")); c.line(left, table_y - 28, right, table_y - 28)
    c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 9.5); c.drawString(left + 15, table_y - 47, invoice.description[:72])
    detail = invoice.details or invoice.service_period
    if detail:
        c.setFillColor(MUTED); c.setFont("Helvetica", 8); c.drawString(left + 15, table_y - 61, detail[:84])
    c.setFillColor(TEXT); c.setFont("Helvetica", 9); c.drawCentredString(335, table_y - 50, str(invoice.quantity))
    c.drawRightString(445, table_y - 50, money(invoice.rate_minor, invoice.currency))
    c.setFont("Helvetica-Bold", 9); c.drawRightString(right - 13, table_y - 50, money(invoice.subtotal_minor, invoice.currency))

    # Totals card.
    totals_x, totals_y, totals_w, totals_h = width - 295, table_y - 158, 253, 76
    c.setFillColor(colors.white); c.setStrokeColor(LINE); c.roundRect(totals_x, totals_y, totals_w, totals_h, 7, fill=1, stroke=1)
    c.setFillColor(MUTED); c.setFont("Helvetica", 8.5); c.drawString(totals_x + 15, totals_y + 56, "Subtotal")
    c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 8.5); c.drawRightString(totals_x + totals_w - 15, totals_y + 56, money(invoice.subtotal_minor, invoice.currency))
    c.setFillColor(MUTED); c.setFont("Helvetica", 8.5); c.drawString(totals_x + 15, totals_y + 37, "Tax")
    c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 8.5); c.drawRightString(totals_x + totals_w - 15, totals_y + 37, money(invoice.tax_minor, invoice.currency))
    c.setFillColor(PALE_GREEN); c.rect(totals_x + 1, totals_y + 1, totals_w - 2, 26, fill=1, stroke=0)
    c.setFillColor(DARK_GREEN); c.setFont("Helvetica-Bold", 10); c.drawString(totals_x + 15, totals_y + 10, "TOTAL DUE")
    c.setFont("Helvetica-Bold", 15); c.drawRightString(totals_x + totals_w - 15, totals_y + 8, money(invoice.total_minor, invoice.currency))

    # Payment and note cards.
    card_y, card_h = totals_y - 120, 102
    card_gap = 14; card_w = (right - left - card_gap) / 2
    c.setFillColor(colors.white); c.setStrokeColor(LINE)
    c.roundRect(left, card_y, card_w, card_h, 7, fill=1, stroke=1)
    c.roundRect(left + card_w + card_gap, card_y, card_w, card_h, 7, fill=1, stroke=1)
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 9); c.drawString(left + 15, card_y + card_h - 20, "PAYMENT DETAILS")
    labels = [("Bank", BANK_NAME), ("Account Name", BANK_ACCOUNT_NAME), ("Account Number", BANK_ACCOUNT_NUMBER), ("Billing Email", FINANCE_SENDER)]
    yy = card_y + card_h - 40
    for label, value in labels:
        c.setFillColor(MUTED); c.setFont("Helvetica", 7.8); c.drawString(left + 15, yy, label)
        c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 8.2); c.drawString(left + 103, yy, value)
        yy -= 17

    note_x = left + card_w + card_gap
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 9); c.drawString(note_x + 15, card_y + card_h - 20, "NOTE")
    c.setFillColor(MUTED); c.setFont("Helvetica", 8)
    note_lines = [
        "Thank you for choosing iMail by Ithute Solutions.",
        "Please use the invoice number or client name as",
        "the payment reference when making payment.",
        f"Reference: {invoice.invoice_number}",
    ]
    yy = card_y + card_h - 42
    for line in note_lines:
        c.drawString(note_x + 15, yy, line); yy -= 14

    # Signature area: intentionally open and light, matching the approved design.
    sig_y = card_y - 88
    try:
        signature = ImageReader(BytesIO(base64.b64decode(_SIGNATURE_PNG_B64)))
        c.drawImage(signature, left + 12, sig_y + 28, width=118, height=52, preserveAspectRatio=True, mask="auto")
    except Exception:
        pass
    c.setStrokeColor(NAVY); c.setLineWidth(.8); c.line(left + 8, sig_y + 28, left + 210, sig_y + 28)
    c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 9); c.drawString(left + 8, sig_y + 13, AUTHORISED_NAME)
    c.setFillColor(MUTED); c.setFont("Helvetica", 8); c.drawString(left + 8, sig_y, AUTHORISED_TITLE)

    # Footer.
    footer_y = 32
    c.setStrokeColor(LINE); c.line(42, footer_y + 20, right, footer_y + 20)
    c.setFillColor(NAVY); c.setFont("Helvetica", 7.3)
    c.drawString(42, footer_y + 7, COMPANY_WEBSITE)
    c.drawString(165, footer_y + 7, FINANCE_SENDER)
    c.drawString(332, footer_y + 7, COMPANY_LOCATION)
    c.setFillColor(HexColor("#8093AA")); c.setFont("Helvetica", 6.8)
    c.drawRightString(right, footer_y + 7, "LEARN ANYWHERE. SUCCEED EVERYWHERE.")
    c.setFillColor(NAVY); c.rect(0, 0, width * .33, 5, fill=1, stroke=0)
    c.setFillColor(GREEN); c.rect(width * .33, 0, width * .40, 5, fill=1, stroke=0)
    c.setFillColor(GOLD); c.rect(width * .73, 0, width * .27, 5, fill=1, stroke=0)

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
