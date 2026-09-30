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
from sqlalchemy.orm import Session, selectinload

from app.models import (
    FinanceCreditNote,
    FinanceDocument,
    FinanceDocumentItem,
    FinanceInvoice,
    FinanceInvoiceItem,
    FinancePayment,
)
from app.services.finance_invoices import (
    AUTHORISED_NAME,
    AUTHORISED_TITLE,
    BANK_ACCOUNT_NAME,
    BANK_ACCOUNT_NUMBER,
    BANK_NAME,
    FINANCE_SENDER,
    build_default_email_body,
    build_default_subject,
    money,
    next_invoice_number,
)
from app.services.finance_mail import send_finance_message

NAVY = HexColor("#062D63")
GREEN = HexColor("#087743")
GOLD = HexColor("#D5A62F")
MUTED = HexColor("#667A96")
TEXT = HexColor("#102E59")
LINE = HexColor("#C8DCEC")
PALE_BLUE = HexColor("#F1F7FC")
PALE_GREEN = HexColor("#EFF8E6")
_ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"
_HEADER_PATH = _ASSET_DIR / "finance_invoice_header.jpg"
_SIGNATURE_PATH = _ASSET_DIR / "koetlisi_theko_mofoka_signature.png"


def _next_number(db: Session, *, prefix: str, model, column) -> str:
    year = datetime.now(timezone.utc).year
    marker = f"{prefix}-{year}-"
    last = db.scalar(select(column).where(column.like(f"{marker}%")).order_by(column.desc()).limit(1))
    sequence = 1
    if last:
        try:
            sequence = int(str(last).rsplit("-", 1)[1]) + 1
        except (ValueError, IndexError):
            sequence = 1
    return f"{marker}{sequence:04d}"


def next_document_number(db: Session, document_type: str) -> str:
    prefix = "QT" if document_type == "quotation" else "PF"
    return _next_number(db, prefix=prefix, model=FinanceDocument, column=FinanceDocument.document_number)


def next_credit_number(db: Session) -> str:
    return _next_number(db, prefix="CN", model=FinanceCreditNote, column=FinanceCreditNote.credit_number)


def invoice_items(invoice: FinanceInvoice) -> list[dict]:
    if getattr(invoice, "items", None):
        return [
            {
                "description": item.description,
                "details": item.details,
                "quantity": item.quantity,
                "rate_minor": item.rate_minor,
                "tax_minor": item.tax_minor,
                "subtotal_minor": item.quantity * item.rate_minor,
                "total_minor": item.quantity * item.rate_minor + item.tax_minor,
            }
            for item in invoice.items
        ]
    return [
        {
            "description": invoice.description,
            "details": invoice.details,
            "quantity": invoice.quantity,
            "rate_minor": invoice.rate_minor,
            "tax_minor": invoice.tax_minor,
            "subtotal_minor": invoice.subtotal_minor,
            "total_minor": invoice.total_minor,
        }
    ]


def document_out(row: FinanceDocument) -> dict:
    return {
        "id": str(row.id),
        "document_number": row.document_number,
        "document_type": row.document_type,
        "status": row.status,
        "client_id": str(row.client_id) if row.client_id else None,
        "client_name": row.client_name,
        "recipient_email": row.recipient_email,
        "client_address": row.client_address,
        "currency": row.currency,
        "subtotal_minor": row.subtotal_minor,
        "tax_minor": row.tax_minor,
        "total_minor": row.total_minor,
        "valid_until": row.valid_until.isoformat() if row.valid_until else None,
        "payment_terms_days": row.payment_terms_days,
        "notes": row.notes,
        "converted_invoice_id": str(row.converted_invoice_id) if row.converted_invoice_id else None,
        "sent_at": row.sent_at.isoformat() if row.sent_at else None,
        "accepted_at": row.accepted_at.isoformat() if row.accepted_at else None,
        "rejected_at": row.rejected_at.isoformat() if row.rejected_at else None,
        "converted_at": row.converted_at.isoformat() if row.converted_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "items": [
            {
                "id": str(item.id),
                "position": item.position,
                "description": item.description,
                "details": item.details,
                "quantity": item.quantity,
                "rate_minor": item.rate_minor,
                "tax_minor": item.tax_minor,
                "subtotal_minor": item.quantity * item.rate_minor,
                "total_minor": item.quantity * item.rate_minor + item.tax_minor,
            }
            for item in row.items
        ],
    }


