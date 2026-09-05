# schemas/finance/fee_plan.py

from datetime import datetime
from uuid import UUID
from typing import Optional

from pydantic import BaseModel


# =========================================
# BASE
# =========================================

class FeePlanBase(BaseModel):

    feeConfig_id: UUID

    grade_id: UUID

    name: str

    third_quarter: float
    first_quarter: float
    second_quarter: float
    fourth_quarter: float

    description: Optional[str] = None


# =========================================
# CREATE
# =========================================

class FeePlanCreate(
    FeePlanBase
):
    pass


# =========================================
# UPDATE
# =========================================

class FeePlanUpdate(BaseModel):

    grade_id: Optional[UUID] = None

    name: Optional[str] = None

    third_quarter: Optional[float] = None
    first_quarter: Optional[float] = None
    second_quarter: Optional[float] = None
    forth_quarter: Optional[float] = None

    description: Optional[str] = None


# =========================================
# RESPONSE
# =========================================

class FeePlanResponse(
    FeePlanBase
):

    id: UUID

    created_at: datetime

    updated_at: datetime

    model_config = {
        "from_attributes": True
    }