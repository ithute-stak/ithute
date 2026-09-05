from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# =====================================================
# BASE
# =====================================================

class EmployeePayrollBase(BaseModel):

    payroll_month: str

    payroll_year: int

    basic_salary: Decimal = Field(default=0)

    allowances: Decimal = Field(default=0)

    deductions: Decimal = Field(default=0)

    gross_salary: Decimal = Field(default=0)

    net_salary: Decimal = Field(default=0)

    amount_paid: Decimal = Field(default=0)

    balance: Decimal = Field(default=0)

    status: str = "unpaid"


# =====================================================
# CREATE
# =====================================================

class EmployeePayrollCreate(
    EmployeePayrollBase
):
    employee_id: UUID


# =====================================================
# UPDATE
# =====================================================

class EmployeePayrollUpdate(BaseModel):

    amount_paid: Optional[Decimal] = None

    balance: Optional[Decimal] = None

    status: Optional[str] = None


# =====================================================
# RESPONSE
# =====================================================

class EmployeePayrollResponse(
    EmployeePayrollBase
):

    id: UUID

    employee_id: UUID

    created_at: Optional[datetime]

    updated_at: Optional[datetime]

    class Config:
        from_attributes = True