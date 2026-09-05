# schemas/finance/fee_payment.py

from datetime import datetime
from uuid import UUID
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import Numeric


# =========================================
# BASE
# =========================================

class CreateFeePayment(BaseModel):
    amount_paid: float
    student_id: UUID
    payment_method:str
    reference: str



class FeePaymentBase(BaseModel):
 
    amount_paid: float

    student_id: UUID

    payment_method: str

    reference: str




# =========================================
# CREATE
# =========================================

class FeePaymentCreate(
    FeePaymentBase
):
    pass


# =========================================
# UPDATE
# =========================================

class FeePaymentUpdate(BaseModel):

    amount: Optional[float] = None

    payment_method: Optional[str] = None

    reference: Optional[str] = None


# =========================================
# RESPONSE
# =========================================

class FeePaymentResponse(
    FeePaymentBase
):

    id: UUID

    paid_at: datetime

    created_at: datetime

    updated_at: datetime

    model_config = {
        "from_attributes": True
    }