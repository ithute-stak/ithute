from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# =====================================================
# BASE
# =====================================================

class EmployeeSalaryStructureBase(BaseModel):

    basic_salary: Decimal = Field(default=0)

    housing_allowance: Decimal = Field(default=0)

    transport_allowance: Decimal = Field(default=0)

    medical_allowance: Decimal = Field(default=0)

    overtime_allowance: Decimal = Field(default=0)

    other_allowance: Decimal = Field(default=0)

    tax_percentage: Decimal = Field(default=0)

    pension_percentage: Decimal = Field(default=0)

    active: bool = True


# =====================================================
# CREATE
# =====================================================

class EmployeeSalaryStructureCreate(
    EmployeeSalaryStructureBase
):
    employee_id: UUID


# =====================================================
# UPDATE
# =====================================================

class EmployeeSalaryStructureUpdate(BaseModel):

    basic_salary: Optional[Decimal] = None

    housing_allowance: Optional[Decimal] = None

    transport_allowance: Optional[Decimal] = None

    medical_allowance: Optional[Decimal] = None

    overtime_allowance: Optional[Decimal] = None

    other_allowance: Optional[Decimal] = None

    tax_percentage: Optional[Decimal] = None

    pension_percentage: Optional[Decimal] = None

    active: Optional[bool] = None


# =====================================================
# RESPONSE
# =====================================================

class EmployeeSalaryStructureResponse(
    EmployeeSalaryStructureBase
):

    id: UUID

    employee_id: UUID

    created_at: Optional[datetime]

    updated_at: Optional[datetime]

    class Config:
        from_attributes = True