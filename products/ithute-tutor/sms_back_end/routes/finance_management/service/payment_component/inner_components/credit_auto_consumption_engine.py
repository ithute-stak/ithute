from decimal import Decimal

from database.multi_tenant_school_management.models import (
    StudentCredit
)


def apply_existing_credit(
        db,
        student,
        invoices,
        allocation_results
):

    credits = (
        db.query(StudentCredit)
        .filter(
            StudentCredit.student_id == student.id,
            StudentCredit.amount > 0
        )
        .order_by(StudentCredit.created_at.asc())
        .all()
    )

    for invoice in invoices:

        if invoice.balance <= 0:
            continue

        invoice_balance = Decimal(str(invoice.balance))

        for credit in credits:

            if credit.amount <= 0:
                continue

            use_amount = min(
                Decimal(str(credit.amount)),
                invoice_balance
            )

            invoice.amount_paid = (
                Decimal(str(invoice.amount_paid))
                + use_amount
            )

            invoice.balance = (
                invoice_balance
                - use_amount
            )

            invoice.status = (
                "paid"
                if invoice.balance == 0
                else "partial"
            )

            credit.amount = (
                Decimal(str(credit.amount))
                - use_amount
            )

            invoice_balance = Decimal(str(invoice.balance))

            db.add(invoice)
            db.add(credit)

            allocation_results.append({
                "type": "credit",
                "quarter": invoice.quarter,
                "allocated": str(use_amount),
                "status": invoice.status
            })

            if invoice.balance == 0:
                break