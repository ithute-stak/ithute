from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# =====================================================
# BASE
# =====================================================

class EmployeeCreditBase(BaseModel):

    amount: Decimal = Field(default=0)


# =====================================================
# CREATE
# =====================================================

class EmployeeCreditCreate(
    EmployeeCreditBase
):

    employee_id: UUID

    source_payment_id: Optional[UUID] = None


# =====================================================
# RESPONSE
# =====================================================

class EmployeeCreditResponse(
    EmployeeCreditBase
):

    id: UUID

    employee_id: UUID

    source_payment_id: Optional[UUID]

    created_at: Optional[datetime]

    class Config:
        from_attributes = True