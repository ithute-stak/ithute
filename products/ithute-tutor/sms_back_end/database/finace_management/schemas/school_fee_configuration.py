# schemas/finance/school_fee_configuration.py

from datetime import date, datetime
from uuid import UUID
from typing import Optional

from pydantic import BaseModel

from database.finace_management.enum.paymentModules import (
    FeeStructureType
)


# =========================================
# BASE
# =========================================

class SchoolFeeConfigurationBase(BaseModel):

    school_id: UUID

    year_start: date

    year_end: date

    fee_structure: FeeStructureType

    allow_partial_payments: bool = True

    allow_late_payments: bool = True


# =========================================
# CREATE
# =========================================

class SchoolFeeConfigurationCreate(
    SchoolFeeConfigurationBase
):
    pass


# =========================================
# UPDATE
# =========================================

class SchoolFeeConfigurationUpdate(BaseModel):

    year_start: Optional[date] = None

    year_end: Optional[date] = None

    fee_structure: Optional[
        FeeStructureType
    ] = None

    allow_partial_payments: Optional[
        bool
    ] = None

    allow_late_payments: Optional[
        bool
    ] = None


# =========================================
# RESPONSE
# =========================================

class SchoolFeeConfigurationResponse(
    SchoolFeeConfigurationBase
):

    id: UUID

    created_at: datetime

    updated_at: datetime

    model_config = {
        "from_attributes": True
    }