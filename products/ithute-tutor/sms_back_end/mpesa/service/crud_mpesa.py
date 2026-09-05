# mpesa/service/mpesa_transaction_crud.py

from sqlalchemy.orm import Session

from database.finace_management.models.mpesa_transaction import MpesaTransaction


def create_pending_mpesa_transaction(
    db: Session,
    student_id: str,
    conversation_id: str,
    transaction_reference: str,
    amount: float,
    phone: str,
):
    tx = MpesaTransaction(
        student_id=student_id,
        conversation_id=conversation_id,
        transaction_reference=transaction_reference,
        amount=amount,
        phone=phone,
        status="PENDING"
    )

    db.add(tx)
    db.commit()
    db.refresh(tx)

    return tx


def get_mpesa_transaction_by_conversation_id(
    db: Session,
    conversation_id: str
):
    return (
        db.query(MpesaTransaction)
        .filter(MpesaTransaction.conversation_id == conversation_id)
        .first()
    )


def get_mpesa_transaction_by_mpesa_id(
    db: Session,
    mpesa_transaction_id: str
):
    return (
        db.query(MpesaTransaction)
        .filter(MpesaTransaction.mpesa_transaction_id == mpesa_transaction_id)
        .first()
    )


def update_mpesa_transaction_status(
    db: Session,
    tx: MpesaTransaction,
    status: str,
    mpesa_transaction_id: str | None = None
):
    tx.status = status

    if mpesa_transaction_id:
        tx.mpesa_transaction_id = mpesa_transaction_id

    db.commit()
    db.refresh(tx)

    return tx