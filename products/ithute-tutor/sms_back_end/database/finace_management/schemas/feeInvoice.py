# schemas/finance/fee_invoice.py

from datetime import date, datetime
from uuid import UUID
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import Numeric


# =========================================
# BASE
# =========================================

class FeeInvoiceBase(BaseModel):

    student_id: UUID

    school_id: UUID

    fee_plan_id: UUID

    period_start: date

    period_end: date

    amount_due: float
    amount_paid: float
    balance: float

    description: Optional[str] = None

    status: str = "unpaid"


# =========================================
# CREATE
# =========================================

class FeeInvoiceCreate(
    FeeInvoiceBase
):
    pass


# =========================================
# UPDATE
# =========================================

class FeeInvoiceUpdate(BaseModel):

    period_start: Optional[date] = None

    period_end: Optional[date] = None

    amount_due: Optional[float] = None

    amount_paid: Optional[float] = None

    balance: Optional[float] = None

    status: Optional[str] = None


# =========================================
# RESPONSE
# =========================================

class FeeInvoiceResponse(
    FeeInvoiceBase
):

    id: UUID
    invoice_number: str

    created_at: datetime

    updated_at: datetime

    model_config = {
        "from_attributes": True
    }