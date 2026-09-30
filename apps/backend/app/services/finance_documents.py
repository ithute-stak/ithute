from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    FinanceAuditEvent,
    FinanceCommercialDocument,
    FinanceCommercialDocumentItem,
    FinanceInvoice,
    FinancePayment,
)
from app.services.finance_invoices import build_default_email_body, build_default_subject, next_invoice_number
from app.services.finance_mail import send_finance_message

NAVY = HexColor("#062D63")
GREEN = HexColor("#087743")
GOLD = HexColor("#D5A62F")
MUTED = HexColor("#667A96")
TEXT = HexColor("#102E59")
LINE = HexColor("#C8DCEC")
PALE_BLUE = HexColor("#F1F7FC")
PALE_GREEN = HexColor("#EFF8E6")
ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"
HEADER_PATH = ASSET_DIR / "finance_invoice_header.jpg"
SIGNATURE_PATH = ASSET_DIR / "koetlisi_theko_mofoka_signature.png"

PREFIXES = {"quotation": "QT", "proforma": "PF", "credit_note": "CN"}
TITLES = {"quotation": "QUOTATION", "proforma": "PRO-FORMA INVOICE", "credit_note": "CREDIT NOTE"}


def audit(db: Session, *, entity_type: str, entity_id, action: str, summary: str, actor_user_id=None) -> None:
    db.add(
        FinanceAuditEvent(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            summary=summary[:1000],
            actor_user_id=actor_user_id,
        )
    )


def next_document_number(db: Session, document_type: str, issue_date: date | None = None) -> str:
    prefix = PREFIXES[document_type]
    year = (issue_date or date.today()).year
    stem = f"{prefix}-{year}-"
    latest = db.scalar(
        select(FinanceCommercialDocument.document_number)
        .where(FinanceCommercialDocument.document_number.like(f"{stem}%"))
        .order_by(FinanceCommercialDocument.document_number.desc())
        .limit(1)
    )
    sequence = 1
    if latest:
        try:
            sequence = int(latest.rsplit("-", 1)[1]) + 1
        except (ValueError, IndexError):
            sequence = 1
    return f"{stem}{sequence:04d}"


def document_out(row: FinanceCommercialDocument) -> dict:
    return {
        "id": str(row.id),
        "document_number": row.document_number,
        "document_type": row.document_type,
        "status": row.status,
        "client_id": str(row.client_id) if row.client_id else None,
        "source_document_id": str(row.source_document_id) if row.source_document_id else None,
        "source_invoice_id": str(row.source_invoice_id) if row.source_invoice_id else None,
        "converted_invoice_id": str(row.converted_invoice_id) if row.converted_invoice_id else None,
        "client_name": row.client_name,
        "recipient_email": row.recipient_email,
        "client_address": row.client_address,
        "issue_date": row.issue_date.isoformat(),
        "valid_until": row.valid_until.isoformat() if row.valid_until else None,
        "currency": row.currency,
        "subtotal_minor": row.subtotal_minor,
        "tax_minor": row.tax_minor,
        "total_minor": row.total_minor,
        "notes": row.notes,
        "sent_at": row.sent_at.isoformat() if row.sent_at else None,
        "accepted_at": row.accepted_at.isoformat() if row.accepted_at else None,
        "rejected_at": row.rejected_at.isoformat() if row.rejected_at else None,
        "converted_at": row.converted_at.isoformat() if row.converted_at else None,
        "last_error": row.last_error,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "items": [
            {
                "id": str(item.id),
                "position": item.position,
                "description": item.description,
                "details": item.details,
                "quantity": item.quantity,
                "unit_rate_minor": item.unit_rate_minor,
                "tax_minor": item.tax_minor,
                "line_subtotal_minor": item.line_subtotal_minor,
                "line_total_minor": item.line_total_minor,
            }
            for item in row.items
        ],
    }


def _money(minor: int) -> str:
    return f"M {minor / 100:,.2f}"


def _draw_header(c: canvas.Canvas, width: float, height: float) -> float:
    header_h = width * 270 / 1103
    if HEADER_PATH.is_file():
        c.drawImage(ImageReader(str(HEADER_PATH)), 0, height - header_h, width=width, height=header_h, preserveAspectRatio=False)
    return header_h


def _draw_signature(c: canvas.Canvas, x: float, y: float) -> None:
    if SIGNATURE_PATH.is_file():
        c.drawImage(ImageReader(str(SIGNATURE_PATH)), x, y + 8, width=128, height=55, preserveAspectRatio=True, mask="auto")
    c.setStrokeColor(NAVY)
    c.line(x, y, x + 205, y)
    c.setFillColor(TEXT)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x, y - 14, "Koetlisi Theko Mofoka")
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(x, y - 27, "CEO, Ithute Digital Solutions")


