from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class GeneratePayrollRequest(BaseModel):
    employee_id: UUID
    payroll_month: str
    payroll_year: int


class PayEmployeeRequest(BaseModel):
    employee_id: UUID
    amount_paid: Decimal
    payment_method: str = "cash"
    reference: Optional[str] = None


class EmployeePayrollResponse(BaseModel):
    id: UUID
    employee_id: UUID
    payroll_month: str
    payroll_year: int
    basic_salary: Decimal
    allowances: Decimal
    deductions: Decimal
    gross_salary: Decimal
    net_salary: Decimal
    amount_paid: Decimal
    balance: Decimal
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EmployeePaymentAllocationResponse(BaseModel):
    id: UUID
    payment_id: UUID
    payroll_id: UUID
    amount_allocated: Decimal
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EmployeeCreditResponse(BaseModel):
    id: UUID
    employee_id: UUID
    amount: Decimal
    source_payment_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EmployeePaymentResponse(BaseModel):
    id: UUID
    employee_id: UUID
    amount_paid: Decimal
    payment_method: str
    reference: Optional[str] = None
    payment_number: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    allocations: List[EmployeePaymentAllocationResponse] = []

    model_config = ConfigDict(from_attributes=True)