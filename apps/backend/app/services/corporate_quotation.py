from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.models import FinanceDocument
from app.services.finance_invoices import money

NAVY = HexColor("#0B4F91")
GREEN = HexColor("#0B6B3A")
LIGHT = HexColor("#F4F8F5")
MID = HexColor("#DCE7E1")
TEXT = HexColor("#17312A")
MUTED = HexColor("#5A6B65")
_ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"
_HEADER_PATH = _ASSET_DIR / "finance_invoice_header.jpg"
PREFIX = "ITHUTE_CORPORATE_QUOTE_V1:"


def pack_metadata(meta: dict, notes: str = "") -> str:
    payload = dict(meta)
    payload["notes"] = notes.strip()
    return PREFIX + json.dumps(payload, separators=(",", ":"), ensure_ascii=True)


def unpack_metadata(value: str | None) -> dict:
    raw = value or ""
    if not raw.startswith(PREFIX):
        return {}
    try:
        data = json.loads(raw[len(PREFIX):])
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _header(c: canvas.Canvas, width: float, height: float) -> float:
    h = width * 270 / 1103
    if _HEADER_PATH.is_file():
        c.drawImage(ImageReader(str(_HEADER_PATH)), 0, height - h, width=width, height=h, preserveAspectRatio=False)
    return h


def _footer(c: canvas.Canvas, page: int, width: float) -> None:
    c.setStrokeColor(MID); c.setLineWidth(.5); c.line(30, 28, width - 30, 28)
    c.setFillColor(MUTED); c.setFont("Helvetica", 7.4)
    c.drawString(30, 16, "Ithute Solutions / iMail - Learn Anywhere. Succeed Everywhere.")
    c.drawRightString(width - 30, 16, f"Page {page}")


