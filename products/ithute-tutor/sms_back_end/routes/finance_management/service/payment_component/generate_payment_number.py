from sqlalchemy import func
from datetime import datetime

from database.multi_tenant_school_management.models import FeePayment


def generate_receipt_number(db):
    year = datetime.now().year
    prefix = f"RCT-{year}"

    count = (
        db.query(func.count(FeePayment.id))
        .filter(
            func.extract("year", FeePayment.created_at) == year
        )
        .scalar()
    )

    next_number = count + 1

    return f"{prefix}-{next_number:06d}"