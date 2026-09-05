from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


# =====================================================
# BASE
# =====================================================

class EmployeePaymentBase(BaseModel):

    amount_paid: Decimal

    payment_method: str = "cash"

    reference: Optional[str] = None


# =====================================================
# CREATE
# =====================================================

class EmployeePaymentCreate(
    EmployeePaymentBase
):
    employee_id: UUID


# =====================================================
# RESPONSE
# =====================================================

class EmployeePaymentResponse(
    EmployeePaymentBase
):

    id: UUID

    employee_id: UUID

    payment_number: Optional[str]

    created_at: Optional[datetime]

    class Config:
        from_attributes = True


# =====================================================
# PROCESS PAYMENT REQUEST
# =====================================================

class ProcessEmployeePaymentRequest(BaseModel):

    employee_id: UUID

    amount_paid: Decimal

    payment_method: Optional[str] = "cash"

    reference: Optional[str] = "manual"