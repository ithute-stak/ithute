from uuid import UUID

from pydantic import BaseModel


class GeneratePayrollRequest(BaseModel):

    employee_id: UUID

    payroll_month: str

    payroll_year: int