def credit_note_out(row: FinanceCreditNote) -> dict:
    return {
        "id": str(row.id),
        "credit_number": row.credit_number,
        "invoice_id": str(row.invoice_id),
        "amount_minor": row.amount_minor,
        "reason": row.reason,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _header(c: canvas.Canvas, width: float, height: float) -> float:
    header_h = width * 270 / 1103
    if _HEADER_PATH.is_file():
        c.drawImage(ImageReader(str(_HEADER_PATH)), 0, height - header_h, width=width, height=header_h, preserveAspectRatio=False)
    return header_h


def _signature(c: canvas.Canvas, x: float, y: float) -> None:
    if _SIGNATURE_PATH.is_file():
        c.drawImage(ImageReader(str(_SIGNATURE_PATH)), x + 10, y + 5, width=128, height=55, preserveAspectRatio=True, mask="auto")
    c.setStrokeColor(NAVY)
    c.line(x, y, x + 205, y)
    c.setFillColor(TEXT)
    c.setFont("Helvetica-Bold", 9.2)
    c.drawString(x, y - 15, AUTHORISED_NAME)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(x, y - 29, AUTHORISED_TITLE)


def _draw_items(c: canvas.Canvas, *, items: list[dict], currency: str, left: float, right: float, top: float) -> float:
    row_h = 36
    head_h = 25
    count = max(1, len(items))
    table_h = head_h + row_h * count
    table_w = right - left
    c.setStrokeColor(LINE)
    c.setFillColor(colors.white)
    c.roundRect(left, top - table_h, table_w, table_h, 6, fill=1, stroke=1)
    c.setFillColor(PALE_BLUE)
    c.roundRect(left, top - head_h, table_w, head_h, 6, fill=1, stroke=0)
    c.rect(left, top - head_h, table_w, 6, fill=1, stroke=0)
    x_qty, x_rate, x_amount = 345, 435, 525
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 8.2)
    c.drawString(left + 12, top - 16, "DESCRIPTION")
    c.drawCentredString(x_qty, top - 16, "QTY")
    c.drawCentredString(x_rate, top - 16, "RATE (M)")
    c.drawCentredString(x_amount, top - 16, "AMOUNT (M)")
    for vx in (312, 375, 470):
        c.line(vx, top, vx, top - table_h)
    y = top - head_h - 22
    for item in items:
        desc = str(item["description"])
        if len(desc) > 52:
            desc = desc[:49] + "..."
        c.setFillColor(TEXT)
        c.setFont("Helvetica-Bold", 8.3)
        c.drawString(left + 12, y, desc)
        detail = str(item.get("details") or "")
        if detail:
            c.setFillColor(MUTED)
            c.setFont("Helvetica", 6.8)
            c.drawString(left + 12, y - 10, detail[:70])
        c.setFillColor(TEXT)
        c.setFont("Helvetica", 8.2)
        c.drawCentredString(x_qty, y, str(item["quantity"]))
        c.drawRightString(457, y, money(int(item["rate_minor"]), currency))
        c.setFont("Helvetica-Bold", 8.2)
        c.drawRightString(right - 12, y, money(int(item["quantity"]) * int(item["rate_minor"]), currency))
        y -= row_h
    return top - table_h


