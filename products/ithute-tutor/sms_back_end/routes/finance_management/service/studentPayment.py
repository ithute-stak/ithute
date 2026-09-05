# services/student_fee_payment.py

from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from database.finace_management.models.studentFeePayment import FeePayment
from database.finace_management.schemas.feePayment import FeePaymentCreate, FeePaymentUpdate


# =========================================
# CREATE
# =========================================

def create_student_fee_payment(
    db: Session,
    payload: FeePaymentCreate
):

    payment = FeePayment(
        student_id=payload.student_id,
        amount=payload.amount,
        payment_method=str(payload.payment_method),
        reference=str(payload.reference)
    )

    db.add(payment)

    db.commit()

    db.refresh(payment)

    return payment


# =========================================
# GET ALL
# =========================================

def get_student_fee_payments(
    db: Session
):
    return (
        db.query(FeePayment)
        .options(
            joinedload(
                FeePayment.student
            ),
            joinedload(
                FeePayment.allocations
            ),
            joinedload(
                FeePayment.credits
            ),
        )
        .all()
    )

# =========================================
# GET ONE
# =========================================

def get_student_fee_payment(
    db: Session,
    payment_id: UUID
):

    return (
        db.query(FeePayment)
        .filter(FeePayment.id == payment_id)
        .first()
    )


# =========================================
# UPDATE
# =========================================

def update_student_fee_payment(
    db: Session,
    payment_id: UUID,
    payload: FeePaymentUpdate
):

    payment = (
        db.query(FeePayment)
        .filter(FeePayment.id == payment_id)
        .first()
    )

    if not payment:
        return None

    update_data = payload.model_dump(
        exclude_unset=True
    )

    for key, value in update_data.items():
        setattr(payment, key, value)

    db.commit()

    db.refresh(payment)

    return payment


# =========================================
# DELETE
# =========================================

def delete_student_fee_payment(
    db: Session,
    payment_id: UUID
):

    payment = (
        db.query(FeePayment)
        .filter(FeePayment.id == payment_id)
        .first()
    )

    if not payment:
        return None

    db.delete(payment)

    db.commit()

    return payment