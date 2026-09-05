import os
from datetime import datetime
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


# =========================================================
# SPACING SYSTEM
# =========================================================
SPACE_XS = 6
SPACE_SM = 12
SPACE_MD = 20
SPACE_LG = 32
SPACE_XL = 48


# =========================================================
# MONEY FORMAT
# =========================================================
def money(value):
    return f"M {Decimal(str(value)):,.2f}"


# =========================================================
# ROUNDED BOX
# =========================================================
def rounded_box(c, x, y, width, height, radius=16,
                fill=colors.white,
                stroke=colors.HexColor("#E5E7EB")):
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.roundRect(x, y, width, height, radius, stroke=1, fill=1)


# =========================================================
# SHADOW CARD
# =========================================================
def shadow_card(c, x, y, width, height, radius=16):
    rounded_box(
        c,
        x + 2, y - 2,
        width, height,
        radius,
        fill=colors.HexColor("#E2E8F0"),
        stroke=colors.HexColor("#E2E8F0")
    )

    rounded_box(
        c,
        x, y,
        width, height,
        radius,
        fill=colors.white,
        stroke=colors.HexColor("#E5E7EB")
    )


# =========================================================
# DIVIDER
# =========================================================
def divider(c, x1, y1, x2, y2):
    c.setStrokeColor(colors.HexColor("#E5E7EB"))
    c.setLineWidth(1)
    c.line(x1, y1, x2, y2)


# =========================================================
# WATERMARK (NEW 🔥)
# =========================================================
def draw_watermark(c, width, height, text):
    c.saveState()

    c.setFont("Helvetica-Bold", 80)
    c.setFillColor(colors.Color(0, 0, 0, alpha=0.08))  # light transparent gray

    c.translate(width / 2, height / 2)
    c.rotate(45)

    c.drawCentredString(0, 0, text)

    c.restoreState()