def render_document_pdf(document: FinanceDocument) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    left, right = 30, width - 30
    c.setFillColor(colors.white)
    c.rect(0, 0, width, height, fill=1, stroke=0)
    header_h = _header(c, width, height)

    title = "QUOTATION" if document.document_type == "quotation" else "PRO-FORMA INVOICE"
    title_y = height - header_h - 36
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 27 if document.document_type == "quotation" else 23)
    c.drawString(left, title_y, title)
    c.setStrokeColor(GREEN)
    c.setLineWidth(2)
    c.line(left, title_y - 10, left + 145, title_y - 10)
    c.setStrokeColor(GOLD)
    c.line(left + 145, title_y - 10, left + 210, title_y - 10)

    meta_x, meta_y, meta_w, meta_h = right - 215, title_y - 49, 215, 80
    c.setFillColor(PALE_BLUE)
    c.setStrokeColor(LINE)
    c.roundRect(meta_x, meta_y, meta_w, meta_h, 8, fill=1, stroke=1)
    issue = document.created_at.strftime("%d %B %Y") if document.created_at else datetime.now(timezone.utc).strftime("%d %B %Y")
    expiry_label = "Valid Until" if document.document_type == "quotation" else "Payment Terms"
    expiry_value = document.valid_until.strftime("%d %B %Y") if document.valid_until else f"{document.payment_terms_days} days"
    for index, (label, value) in enumerate((("Document No.", document.document_number), ("Issue Date", issue), (expiry_label, expiry_value))):
        y = meta_y + meta_h - 20 - index * 23
        c.setFillColor(MUTED); c.setFont("Helvetica-Bold", 8.2); c.drawString(meta_x + 14, y, label)
        c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 9); c.drawRightString(meta_x + meta_w - 14, y, value)

    bill_y = title_y - 105
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 8.8); c.drawString(left, bill_y + 10, "PREPARED FOR")
    c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 11); c.drawString(left, bill_y - 7, document.client_name[:58])
    c.setFillColor(MUTED); c.setFont("Helvetica", 9); c.drawString(left, bill_y - 23, document.recipient_email)
    if document.client_address:
        c.drawString(left, bill_y - 39, document.client_address[:80])

    items = [
        {
            "description": item.description,
            "details": item.details,
            "quantity": item.quantity,
            "rate_minor": item.rate_minor,
            "tax_minor": item.tax_minor,
        }
        for item in document.items[:8]
    ]
    table_bottom = _draw_items(c, items=items, currency=document.currency, left=left, right=right, top=bill_y - 62)

    totals_w, totals_h = 260, 88
    totals_x, totals_y = right - totals_w, table_bottom - 98
    c.setFillColor(colors.white); c.setStrokeColor(LINE)
    c.roundRect(totals_x, totals_y, totals_w, totals_h, 7, fill=1, stroke=1)
    for label, value, ry in (("Subtotal", money(document.subtotal_minor, document.currency), totals_y + 64), ("Tax", money(document.tax_minor, document.currency), totals_y + 42)):
        c.setFillColor(MUTED); c.setFont("Helvetica", 8.8); c.drawString(totals_x + 17, ry, label)
        c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 8.8); c.drawRightString(totals_x + totals_w - 17, ry, value)
    c.setFillColor(PALE_GREEN); c.roundRect(totals_x + 1, totals_y + 1, totals_w - 2, 31, 6, fill=1, stroke=0)
    c.setFillColor(GREEN); c.setFont("Helvetica-Bold", 10); c.drawString(totals_x + 17, totals_y + 11, "TOTAL")
    c.setFont("Helvetica-Bold", 15); c.drawRightString(totals_x + totals_w - 17, totals_y + 9, money(document.total_minor, document.currency))

    note_y = totals_y - 75
    c.setFillColor(MUTED); c.setFont("Helvetica", 8)
    if document.notes:
        c.drawString(left, note_y + 37, "Notes: " + document.notes[:110])
    if document.document_type == "quotation":
        c.drawString(left, note_y + 20, "This quotation is subject to acceptance and remains valid until the date shown above.")
    else:
        c.drawString(left, note_y + 20, "This pro-forma invoice is a request for payment and is not a tax invoice or receipt.")
    _signature(c, left, max(88, note_y - 30))

    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 7.2)
    c.drawString(left, 28, "ithute.co.ls")
    c.drawString(left + 155, 28, FINANCE_SENDER)
    c.drawRightString(right, 28, "Maseru, Lesotho")
    c.setStrokeColor(GREEN); c.setLineWidth(2); c.line(0, 15, width * .55, 15)
    c.setStrokeColor(GOLD); c.line(width * .55, 15, width, 15)
    c.showPage(); c.save()
    return buffer.getvalue()


