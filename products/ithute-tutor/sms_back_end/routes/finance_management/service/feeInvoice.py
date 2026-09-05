from uuid import UUID

from sqlalchemy.orm import Session

from database.finace_management.models.feeInvoice import FeeInvoice
from database.finace_management.schemas.feeInvoice import FeeInvoiceCreate, FeeInvoiceUpdate


def create_fee_invoice(db: Session, payload: FeeInvoiceCreate, school_id: UUID):
    data = payload.model_dump(exclude={"school_id"})
    data["school_id"] = school_id
    data["balance"] = data["amount_due"] - data["amount_paid"]
    invoice = FeeInvoice(**data)
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


def get_fee_invoices(db: Session, school_id: UUID):
    return db.query(FeeInvoice).filter(FeeInvoice.school_id == school_id).all()


def get_fee_invoice(db: Session, invoice_id: UUID, school_id: UUID):
    return (
        db.query(FeeInvoice)
        .filter(FeeInvoice.id == invoice_id, FeeInvoice.school_id == school_id)
        .first()
    )


def update_fee_invoice(
    db: Session,
    invoice_id: UUID,
    payload: FeeInvoiceUpdate,
    school_id: UUID,
):
    invoice = get_fee_invoice(db, invoice_id, school_id)
    if not invoice:
        return None
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(invoice, key, value)
    invoice.balance = invoice.amount_due - invoice.amount_paid
    db.commit()
    db.refresh(invoice)
    return invoice


def delete_fee_invoice(db: Session, invoice_id: UUID, school_id: UUID):
    invoice = get_fee_invoice(db, invoice_id, school_id)
    if not invoice:
        return None
    db.delete(invoice)
    db.commit()
    return invoice