def render_document_pdf(document: FinanceCommercialDocument) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    left, right = 32, width - 32
    c.setTitle(f"{TITLES[document.document_type]} {document.document_number}")
    c.setFillColor(colors.white)
    c.rect(0, 0, width, height, fill=1, stroke=0)
    header_h = _draw_header(c, width, height)

    y = height - header_h - 38
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 27 if document.document_type != "proforma" else 23)
    c.drawString(left, y, TITLES[document.document_type])
    c.setStrokeColor(GREEN)
    c.setLineWidth(2)
    c.line(left, y - 10, left + 170, y - 10)
    c.setStrokeColor(GOLD)
    c.line(left + 170, y - 10, left + 225, y - 10)

    meta_x, meta_y, meta_w, meta_h = right - 205, y - 42, 205, 78
    c.setFillColor(PALE_BLUE)
    c.setStrokeColor(LINE)
    c.roundRect(meta_x, meta_y, meta_w, meta_h, 8, fill=1, stroke=1)
    labels = [("Document No.", document.document_number), ("Issue Date", document.issue_date.strftime("%d %B %Y"))]
    if document.valid_until:
        labels.append(("Valid Until", document.valid_until.strftime("%d %B %Y")))
    my = meta_y + meta_h - 20
    for label, value in labels:
        c.setFillColor(MUTED); c.setFont("Helvetica-Bold", 8); c.drawString(meta_x + 13, my, label)
        c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 8.6); c.drawRightString(meta_x + meta_w - 13, my, value)
        my -= 22

    bill_y = y - 110
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 8.5); c.drawString(left, bill_y, "PREPARED FOR")
    c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 11); c.drawString(left, bill_y - 18, document.client_name)
    c.setFillColor(MUTED); c.setFont("Helvetica", 9); c.drawString(left, bill_y - 35, document.recipient_email)
    if document.client_address:
        c.drawString(left, bill_y - 51, document.client_address[:80])

    table_top = bill_y - 78
    row_h = 34
    header_row_h = 26
    items = list(document.items)
    table_h = header_row_h + max(1, len(items)) * row_h
    c.setFillColor(colors.white); c.setStrokeColor(LINE)
    c.roundRect(left, table_top - table_h, right - left, table_h, 7, fill=1, stroke=1)
    c.setFillColor(PALE_BLUE); c.roundRect(left, table_top - header_row_h, right - left, header_row_h, 7, fill=1, stroke=0)
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 8)
    c.drawString(left + 12, table_top - 17, "DESCRIPTION")
    c.drawCentredString(345, table_top - 17, "QTY")
    c.drawRightString(456, table_top - 17, "RATE")
    c.drawRightString(right - 12, table_top - 17, "AMOUNT")

    row_y = table_top - header_row_h
    for item in items:
        row_y -= row_h
        c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 8.2); c.drawString(left + 12, row_y + 20, item.description[:52])
        if item.details:
            c.setFillColor(MUTED); c.setFont("Helvetica", 6.8); c.drawString(left + 12, row_y + 8, item.details[:72])
        c.setFillColor(TEXT); c.setFont("Helvetica", 8.2); c.drawCentredString(345, row_y + 15, str(item.quantity))
        c.drawRightString(456, row_y + 15, _money(item.unit_rate_minor))
        c.setFont("Helvetica-Bold", 8.2); c.drawRightString(right - 12, row_y + 15, _money(item.line_total_minor))
        c.setStrokeColor(LINE); c.setLineWidth(.4); c.line(left, row_y, right, row_y)

    totals_y = table_top - table_h - 90
    totals_x, totals_w = right - 255, 255
    c.setFillColor(colors.white); c.setStrokeColor(LINE); c.roundRect(totals_x, totals_y, totals_w, 80, 7, fill=1, stroke=1)
    for label, value, yy in (("Subtotal", _money(document.subtotal_minor), totals_y + 58), ("Tax", _money(document.tax_minor), totals_y + 38)):
        c.setFillColor(MUTED); c.setFont("Helvetica", 8.5); c.drawString(totals_x + 15, yy, label)
        c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 8.5); c.drawRightString(totals_x + totals_w - 15, yy, value)
    c.setFillColor(PALE_GREEN); c.roundRect(totals_x + 1, totals_y + 1, totals_w - 2, 27, 6, fill=1, stroke=0)
    c.setFillColor(GREEN); c.setFont("Helvetica-Bold", 10); c.drawString(totals_x + 15, totals_y + 9, "TOTAL")
    c.setFont("Helvetica-Bold", 14); c.drawRightString(totals_x + totals_w - 15, totals_y + 8, _money(document.total_minor))

    note_y = totals_y - 35
    if document.notes:
        c.setFillColor(MUTED); c.setFont("Helvetica", 8)
        c.drawString(left, note_y, f"Note: {document.notes[:110]}")
    _draw_signature(c, left, max(82, note_y - 82))
    c.setFillColor(MUTED); c.setFont("Helvetica", 7.5)
    c.drawString(left, 24, "ithute.co.ls")
    c.drawCentredString(width / 2, 24, "invoices@ithute.co.ls")
    c.drawRightString(right, 24, "Maseru, Lesotho")
    c.save()
    return buffer.getvalue()