def render_receipt_pdf(payment: FinancePayment) -> bytes:
    invoice = payment.invoice
    buffer = BytesIO(); c = canvas.Canvas(buffer, pagesize=A4); width, height = A4
    left, right = 40, width - 40
    c.setFillColor(colors.white); c.rect(0, 0, width, height, fill=1, stroke=0)
    header_h = _header(c, width, height)
    y = height - header_h - 45
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 30); c.drawString(left, y, "PAYMENT RECEIPT")
    c.setFillColor(MUTED); c.setFont("Helvetica", 9); c.drawString(left, y - 24, "Official acknowledgement of payment received by Ithute Digital Solutions")
    card_y = y - 225
    c.setFillColor(PALE_BLUE); c.setStrokeColor(LINE); c.roundRect(left, card_y, right-left, 175, 10, fill=1, stroke=1)
    receipt_no = f"RC-{payment.payment_date.year}-{str(payment.id).split('-')[0].upper()}"
    rows = [
        ("Receipt No.", receipt_no), ("Payment Date", payment.payment_date.strftime("%d %B %Y")),
        ("Received From", invoice.client_name), ("Invoice", invoice.invoice_number),
        ("Payment Method", payment.method.replace("_", " ").title()), ("Reference", payment.reference or "—"),
    ]
    ry = card_y + 148
    for label, value in rows:
        c.setFillColor(MUTED); c.setFont("Helvetica-Bold", 8.5); c.drawString(left + 22, ry, label)
        c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 9.5); c.drawString(left + 155, ry, str(value)[:62])
        ry -= 22
    c.setFillColor(PALE_GREEN); c.roundRect(left, card_y - 76, right-left, 58, 9, fill=1, stroke=0)
    c.setFillColor(GREEN); c.setFont("Helvetica-Bold", 11); c.drawString(left + 22, card_y - 44, "AMOUNT RECEIVED")
    c.setFont("Helvetica-Bold", 21); c.drawRightString(right - 22, card_y - 49, money(payment.amount_minor, invoice.currency))
    _signature(c, left, card_y - 170)
    c.setFillColor(MUTED); c.setFont("Helvetica", 8); c.drawString(left, 55, f"Bank: {BANK_NAME}   Account Name: {BANK_ACCOUNT_NAME}   Account Number: {BANK_ACCOUNT_NUMBER}")
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 7.5); c.drawString(left, 32, "ithute.co.ls"); c.drawRightString(right, 32, FINANCE_SENDER)
    c.showPage(); c.save(); return buffer.getvalue()


def render_credit_note_pdf(credit: FinanceCreditNote) -> bytes:
    invoice = credit.invoice
    buffer = BytesIO(); c = canvas.Canvas(buffer, pagesize=A4); width, height = A4
    left, right = 40, width - 40
    c.setFillColor(colors.white); c.rect(0, 0, width, height, fill=1, stroke=0)
    header_h = _header(c, width, height)
    y = height - header_h - 45
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 30); c.drawString(left, y, "CREDIT NOTE")
    c.setFillColor(MUTED); c.setFont("Helvetica", 9); c.drawString(left, y - 24, "Issued against an existing Ithute invoice")
    box_y = y - 220
    c.setFillColor(PALE_BLUE); c.setStrokeColor(LINE); c.roundRect(left, box_y, right-left, 166, 10, fill=1, stroke=1)
    rows = [
        ("Credit Note", credit.credit_number), ("Original Invoice", invoice.invoice_number),
        ("Client", invoice.client_name), ("Issued", credit.created_at.strftime("%d %B %Y") if credit.created_at else date.today().strftime("%d %B %Y")),
        ("Reason", credit.reason),
    ]
    ry = box_y + 139
    for label, value in rows:
        c.setFillColor(MUTED); c.setFont("Helvetica-Bold", 8.5); c.drawString(left + 22, ry, label)
        c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 9.2); c.drawString(left + 150, ry, str(value)[:70])
        ry -= 24
    c.setFillColor(PALE_GREEN); c.roundRect(left, box_y - 76, right-left, 58, 9, fill=1, stroke=0)
    c.setFillColor(GREEN); c.setFont("Helvetica-Bold", 11); c.drawString(left + 22, box_y - 44, "CREDIT AMOUNT")
    c.setFont("Helvetica-Bold", 21); c.drawRightString(right - 22, box_y - 49, money(credit.amount_minor, invoice.currency))
    _signature(c, left, box_y - 170)
    c.showPage(); c.save(); return buffer.getvalue()


