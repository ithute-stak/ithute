from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.session import get_db
from mpesa.service.b2b_payment import MpesaB2BService
from mpesa.service.b2c_payment import MpesaB2CService
from mpesa.service.c2b_payment import MpesaC2BService
from mpesa.service.callback.student_fee_payment_callback import MpesaCallbackService

router = APIRouter(prefix="/mpesa", tags=["Mpesa Payment Service"])

class SupplierPaymentRequest(BaseModel):
    supplier_id: str
    receiver_party_code: str
    amount: float
    description: str = "Supplier payment"

class EmployeePaymentRequest(BaseModel):
    employee_id: str
    phone: str
    amount: float
    payment_reason: str = "Salary payment"

class C2BRequest(BaseModel):
    student_id: UUID
    phone: str
    amount: float
#

@router.post("/c2b")
async def pay_school_fees(
    data: C2BRequest,
    db: Session = Depends(get_db)
):

    result = await MpesaC2BService.initiate_student_fee_payment(
        db=db,
        student_id=data.student_id,
        phone=data.phone,
        amount=data.amount
    )

    mpesa_response = result["mpesa_response"]

    response_code = mpesa_response.get(
        "output_ResponseCode"
    )

    if response_code != "INS-0":
        raise HTTPException(
            status_code=400,
            detail={
                "message": mpesa_response.get(
                    "output_ResponseDesc",
                    "M-Pesa request failed"
                ),
                "mpesa_response": mpesa_response
            }
        )


    return await MpesaCallbackService.handle_student_fee_c2b_callback(db, {
        "message": "Payment request sent",
        "data": result
    })

@router.post("/employee/pay")
async def pay_employee(
    payload: EmployeePaymentRequest,
    db: Session = Depends(get_db)
):
    return await MpesaB2CService.initiate_employee_payment(
        db=db,
        employee_id=payload.employee_id,
        phone=payload.phone,
        amount=payload.amount,
        payment_reason=payload.payment_reason
    )


@router.post("/business/pay")
async def pay_supplier(
    payload: SupplierPaymentRequest,
    db: Session = Depends(get_db)
):
    return await MpesaB2BService.initiate_supplier_payment(
        db=db,
        supplier_id=payload.supplier_id,
        receiver_party_code=payload.receiver_party_code,
        amount=payload.amount,
        description=payload.description
    )

@router.post("/callback")
async def mpesa_callback(
    payload: dict,
    db: Session = Depends(get_db)
):
    return MpesaCallbackService.handle_c2b_callback(
        db=db,
        payload=payload
    )