# =========================================================
# PDF RECEIPT
# =========================================================
def generate_receipt_pdf(
        file_path: str,
        student,
        payment,
        allocation_results,
        remaining_credit,
        total_balance,
        logo_path: str = "media/logo.png"
):
    c = canvas.Canvas(file_path, pagesize=A4)
    width, height = A4

    margin = 40

    # =====================================================
    # WATERMARK (IMPORTANT — draw early)
    # =====================================================
    watermark_text = "PAID" if Decimal(str(total_balance)) == 0 else "COPY"
    draw_watermark(c, width, height, watermark_text)

    # =====================================================
    # PAGE BACKGROUND
    # =====================================================
    c.setFillColor(colors.HexColor("#F8FAFC"))
    c.rect(0, 0, width, height, fill=1, stroke=0)

    # =====================================================
    # MAIN CONTAINER
    shadow_card(c, 25, 25, width - 50, height - 50, radius=24)

    # =====================================================
    # HEADER
    y = height - 70

    if os.path.exists(logo_path):
        try:
            c.drawImage(
                ImageReader(logo_path),
                margin,
                y - 10,
                width=58,
                height=58,
                mask='auto'
            )
        except:
            pass

    c.setFillColor(colors.HexColor("#0F172A"))
    c.setFont("Helvetica-Bold", 24)
    c.drawCentredString(width / 2, y + 10, "PAYMENT RECEIPT")

    c.setFont("Helvetica", 11)
    c.setFillColor(colors.HexColor("#64748B"))
    c.drawCentredString(width / 2, y - 10, "Official School Financial Document")

    # =====================================================
    # STATUS
    status = "FULLY PAID" if Decimal(str(total_balance)) == 0 else "PARTIAL PAYMENT"

    c.setFillColor(colors.HexColor("#DCFCE7" if status == "FULLY PAID" else "#FEF3C7"))
    c.roundRect(width - 190, height - 88, 140, 30, 14, fill=1, stroke=0)

    c.setFillColor(colors.HexColor("#166534" if status == "FULLY PAID" else "#92400E"))
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(width - 120, height - 77, status)

    # =====================================================
    # META
    meta_y = height - 150

    c.setFont("Helvetica", 10)
    c.setFillColor(colors.HexColor("#475569"))

    c.drawRightString(width - margin, meta_y, f"Receipt No: {payment.reference}")
    c.drawRightString(width - margin, meta_y - 18,
                      f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    divider(c, margin, meta_y - 35, width - margin, meta_y - 35)

    # =====================================================
    # PAYMENT HERO
    hero_y = meta_y - 120

    shadow_card(c, margin, hero_y, width - (margin * 2), 90, radius=22)

    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(colors.HexColor("#64748B"))
    c.drawCentredString(width / 2, hero_y + 60, "TOTAL PAYMENT RECEIVED")

    c.setFont("Helvetica-Bold", 28)
    c.setFillColor(colors.HexColor("#0F172A"))
    c.drawCentredString(width / 2, hero_y + 28, money(payment.amount_paid))

    # =====================================================
    # STUDENT CARD
    card_y = hero_y - 150

    shadow_card(c, margin, card_y, width - (margin * 2), 105, radius=20)

    c.setFont("Helvetica-Bold", 13)
    c.setFillColor(colors.HexColor("#0F172A"))
    c.drawString(margin + 20, card_y + 75, "STUDENT INFORMATION")

    divider(c, margin + 20, card_y + 62, width - margin - 20, card_y + 62)

    student_name = f"{student.user.person.first_name} {student.user.person.last_name}"

    c.setFont("Helvetica", 11)
    c.setFillColor(colors.HexColor("#334155"))
    c.drawString(margin + 20, card_y + 38, f"Student Name: {student_name}")
    c.drawString(margin + 20, card_y + 16, f"Admission Number: {student.admission_number}")

    # =====================================================
    # ALLOCATION TABLE
    alloc_y = card_y - 70

    c.setFont("Helvetica-Bold", 15)
    c.setFillColor(colors.HexColor("#0F172A"))
    c.drawString(margin, alloc_y, "PAYMENT ALLOCATION")

    table_y = alloc_y - 280

    shadow_card(c, margin, table_y, width - (margin * 2), 250, radius=20)

    header_y = table_y + 220

    c.setFillColor(colors.HexColor("#F1F5F9"))
    c.roundRect(margin + 10, header_y - 18,
                width - (margin * 2) - 20, 32, 10, fill=1, stroke=0)

    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.HexColor("#0F172A"))

    c.drawString(margin + 20, header_y, "Quarter")
    c.drawString(margin + 180, header_y, "Allocated")
    c.drawString(margin + 340, header_y, "Balance")
    c.drawString(margin + 470, header_y, "Status")

    # =====================================================
    # ROWS
    row_y = header_y - 42

    for a in allocation_results:
        c.setFont("Helvetica", 10)
        c.setFillColor(colors.HexColor("#334155"))

        c.drawString(margin + 20, row_y, str(a.get("quarter", "")))
        c.drawString(margin + 180, row_y, money(a.get("allocated", 0)))
        c.drawString(margin + 340, row_y, money(a.get("balance", 0)))

        status_text = str(a.get("status", "")).upper()

        c.setFillColor(colors.HexColor("#166534" if status_text == "PAID" else "#92400E"))
        c.drawString(margin + 470, row_y, status_text)

        divider(c, margin + 20, row_y - 12, width - margin - 20, row_y - 12)

        row_y -= 42

    # =====================================================
    # SUMMARY
    summary_y = table_y - 160

    shadow_card(c, margin, summary_y, width - (margin * 2), 135, radius=20)

    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(colors.HexColor("#0F172A"))
    c.drawString(margin + 20, summary_y + 100, "FINANCIAL SUMMARY")

    divider(c, margin + 20, summary_y + 88, width - margin - 20, summary_y + 88)

    c.setFont("Helvetica", 11)
    c.setFillColor(colors.HexColor("#334155"))

    c.drawString(margin + 20, summary_y + 58,
                 f"Applied To Fees: {money(payment.amount_paid - remaining_credit)}")
    c.drawString(margin + 20, summary_y + 36,
                 f"Outstanding Balance: {money(total_balance)}")
    c.drawString(margin + 20, summary_y + 14,
                 f"Excess Credit: {money(remaining_credit)}")

    # =====================================================
    # FOOTER
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(colors.HexColor("#94A3B8"))

    c.drawCentredString(
        width / 2,
        45,
        "This receipt is system generated and valid without signature."
    )

    c.save()

    return file_path