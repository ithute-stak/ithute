from datetime import date
from decimal import Decimal

from database.multi_tenant_school_management.models import (
    FeeInvoice
)


def process_overdue_invoices(db):

    today = date.today()

    invoices = (
        db.query(FeeInvoice)
        .filter(
            FeeInvoice.balance > 0,
            FeeInvoice.due_date < today
        )
        .all()
    )

    for inv in invoices:

        inv.is_overdue = True

        penalty = (
            Decimal(str(inv.balance))
            * Decimal("0.05")
        )

        inv.penalty_amount += penalty

        inv.balance += penalty

        db.add(inv)

    db.commit()