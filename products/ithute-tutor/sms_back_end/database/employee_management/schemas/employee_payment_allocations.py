from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


# =====================================================
# BASE
# =====================================================

class EmployeePaymentAllocationBase(BaseModel):

    amount_allocated: Decimal


# =====================================================
# CREATE
# =====================================================

class EmployeePaymentAllocationCreate(
    EmployeePaymentAllocationBase
):

    payment_id: UUID

    payroll_id: UUID


# =====================================================
# RESPONSE
# =====================================================

class EmployeePaymentAllocationResponse(
    EmployeePaymentAllocationBase
):

    id: UUID

    payment_id: UUID

    payroll_id: UUID

    created_at: Optional[datetime]

    class Config:
        from_attributes = True