def send_document(db: Session, document: FinanceDocument) -> None:
    label = "Quotation" if document.document_type == "quotation" else "Pro-forma Invoice"
    pdf = render_document_pdf(document)
    text = (
        f"Dear {document.client_name},\n\nPlease find attached {document.document_number}, your {label.lower()} from Ithute Digital Solutions.\n\n"
        f"Total: {money(document.total_minor, document.currency)}\n\nKind regards,\nKoetlisi Theko Mofoka\nCEO, Ithute Digital Solutions"
    )
    send_finance_message(
        db,
        recipient=document.recipient_email,
        subject=f"Ithute {label} - {document.document_number}",
        text_body=text,
        html_body=text.replace("\n", "<br>"),
        attachment_filename=f"{document.document_number}.pdf",
        attachment_data=pdf,
    )
    document.status = "sent"
    document.sent_at = datetime.now(timezone.utc)


def convert_document_to_invoice(db: Session, document: FinanceDocument, *, user_id) -> FinanceInvoice:
    if document.converted_invoice_id:
        existing = db.get(FinanceInvoice, document.converted_invoice_id)
        if existing is not None:
            return existing
    if not document.items:
        raise ValueError("Document has no line items")
    issue_date = date.today()
    due_date = issue_date + timedelta(days=document.payment_terms_days)
    first = document.items[0]
    invoice_number = next_invoice_number(db)
    invoice = FinanceInvoice(
        invoice_number=invoice_number,
        client_id=document.client_id,
        client_name=document.client_name,
        recipient_email=document.recipient_email,
        client_address=document.client_address,
        description=first.description,
        details=first.details,
        service_period=issue_date.strftime("%B %Y"),
        quantity=first.quantity,
        rate_minor=first.rate_minor,
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
            description=first.description if len(document.items) == 1 else f"{len(document.items)} services/items",
            total_minor=document.total_minor,
            currency=document.currency,
            due_date=due_date,
        ),
        created_by_user_id=user_id,
    )
    db.add(invoice); db.flush()
    for item in document.items:
        db.add(FinanceInvoiceItem(
            invoice_id=invoice.id,
            position=item.position,
            description=item.description,
            details=item.details,
            quantity=item.quantity,
            rate_minor=item.rate_minor,
            tax_minor=item.tax_minor,
        ))
    document.converted_invoice_id = invoice.id
    document.converted_at = datetime.now(timezone.utc)
    document.status = "converted"
    db.flush()
    return invoice


def load_document(db: Session, document_id) -> FinanceDocument | None:
    return db.scalar(select(FinanceDocument).options(selectinload(FinanceDocument.items)).where(FinanceDocument.id == document_id))


def load_payment(db: Session, payment_id) -> FinancePayment | None:
    return db.scalar(select(FinancePayment).options(selectinload(FinancePayment.invoice)).where(FinancePayment.id == payment_id))


def load_credit(db: Session, credit_id) -> FinanceCreditNote | None:
    return db.scalar(select(FinanceCreditNote).options(selectinload(FinanceCreditNote.invoice)).where(FinanceCreditNote.id == credit_id))
