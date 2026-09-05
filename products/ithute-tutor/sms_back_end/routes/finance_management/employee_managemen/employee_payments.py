from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.employee_management.schemas.emaployee_payment import EmployeePaymentResponse
from database.employee_management.schemas.employee_management import PayEmployeeRequest
from database.session import get_db
from routes.finance_management.employee_managemen.service.payment_allocation_service import EmployeePaymentService

router = APIRouter(
    prefix="/employee-payments",
    tags=["Employee Payments"],
)


@router.post("/pay")
def pay_employee(
    payload: PayEmployeeRequest,
    db: Session = Depends(get_db),
):
    return EmployeePaymentService.pay_employee(
        db=db,
        employee_id=payload.employee_id,
        amount_paid=payload.amount_paid,
        payment_method=payload.payment_method,
        reference=payload.reference,
    )


@router.get(
    "/",
    response_model=list[EmployeePaymentResponse],
)
def get_all_employee_payments(
    db: Session = Depends(get_db),
):
    return EmployeePaymentService.get_all_payments(db)


@router.get(
    "/employee/{employee_id}",
    response_model=list[EmployeePaymentResponse],
)
def get_employee_payments(
    employee_id: str,
    db: Session = Depends(get_db),
):
    return EmployeePaymentService.get_employee_payments(
        db=db,
        employee_id=employee_id,
    )


@router.get(
    "/{payment_id}",
    response_model=EmployeePaymentResponse,
)
def get_employee_payment(
    payment_id: str,
    db: Session = Depends(get_db),
):
    payment = EmployeePaymentService.get_payment(
        db=db,
        payment_id=payment_id,
    )

    if not payment:
        raise HTTPException(
            status_code=404,
            detail="Payment not found",
        )

    return payment