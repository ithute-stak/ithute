from decimal import Decimal

from sqlalchemy.orm import Session
from dateutil.relativedelta import relativedelta

from database.multi_tenant_school_management.models import (
    FeeInvoice
)

from utils.generateInvoiceNumber import (
    generate_invoice_number
)


def create_student_quarter_invoices(
    db: Session,
    student,
    fee_plan,
    fee_config
):

    existing = (
        db.query(FeeInvoice)
        .filter(
            FeeInvoice.student_id == student.id,
            FeeInvoice.fee_plan_id == fee_plan.id
        )
        .first()
    )

    if existing:
        return

    quarter_amounts = [
        Decimal(str(fee_plan.first_quarter)),
        Decimal(str(fee_plan.second_quarter)),
        Decimal(str(fee_plan.third_quarter)),
        Decimal(str(fee_plan.fourth_quarter)),
    ]

    current_start = fee_config.year_start

    for i in range(4):

        if i == 3:
            quarter_end = fee_config.year_end
        else:
            quarter_end = (
                current_start
                + relativedelta(months=3)
                - relativedelta(days=1)
            )

        amount_due = quarter_amounts[i]

        invoice = FeeInvoice(
            invoice_number=generate_invoice_number(db),
            student_id=student.id,
            school_id=student.user.school_id,
            fee_plan_id=fee_plan.id,
            quarter=f"Q{i+1}",
            description=f"Quarter {i+1}",
            period_start=current_start,
            period_end=quarter_end,
            amount_due=amount_due,
            amount_paid=Decimal("0.00"),
            balance=amount_due,
            status="unpaid"
        )

        db.add(invoice)

        current_start = (
            quarter_end
            + relativedelta(days=1)
        )

    db.flush()