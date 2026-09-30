from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.models import FinanceInvoice
from app.services.finance_invoice_v2 import render_invoice_pdf as render_single_item_invoice_pdf
from app.services.finance_invoices import (
    AUTHORISED_NAME,
    AUTHORISED_TITLE,
    BANK_ACCOUNT_NAME,
    BANK_ACCOUNT_NUMBER,
    BANK_NAME,
    FINANCE_SENDER,
    money,
)

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


def _header(c: canvas.Canvas, width: float, height: float) -> float:
    header_h = width * 270 / 1103
    c.drawImage(ImageReader(str(_HEADER_PATH)), 0, height - header_h, width=width, height=header_h, preserveAspectRatio=False)
    return header_h


def _signature(c: canvas.Canvas, x: float, y: float) -> None:
    c.drawImage(ImageReader(str(_SIGNATURE_PATH)), x + 10, y + 5, width=128, height=55, preserveAspectRatio=True, mask="auto")
    c.setStrokeColor(NAVY); c.line(x, y, x + 205, y)
    c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 9.2); c.drawString(x, y - 15, AUTHORISED_NAME)
    c.setFillColor(MUTED); c.setFont("Helvetica", 8); c.drawString(x, y - 29, AUTHORISED_TITLE)


def render_invoice_pdf(invoice: FinanceInvoice, *, include_stamp: bool = False) -> bytes:
    items = list(getattr(invoice, "items", []) or [])
    if len(items) <= 1:
        return render_single_item_invoice_pdf(invoice, include_stamp=include_stamp)

    buffer = BytesIO(); c = canvas.Canvas(buffer, pagesize=A4); width, height = A4
    left, right = 30, width - 30
    c.setTitle(f"Invoice {invoice.invoice_number}")
    c.setFillColor(colors.white); c.rect(0, 0, width, height, fill=1, stroke=0)
    header_h = _header(c, width, height)
    title_y = height - header_h - 36
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 30); c.drawString(left, title_y, "INVOICE")
    c.setStrokeColor(GREEN); c.setLineWidth(2); c.line(left, title_y - 10, left + 145, title_y - 10)
    c.setStrokeColor(GOLD); c.line(left + 145, title_y - 10, left + 210, title_y - 10)
    c.setFillColor(MUTED); c.setFont("Helvetica", 9.5); c.drawString(left, title_y - 27, "Professional Email & Digital Solutions for Your Business")

    meta_x, meta_y, meta_w, meta_h = right - 215, title_y - 50, 215, 82
    c.setFillColor(PALE_BLUE); c.setStrokeColor(LINE); c.roundRect(meta_x, meta_y, meta_w, meta_h, 8, fill=1, stroke=1)
    issue = invoice.created_at.strftime("%d %B %Y") if invoice.created_at else datetime.now(timezone.utc).strftime("%d %B %Y")
    for index, (label, value) in enumerate((("Invoice No.", invoice.invoice_number), ("Issue Date", issue), ("Due Date", invoice.due_date.strftime("%d %B %Y")))):
        y = meta_y + meta_h - 21 - index * 24
        c.setFillColor(MUTED); c.setFont("Helvetica-Bold", 8.4); c.drawString(meta_x + 14, y, label)
        c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 9.2); c.drawRightString(meta_x + meta_w - 14, y, value)

    bill_y = title_y - 108
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 8.8); c.drawString(left, bill_y + 10, "BILLED TO")
    c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 11); c.drawString(left, bill_y - 7, invoice.client_name[:60])
    c.setFillColor(MUTED); c.setFont("Helvetica", 9); c.drawString(left, bill_y - 23, invoice.recipient_email)
    if invoice.client_address: c.drawString(left, bill_y - 39, invoice.client_address[:80])

    visible = items[:8]
    row_h, head_h = 35, 25
    top = bill_y - 60; table_h = head_h + row_h * len(visible); table_w = right - left
    c.setFillColor(colors.white); c.setStrokeColor(LINE); c.roundRect(left, top-table_h, table_w, table_h, 6, fill=1, stroke=1)
    c.setFillColor(PALE_BLUE); c.roundRect(left, top-head_h, table_w, head_h, 6, fill=1, stroke=0); c.rect(left, top-head_h, table_w, 6, fill=1, stroke=0)
    x_qty, x_rate, x_amount = 345, 435, 525
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 8.2)
    c.drawString(left+12, top-16, "DESCRIPTION"); c.drawCentredString(x_qty, top-16, "QTY"); c.drawCentredString(x_rate, top-16, "RATE (M)"); c.drawCentredString(x_amount, top-16, "AMOUNT (M)")
    for vx in (312, 375, 470): c.line(vx, top, vx, top-table_h)
    y = top - head_h - 21
    for item in visible:
        desc = item.description if len(item.description) <= 52 else item.description[:49] + "..."
        c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 8.1); c.drawString(left+12, y, desc)
        if item.details:
            c.setFillColor(MUTED); c.setFont("Helvetica", 6.7); c.drawString(left+12, y-10, item.details[:70])
        c.setFillColor(TEXT); c.setFont("Helvetica", 8.1); c.drawCentredString(x_qty, y, str(item.quantity)); c.drawRightString(457, y, money(item.rate_minor, invoice.currency))
        c.setFont("Helvetica-Bold", 8.1); c.drawRightString(right-12, y, money(item.quantity * item.rate_minor, invoice.currency)); y -= row_h

    table_bottom = top - table_h
    totals_w, totals_h = 260, 88; totals_x, totals_y = right-totals_w, table_bottom-96
    c.setFillColor(colors.white); c.setStrokeColor(LINE); c.roundRect(totals_x, totals_y, totals_w, totals_h, 7, fill=1, stroke=1)
    for label, value, ry in (("Subtotal", money(invoice.subtotal_minor, invoice.currency), totals_y+64), ("Tax", money(invoice.tax_minor, invoice.currency), totals_y+42)):
        c.setFillColor(MUTED); c.setFont("Helvetica", 8.8); c.drawString(totals_x+17, ry, label); c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 8.8); c.drawRightString(totals_x+totals_w-17, ry, value)
    c.setFillColor(PALE_GREEN); c.roundRect(totals_x+1, totals_y+1, totals_w-2, 31, 6, fill=1, stroke=0)
    c.setFillColor(GREEN); c.setFont("Helvetica-Bold", 10); c.drawString(totals_x+17, totals_y+11, "TOTAL DUE"); c.setFont("Helvetica-Bold", 15); c.drawRightString(totals_x+totals_w-17, totals_y+9, money(invoice.total_minor, invoice.currency))

    cards_y = max(168, totals_y - 112); card_h = 88; gap = 14; card_w = (table_w-gap)/2
    c.setFillColor(colors.white); c.setStrokeColor(LINE); c.roundRect(left, cards_y, card_w, card_h, 7, fill=1, stroke=1); c.roundRect(left+card_w+gap, cards_y, card_w, card_h, 7, fill=1, stroke=1)
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 8.8); c.drawString(left+14, cards_y+card_h-21, "PAYMENT DETAILS")
    c.setFillColor(TEXT); c.setFont("Helvetica", 7.6); c.drawString(left+14, cards_y+card_h-40, f"Bank: {BANK_NAME}"); c.drawString(left+14, cards_y+card_h-55, f"Account Name: {BANK_ACCOUNT_NAME}"); c.drawString(left+14, cards_y+card_h-70, f"Account Number: {BANK_ACCOUNT_NUMBER}")
    nx = left+card_w+gap+14; c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 8.8); c.drawString(nx, cards_y+card_h-21, "NOTE")
    c.setFillColor(MUTED); c.setFont("Helvetica", 7.7); c.drawString(nx, cards_y+card_h-40, "Thank you for choosing Ithute Solutions."); c.drawString(nx, cards_y+card_h-55, "Use the invoice number or client name"); c.drawString(nx, cards_y+card_h-70, "as the payment reference.")
    _signature(c, left, 86)
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 7.2); c.drawString(left, 28, "ithute.co.ls"); c.drawString(left+155, 28, FINANCE_SENDER); c.drawRightString(right, 28, "Maseru, Lesotho")
    c.setStrokeColor(GREEN); c.setLineWidth(2); c.line(0, 15, width*.55, 15); c.setStrokeColor(GOLD); c.line(width*.55, 15, width, 15)
    c.showPage(); c.save(); return buffer.getvalue()