def _fit(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _money(amount: int) -> str:
    return money(amount, "LSL")


def render_corporate_quote_pdf(document: FinanceDocument) -> bytes:
    meta = unpack_metadata(document.notes)
    if not meta:
        raise ValueError("Document is not a corporate quotation")
    buffer = BytesIO(); c = canvas.Canvas(buffer, pagesize=A4); width, height = A4
    left, right = 34, width - 34
    mailbox_count = int(meta.get("mailbox_count") or 20)
    storage_gb = int(meta.get("storage_gb") or 50)
    total_gb = mailbox_count * storage_gb
    monthly = int(meta.get("monthly_total_minor") or 0)
    quarterly = int(meta.get("quarterly_total_minor") or 0)
    annual = int(meta.get("annual_total_minor") or document.total_minor)
    retail_monthly = int(meta.get("retail_monthly_minor") or mailbox_count * 40000)
    emails = [document.recipient_email] + [str(x) for x in meta.get("recipient_cc", []) if str(x).strip()]
    issue = document.created_at.strftime("%d %B %Y") if document.created_at else datetime.now(timezone.utc).strftime("%d %B %Y")
    validity = int(meta.get("validity_days") or 30)

    # page 1
    c.setFillColor(colors.white); c.rect(0, 0, width, height, fill=1, stroke=0)
    header_h = _header(c, width, height)
    y = height - header_h - 26
    c.setFillColor(GREEN); c.setFont("Helvetica-Bold", 22); c.drawCentredString(width / 2, y, "CORPORATE EMAIL HOSTING QUOTATION")
    c.setFillColor(MUTED); c.setFont("Helvetica", 9.2)
    c.drawCentredString(width / 2, y - 20, f"{mailbox_count} professional mailboxes | {storage_gb} GB per mailbox | {total_gb/1000:g} TB total allocated mailbox capacity")

    box_top = y - 44; row_h = 23; box_h = row_h * 3
    c.setStrokeColor(MID); c.rect(left, box_top - box_h, right-left, box_h, fill=0, stroke=1)
    mid = left + (right-left)/2
    c.line(mid, box_top, mid, box_top-box_h)
    rows = [
        (("Quotation No.", document.document_number), ("Date", issue)),
        (("Prepared for", document.client_name), ("Validity", f"{validity} days")),
        (("Email", ", ".join(emails)), ("Prepared by", meta.get("prepared_by") or "Koetlisi Theko")),
    ]
    for i, pair in enumerate(rows):
        yy = box_top - i*row_h - 15
        if i: c.line(left, box_top-i*row_h, right, box_top-i*row_h)
        for offset, (label, value) in ((0, pair[0]), (mid-left, pair[1])):
            x = left + offset + 9
            c.setFillColor(MUTED); c.setFont("Helvetica-Bold", 7.6); c.drawString(x, yy, label)
            c.setFillColor(TEXT); c.setFont("Helvetica", 7.8); c.drawString(x + 72, yy, _fit(str(value), 48))

    y = box_top - box_h - 26
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 12); c.drawString(left, y, "Executive Summary")
    c.setFillColor(TEXT); c.setFont("Helvetica", 8.5)
    summary = (f"Ithute Solutions is pleased to provide {document.client_name} with a managed iMail business email package comprising "
               f"{mailbox_count} professional mailboxes, each with {storage_gb} GB of storage. The combined allocation is approximately "
               f"{total_gb/1000:g} TB. The service includes secure mailbox access, migration assistance, DNS/MX cutover support, mailbox setup and ongoing technical support.")
    words = summary.split(); line = ""; yy = y - 17
    for word in words:
        test = (line + " " + word).strip()
        if c.stringWidth(test, "Helvetica", 8.5) > right-left:
            c.drawString(left, yy, line); yy -= 12; line = word
        else: line = test
    if line: c.drawString(left, yy, line); yy -= 16

    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 12); c.drawString(left, yy, "Commercial Options"); yy -= 18
    widths = [92, 92, 112, 145, 87]; labels = ["Billing", "Price", "Effective / month", "Per mailbox / month", "Saving"]
    x = left
    c.setFillColor(GREEN); c.rect(left, yy-22, sum(widths), 22, fill=1, stroke=0); c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 7.3)
    for w, label in zip(widths, labels): c.drawCentredString(x+w/2, yy-14, label); x += w
    options = [
        ("Monthly", monthly, monthly, monthly//max(1, mailbox_count), max(0, 1 - monthly/max(1, retail_monthly))),
        ("Quarterly", quarterly, quarterly//3, quarterly//3//max(1, mailbox_count), max(0, 1 - (quarterly/3)/max(1, retail_monthly))),
        ("Annual", annual, annual//12, annual//12//max(1, mailbox_count), max(0, 1 - (annual/12)/max(1, retail_monthly))),
    ]
    yy -= 22
    for idx, (label, price, eff, per, saving) in enumerate(options):
        c.setFillColor(colors.white if idx % 2 == 0 else LIGHT); c.rect(left, yy-24, sum(widths), 24, fill=1, stroke=0)
        values = [label, _money(price), _money(eff), _money(per), f"{saving*100:.2f}%".rstrip("0").rstrip(".")]
        x = left; c.setFillColor(TEXT); c.setFont("Helvetica-Bold" if label == "Annual" else "Helvetica", 7.8)
        for w, value in zip(widths, values): c.drawCentredString(x+w/2, yy-15, value); x += w
        yy -= 24

    yy -= 12; c.setFillColor(NAVY); c.rect(left+18, yy-88, right-left-36, 88, fill=1, stroke=0)
    c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 8.5); c.drawCentredString(width/2, yy-17, "RECOMMENDED ANNUAL PACKAGE")
    c.setFillColor(LIGHT); c.rect(left+19, yy-87, right-left-38, 64, fill=1, stroke=0)
    c.setFillColor(GREEN); c.setFont("Helvetica-Bold", 17); c.drawCentredString(width/2, yy-48, f"{_money(annual)} / year")
    c.setFillColor(MUTED); c.setFont("Helvetica", 7.8); c.drawCentredString(width/2, yy-66, f"Equivalent to {_money(annual//12)}/month, or {_money(annual//12//max(1, mailbox_count))} per {storage_gb} GB mailbox per month.")
    saving_amount = max(0, retail_monthly*12-annual)
    c.drawCentredString(width/2, yy-80, f"Annual saving: {_money(saving_amount)} compared with standard retail value of {_money(retail_monthly*12)}/year.")
    _footer(c, 1, width); c.showPage()

    # page 2
    c.setFillColor(colors.white); c.rect(0,0,width,height,fill=1,stroke=0)
    y = height - 48
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 13); c.drawString(left, y, "Service Inclusions"); y -= 18
    inclusions = [
        f"{mailbox_count} business email accounts", f"{storage_gb} GB allocated per mailbox", f"{total_gb/1000:g} TB total mailbox allocation",
        "Secure webmail access", "IMAP and SMTP access", "TLS/SSL secured connections", "Spam and abuse controls",
        "Migration assistance", "DNS and MX configuration support", "Mailbox setup and standard support",
    ]
    for i in range(0, len(inclusions), 2):
        c.setFillColor(LIGHT); c.rect(left, y-22, right-left, 22, fill=1, stroke=0); c.setFillColor(TEXT); c.setFont("Helvetica", 8.2)
        c.drawString(left+10, y-14, "• " + inclusions[i])
        if i+1 < len(inclusions): c.drawString(left+270, y-14, "• " + inclusions[i+1])
        y -= 22

    y -= 15; c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 13); c.drawString(left, y, "Email Migration & Cutover"); y -= 17
    c.setFillColor(TEXT); c.setFont("Helvetica", 8.1); c.drawString(left, y, "The previous provider should remain active during migration. Ithute uses a staged process intended to preserve existing mail while reducing downtime."); y -= 16
    steps = [
        ("1", "Initial copy", "Copy existing folders and messages from the current provider."),
        ("2", "Parallel operation", "Keep the old service active while migrated data is checked."),
        ("3", "Incremental sync", "Copy messages that arrived after the first migration pass."),
        ("4", "MX cutover", "Update DNS mail-routing records to direct new email to iMail."),
        ("5", "Final sync", "Capture remaining messages from the previous provider."),
        ("6", "Verification", "Confirm access and migration status before retiring the old service."),
    ]
    for no, title, desc in steps:
        c.setFillColor(GREEN); c.rect(left, y-23, 24, 23, fill=1, stroke=0); c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 8); c.drawCentredString(left+12, y-15, no)
        c.setFillColor(LIGHT); c.rect(left+24, y-23, right-left-24, 23, fill=1, stroke=0); c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 7.8); c.drawString(left+34, y-15, title)
        c.setFont("Helvetica", 7.5); c.drawString(left+132, y-15, desc); y -= 23

    y -= 14; c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 13); c.drawString(left, y, "Commercial Terms"); y -= 17
    terms = [
        ("Validity", f"{validity} days from issue date."),
        ("Monthly", f"{_money(monthly)} payable at the start of each monthly billing cycle."),
        ("Quarterly", f"{_money(quarterly)} payable at the start of each 3-month billing cycle."),
        ("Annual", f"{_money(annual)} payable upfront for 12 months of service."),
        ("Additional mailboxes", "Accounts beyond the quoted allocation will be quoted separately or billed at the prevailing package rate."),
        ("Domain", "Domain registration/renewal remains the client's responsibility unless separately agreed."),
        ("Acceptable use", "No spam, unlawful bulk messaging, malware distribution or activity that threatens service/IP reputation."),
    ]
    for idx, (label, value) in enumerate(terms):
        c.setFillColor(colors.white if idx%2==0 else LIGHT); c.rect(left, y-22, right-left, 22, fill=1, stroke=0)
        c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 7.4); c.drawString(left+8, y-14, label); c.setFont("Helvetica", 7.2); c.drawString(left+122, y-14, _fit(value, 96)); y -= 22

    y -= 13; c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 13); c.drawString(left, y, "Acceptance & Next Steps"); y -= 18
    c.setFillColor(TEXT); c.setFont("Helvetica", 8)
    c.drawString(left, y, f"To proceed, {document.client_name} may confirm the preferred billing option and provide the domain name(s), mailbox list and migration access details.")
    y -= 14; c.drawString(left, y, "Ithute will then agree a migration and cutover window before production DNS changes are made.")
    y -= 38; c.setFillColor(LIGHT); c.rect(left, y-48, right-left, 48, fill=1, stroke=0)
    c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 8.2); c.drawString(left+12, y-16, meta.get("prepared_by") or "Koetlisi Theko")
    c.setFont("Helvetica", 7.8); c.drawString(left+12, y-31, "Ithute Solutions / iMail")
    c.setFont("Helvetica-Bold", 7.8); c.drawString(left+275, y-16, "Email:")
    c.setFont("Helvetica", 7.8); c.drawString(left+315, y-16, meta.get("prepared_email") or "thekoetlisi@ithute.co.ls")
    c.setFont("Helvetica-Bold", 7.8); c.drawString(left+275, y-30, "Tel:"); c.setFont("Helvetica", 7.8); c.drawString(left+315, y-30, meta.get("prepared_phone") or "+266 5900 1394")
    c.setFont("Helvetica-Bold", 7.8); c.drawString(left+275, y-44, "Web:"); c.setFont("Helvetica", 7.8); c.drawString(left+315, y-44, "https://ithute.co.ls")
    _footer(c, 2, width); c.showPage(); c.save(); return buffer.getvalue()
