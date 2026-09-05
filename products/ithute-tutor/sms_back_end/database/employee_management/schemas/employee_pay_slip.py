from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class PayrollPayslipResponse(BaseModel):

    payroll_id: UUID

    employee_id: UUID

    employee_name: str

    payroll_month: str

    payroll_year: int

    gross_salary: Decimal

    deductions: Decimal

    net_salary: Decimal

    amount_paid: Decimal

    balance: Decimal

    status: str

    generated_at: datetime