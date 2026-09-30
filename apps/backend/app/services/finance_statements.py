from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.models import FinanceClient, FinanceInvoice
from app.services.finance_ledger import invoice_financial_out
from app.services.finance_invoices import FINANCE_SENDER

NAVY = HexColor("#062D63")
GREEN = HexColor("#087743")
GOLD = HexColor("#D5A62F")
MUTED = HexColor("#667A96")
TEXT = HexColor("#102E59")
LINE = HexColor("#C8DCEC")
PALE_BLUE = HexColor("#F1F7FC")
_ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"
_HEADER_PATH = _ASSET_DIR / "finance_invoice_header.jpg"


def _money(minor: int) -> str:
    return f"M {minor / 100:,.2f}"


def client_payment_behaviour(client: FinanceClient, invoices: list[FinanceInvoice], *, today: date | None = None) -> dict:
    current = today or date.today()
    rows = [invoice_financial_out(invoice) for invoice in invoices if invoice.status != "cancelled"]
    settled_days: list[int] = []
    settled_count = on_time_count = late_count = 0
    overdue_open_count = 0
    max_days_overdue = 0
    current_exposure = 0

    for invoice, row in zip([i for i in invoices if i.status != "cancelled"], rows):
        current_exposure += row["outstanding_minor"]
        if row["outstanding_minor"] > 0 and invoice.due_date < current and row["status"] not in {"draft", "failed"}:
            overdue_open_count += 1
            max_days_overdue = max(max_days_overdue, (current - invoice.due_date).days)
        if row["status"] == "paid" and invoice.payments:
            settlement_date = max(payment.payment_date for payment in invoice.payments)
            issued = invoice.created_at.date() if invoice.created_at else settlement_date
            settled_days.append(max(0, (settlement_date - issued).days))
            settled_count += 1
            if settlement_date <= invoice.due_date:
                on_time_count += 1
            else:
                late_count += 1

    average_days = round(sum(settled_days) / len(settled_days), 1) if settled_days else None
    on_time_percent = round((on_time_count / settled_count) * 100, 1) if settled_count else None
    return {
        "client_id": str(client.id),
        "client_name": client.name,
        "invoice_count": len(rows),
        "settled_invoice_count": settled_count,
        "on_time_invoice_count": on_time_count,
        "late_invoice_count": late_count,
        "on_time_percent": on_time_percent,
        "average_days_to_pay": average_days,
        "open_overdue_invoice_count": overdue_open_count,
        "max_days_overdue": max_days_overdue,
        "current_exposure_minor": current_exposure,
    }


