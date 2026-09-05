from decimal import Decimal
from typing import List
from uuid import UUID

from pydantic import BaseModel


class EmployeeStatementItem(BaseModel):

    payroll_month: str

    payroll_year: int

    gross_salary: Decimal

    net_salary: Decimal

    amount_paid: Decimal

    balance: Decimal

    status: str


class EmployeeStatementResponse(BaseModel):

    employee_id: UUID

    employee_name: str

    total_payrolls: int

    total_paid: Decimal

    total_balance: Decimal

    payrolls: List[EmployeeStatementItem]