from decimal import Decimal

from database.multi_tenant_school_management.models import (
    FeeInvoice,
    FeePayment,
    StudentCredit
)


def get_student_statement(db,student_id):

    invoices = (
        db.query(FeeInvoice)
        .filter(FeeInvoice.student_id == student_id)
        .order_by(FeeInvoice.period_start.asc())
        .all()
    )

    payments = (
        db.query(FeePayment)
        .filter(FeePayment.student_id == student_id)
        .all()
    )

    credits = (
        db.query(StudentCredit)
        .filter(StudentCredit.student_id == student_id)
        .all()
    )

    total_due = Decimal("0.00")
    total_paid = Decimal("0.00")
    total_balance = Decimal("0.00")

    invoice_data = []

    for inv in invoices:

        total_due += Decimal(str(inv.amount_due))
        total_paid += Decimal(str(inv.amount_paid))
        total_balance += Decimal(str(inv.balance))

        invoice_data.append({
            "invoice_number": inv.invoice_number,
            "quarter": inv.quarter,
            "amount_due": str(inv.amount_due),
            "amount_paid": str(inv.amount_paid),
            "balance": str(inv.balance),
            "status": inv.status
        })

    return {
        "student_id": str(student_id),

        "summary": {
            "total_due": str(total_due),
            "total_paid": str(total_paid),
            "total_balance": str(total_balance)
        },

        "invoices": invoice_data,

        "payments": [
            {
                "payment_id": str(p.id),
                "amount_paid": str(p.amount_paid),
                "method": p.payment_method,
                "reference": p.reference
            }
            for p in payments
        ],

        "credits": [
            {
                "credit_id": str(c.id),
                "amount": str(c.amount)
            }
            for c in credits
        ]
    }