def send_document(db: Session, document: FinanceCommercialDocument) -> None:
    pdf = render_document_pdf(document)
    title = TITLES[document.document_type].title()
    text = (
        f"Dear {document.client_name},\n\nPlease find attached {title.lower()} {document.document_number} "
        f"from Ithute Digital Solutions.\n\nTotal: {_money(document.total_minor)}\n\nKind regards,\nIthute Digital Solutions"
    )
    html = text.replace("\n", "<br>")
    send_finance_message(
        db,
        recipient=document.recipient_email,
        subject=f"Ithute {title} - {document.document_number}",
        text_body=text,
        html_body=f"<p>{html}</p>",
        attachment_filename=f"{document.document_number}.pdf",
        attachment_data=pdf,
    )
    document.status = "sent" if document.status == "draft" else document.status
    document.sent_at = datetime.now(timezone.utc)
    document.last_error = None


def convert_to_invoice(db: Session, document: FinanceCommercialDocument, actor_user_id=None) -> FinanceInvoice:
    if document.document_type not in {"quotation", "proforma"}:
        raise ValueError("Only quotations and pro-forma invoices can be converted to invoices")
    if document.converted_invoice_id:
        existing = db.get(FinanceInvoice, document.converted_invoice_id)
        if existing is not None:
            return existing
    due_date = date.today() + timedelta(days=7)
    summary = "; ".join(item.description for item in document.items)[:1200] or document.document_number
    invoice_number = next_invoice_number(db)
    invoice = FinanceInvoice(
        invoice_number=invoice_number,
        client_id=document.client_id,
        client_name=document.client_name,
        recipient_email=document.recipient_email,
        client_address=document.client_address,
        description=f"Services per {document.document_number}",
        details=summary,
        service_period=date.today().strftime("%B %Y"),
        quantity=1,
        rate_minor=document.subtotal_minor,
        tax_minor=document.tax_minor,
        subtotal_minor=document.subtotal_minor,
        total_minor=document.total_minor,
        currency=document.currency,
        due_date=due_date,
        status="draft",
        email_subject=build_default_subject(invoice_number, document.client_name),
        email_body=build_default_email_body(
            invoice_number=invoice_number,
            client_name=document.client_name,
            description=f"Services per {document.document_number}",
            total_minor=document.total_minor,
            currency=document.currency,
            due_date=due_date,
        ),
        created_by_user_id=actor_user_id,
    )
    db.add(invoice)
    db.flush()
    document.converted_invoice_id = invoice.id
    document.converted_at = datetime.now(timezone.utc)
    document.status = "converted"
    audit(db, entity_type="commercial_document", entity_id=document.id, action="converted_to_invoice", summary=f"{document.document_number} -> {invoice.invoice_number}", actor_user_id=actor_user_id)
    return invoice


def render_receipt_pdf(payment: FinancePayment, invoice: FinanceInvoice) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    left, right = 42, width - 42
    c.setFillColor(colors.white); c.rect(0, 0, width, height, fill=1, stroke=0)
    header_h = _draw_header(c, width, height)
    y = height - header_h - 45
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 29); c.drawString(left, y, "PAYMENT RECEIPT")
    c.setStrokeColor(GREEN); c.setLineWidth(2); c.line(left, y - 10, left + 220, y - 10)
    c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 13); c.drawString(left, y - 55, invoice.client_name)
    c.setFillColor(MUTED); c.setFont("Helvetica", 9); c.drawString(left, y - 73, invoice.recipient_email)

    box_y = y - 220
    c.setFillColor(PALE_BLUE); c.setStrokeColor(LINE); c.roundRect(left, box_y, right - left, 115, 8, fill=1, stroke=1)
    rows = [
        ("Invoice", invoice.invoice_number),
        ("Payment date", payment.payment_date.strftime("%d %B %Y")),
        ("Payment method", payment.method.replace("_", " ").title()),
        ("Reference", payment.reference or "-"),
    ]
    yy = box_y + 88
    for label, value in rows:
        c.setFillColor(MUTED); c.setFont("Helvetica-Bold", 8.5); c.drawString(left + 18, yy, label)
        c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 9.3); c.drawRightString(right - 18, yy, value)
        yy -= 22
    c.setFillColor(PALE_GREEN); c.roundRect(left, box_y - 65, right - left, 48, 8, fill=1, stroke=0)
    c.setFillColor(GREEN); c.setFont("Helvetica-Bold", 11); c.drawString(left + 18, box_y - 45, "AMOUNT RECEIVED")
    c.setFont("Helvetica-Bold", 19); c.drawRightString(right - 18, box_y - 47, _money(payment.amount_minor))
    _draw_signature(c, left, box_y - 165)
    c.setFillColor(MUTED); c.setFont("Helvetica", 8); c.drawString(left, 34, "Thank you for your payment. This receipt confirms the payment recorded by Ithute Digital Solutions.")
    c.save()
    return buffer.getvalue()
