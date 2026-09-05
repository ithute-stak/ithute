from sqlalchemy import func

from database.multi_tenant_school_management.models import (
    FeeInvoice,
    FeePayment
)


def finance_dashboard(db):

    total_collected = (
        db.query(
            func.sum(FeePayment.amount_paid)
        )
        .scalar()
    )

    total_outstanding = (
        db.query(
            func.sum(FeeInvoice.balance)
        )
        .scalar()
    )

    unpaid_students = (
        db.query(FeeInvoice.student_id)
        .filter(FeeInvoice.balance > 0)
        .distinct()
        .count()
    )

    monthly_collection = (
        db.query(
            func.date_trunc(
                "month",
                FeePayment.created_at
            ).label("month"),

            func.sum(
                FeePayment.amount_paid
            )
        )
        .group_by("month")
        .all()
    )

    return {
        "total_collected": str(total_collected or 0),
        "total_outstanding": str(total_outstanding or 0),
        "unpaid_students": unpaid_students,

        "monthly_collection": [
            {
                "month": str(m[0]),
                "amount": str(m[1])
            }
            for m in monthly_collection
        ]
    }