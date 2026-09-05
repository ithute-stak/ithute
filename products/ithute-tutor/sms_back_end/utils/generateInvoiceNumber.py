from sqlalchemy import select
from sqlalchemy.orm import Session
from datetime import datetime

from database.finace_management.models.invoice_counter import InvoiceCounter


def generate_invoice_number(db: Session):
    year = str(datetime.now().year)

    counter = (
        db.query(InvoiceCounter)
        .filter(InvoiceCounter.year == year)
        .with_for_update()
        .first()
    )

    if not counter:
        counter = InvoiceCounter(year=year, last_number=0)
        db.add(counter)
        db.flush()

    counter.last_number += 1
    number = counter.last_number

    if number > 99_999_999:
        raise Exception("Invoice limit reached for the year")

    invoice_number = f"INV-{year}-{number:08d}"

    return invoice_number