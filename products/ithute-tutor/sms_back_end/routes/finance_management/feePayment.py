from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from database.finace_management.models.studentFeePayment import FeePayment
from database.finace_management.schemas.feePayment import (
    CreateFeePayment,
    FeePaymentCreate,
    FeePaymentResponse,
    FeePaymentUpdate,
)
from database.multi_tenant_school_management.models import StudentEnrollment
from database.session import get_db
from routes.finance_management.service.create_fee_payment import create_student_payment_nit
from routes.finance_management.service.studentPayment import (
    create_student_fee_payment,
    delete_student_fee_payment,
    update_student_fee_payment,
)
from utils.school_context import SchoolContext, get_school_context, require_school_roles

router = APIRouter(prefix="/student-fee-payments", tags=["Student Fee Payments"])


def _school_payment_query(db: Session, school_id: UUID):
    # New payments have immutable school ownership. The enrollment branch is
    # only a temporary compatibility path for legacy rows not yet backfilled.
    return (
        db.query(FeePayment)
        .outerjoin(StudentEnrollment, StudentEnrollment.student_id == FeePayment.student_id)
        .filter(
            or_(
                FeePayment.school_id == school_id,
                and_(
                    FeePayment.school_id.is_(None),
                    StudentEnrollment.school_id == school_id,
                    StudentEnrollment.is_current.is_(True),
                ),
            )
        )
        .distinct()
    )


def _student_is_enrolled(db: Session, student_id: UUID, school_id: UUID) -> bool:
    return (
        db.query(StudentEnrollment)
        .filter(
            StudentEnrollment.student_id == student_id,
            StudentEnrollment.school_id == school_id,
            StudentEnrollment.is_current.is_(True),
        )
        .first()
        is not None
    )


def _stamp_payment_school(db: Session, payment_id: UUID, school_id: UUID) -> FeePayment:
    payment = db.get(FeePayment, payment_id)
    if payment is None:
        raise HTTPException(status_code=500, detail="Payment was created but could not be reloaded")
    if payment.school_id is not None and payment.school_id != school_id:
        raise HTTPException(status_code=409, detail="Payment already belongs to another school")
    payment.school_id = school_id
    db.commit()
    db.refresh(payment)
    return payment


@router.post("/create-student-fee-payment")
async def create_student_fee_payment_(
    payload: CreateFeePayment,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles("school_admin", "bursar", "accountant", "cashier")),
):
    if not _student_is_enrolled(db, payload.student_id, context.school_id):
        raise HTTPException(status_code=404, detail="Student is not enrolled in this school")

    result = await create_student_payment_nit(db=db, payLoad=payload)
    payment_data = result.get("payment", {}) if isinstance(result, dict) else {}
    raw_payment_id = payment_data.get("payment_id")
    if raw_payment_id:
        _stamp_payment_school(db, UUID(str(raw_payment_id)), context.school_id)
    return result


@router.post("/", response_model=FeePaymentResponse)
def create_payment(
    payload: FeePaymentCreate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles("school_admin", "bursar", "accountant", "cashier")),
):
    if not _student_is_enrolled(db, payload.student_id, context.school_id):
        raise HTTPException(status_code=404, detail="Student is not enrolled in this school")
    payment = create_student_fee_payment(db, payload)
    return _stamp_payment_school(db, payment.id, context.school_id)


@router.get("/")
def get_all_payments(
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    return _school_payment_query(db, context.school_id).all()


@router.get("/{payment_id}", response_model=FeePaymentResponse)
def get_single_payment(
    payment_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    payment = _school_payment_query(db, context.school_id).filter(FeePayment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found in this school")
    return payment


@router.put("/{payment_id}", response_model=FeePaymentResponse)
def update_payment(
    payment_id: UUID,
    payload: FeePaymentUpdate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles("school_admin", "bursar", "accountant")),
):
    if _school_payment_query(db, context.school_id).filter(FeePayment.id == payment_id).first() is None:
        raise HTTPException(status_code=404, detail="Payment not found in this school")
    payment = update_student_fee_payment(db, payment_id, payload)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.school_id is None:
        payment.school_id = context.school_id
        db.commit()
        db.refresh(payment)
    return payment


@router.delete("/{payment_id}")
def delete_payment(
    payment_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles("school_admin", "bursar")),
):
    if _school_payment_query(db, context.school_id).filter(FeePayment.id == payment_id).first() is None:
        raise HTTPException(status_code=404, detail="Payment not found in this school")
    payment = delete_student_fee_payment(db, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return {"message": "Payment deleted successfully"}