def render_statement_pdf(client: FinanceClient, invoices: list[FinanceInvoice], *, as_of: date | None = None) -> bytes:
    statement_date = as_of or date.today()
    rows = [invoice_financial_out(invoice) for invoice in invoices if invoice.status != "cancelled"]
    balance = sum(row["outstanding_minor"] for row in rows)
    invoiced = sum(row["total_minor"] for row in rows)
    credited = sum(row.get("credited_minor", 0) for row in rows)
    refunded = sum(row.get("refunded_minor", 0) for row in rows)
    paid = sum(row["paid_minor"] for row in rows)

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    left, right = 32, width - 32
    c.setTitle(f"Statement - {client.name} - {statement_date.isoformat()}")
    c.setFillColor(colors.white); c.rect(0, 0, width, height, fill=1, stroke=0)
    header_h = width * 270 / 1103
    c.drawImage(ImageReader(str(_HEADER_PATH)), 0, height - header_h, width=width, height=header_h, preserveAspectRatio=False)

    y = height - header_h - 32
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 25); c.drawString(left, y, "STATEMENT OF ACCOUNT")
    c.setStrokeColor(GREEN); c.setLineWidth(2); c.line(left, y - 9, left + 190, y - 9)
    c.setStrokeColor(GOLD); c.line(left + 190, y - 9, left + 260, y - 9)
    c.setFillColor(MUTED); c.setFont("Helvetica", 8.8); c.drawRightString(right, y, f"As at {statement_date.strftime('%d %B %Y')}")

    y -= 48
    c.setFillColor(PALE_BLUE); c.setStrokeColor(LINE); c.roundRect(left, y - 68, right - left, 68, 7, fill=1, stroke=1)
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 8.5); c.drawString(left + 14, y - 18, "ACCOUNT HOLDER")
    c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 11); c.drawString(left + 14, y - 35, client.name[:70])
    c.setFillColor(MUTED); c.setFont("Helvetica", 8.3); c.drawString(left + 14, y - 50, client.email)
    if client.address:
        c.drawRightString(right - 14, y - 35, client.address[:55])

    y -= 92
    cards = [("Invoiced", invoiced), ("Credits", credited), ("Net paid", paid), ("Balance", balance)]
    card_gap = 8; card_w = (right - left - card_gap * 3) / 4
    for idx, (label, amount) in enumerate(cards):
        x = left + idx * (card_w + card_gap)
        c.setFillColor(colors.white); c.setStrokeColor(LINE); c.roundRect(x, y - 52, card_w, 52, 6, fill=1, stroke=1)
        c.setFillColor(MUTED); c.setFont("Helvetica-Bold", 7.5); c.drawString(x + 9, y - 16, label.upper())
        c.setFillColor(GREEN if label == "Balance" else TEXT); c.setFont("Helvetica-Bold", 10.5); c.drawString(x + 9, y - 35, _money(amount))

    y -= 78
    table_top = y
    c.setFillColor(PALE_BLUE); c.setStrokeColor(LINE); c.roundRect(left, table_top - 24, right - left, 24, 5, fill=1, stroke=1)
    headers = [(left + 8, "INVOICE"), (left + 92, "ISSUED"), (left + 155, "DUE"), (left + 218, "STATUS"), (right - 145, "NET TOTAL"), (right - 64, "BALANCE")]
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 7.2)
    for x, label in headers:
        c.drawString(x, table_top - 15, label)

    y = table_top - 24
    visible = rows[-15:]
    for row in visible:
        y -= 25
        if y < 78:
            break
        c.setStrokeColor(LINE); c.line(left, y - 6, right, y - 6)
        c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 7.4); c.drawString(left + 8, y + 4, row["invoice_number"][:18])
        c.setFont("Helvetica", 7.2); c.drawString(left + 92, y + 4, (row.get("created_at") or "")[:10])
        c.drawString(left + 155, y + 4, row["due_date"][:10]); c.drawString(left + 218, y + 4, row["status"].upper()[:12])
        c.drawRightString(right - 75, y + 4, _money(row.get("adjusted_total_minor", row["total_minor"])))
        c.setFont("Helvetica-Bold", 7.3); c.drawRightString(right - 8, y + 4, _money(row["outstanding_minor"]))

    c.setFillColor(MUTED); c.setFont("Helvetica", 7.3)
    c.drawString(left, 54, f"Refunds recorded to date: {_money(refunded)}")
    c.drawString(left, 40, "Please use the invoice number or client name as the payment reference.")
    c.drawRightString(right, 40, FINANCE_SENDER)
    c.setStrokeColor(GREEN); c.setLineWidth(2); c.line(0, 18, width * .55, 18); c.setStrokeColor(GOLD); c.line(width * .55, 18, width, 18)
    c.showPage(); c.save()
    return buffer.getvalue()


def render_statement_pack(clients_with_invoices: list[tuple[FinanceClient, list[FinanceInvoice]]], *, as_of: date | None = None) -> bytes:
    statement_date = as_of or date.today()
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for client, invoices in clients_with_invoices:
            if not invoices:
                continue
            safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in client.name).strip("_") or str(client.id)
            archive.writestr(
                f"{safe}-statement-{statement_date.isoformat()}.pdf",
                render_statement_pdf(client, invoices, as_of=statement_date),
            )
    return output.getvalue()
