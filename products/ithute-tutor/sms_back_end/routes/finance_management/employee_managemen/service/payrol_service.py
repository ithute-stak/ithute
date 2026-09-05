from decimal import Decimal
from sqlalchemy.orm import Session

from database.multi_tenant_school_management.models import (
    EmployeePayroll,
    EmployeeSalaryStructure,
)


class EmployeePayrollService:

    @staticmethod
    def calculate_salary(structure: EmployeeSalaryStructure):
        basic_salary = structure.basic_salary or Decimal("0")

        allowances = (
            (structure.housing_allowance or Decimal("0")) +
            (structure.transport_allowance or Decimal("0")) +
            (structure.medical_allowance or Decimal("0")) +
            (structure.overtime_allowance or Decimal("0")) +
            (structure.other_allowance or Decimal("0"))
        )

        gross_salary = basic_salary + allowances

        tax = (
            gross_salary *
            (structure.tax_percentage or Decimal("0")) /
            Decimal("100")
        )

        pension = (
            gross_salary *
            (structure.pension_percentage or Decimal("0")) /
            Decimal("100")
        )

        deductions = tax + pension
        net_salary = gross_salary - deductions

        return {
            "basic_salary": basic_salary,
            "allowances": allowances,
            "deductions": deductions,
            "gross_salary": gross_salary,
            "net_salary": net_salary,
        }

    @staticmethod
    def generate_payroll(
        db: Session,
        employee_id,
        payroll_month: str,
        payroll_year: int,
    ):
        existing = (
            db.query(EmployeePayroll)
            .filter(
                EmployeePayroll.employee_id == employee_id,
                EmployeePayroll.payroll_month == payroll_month,
                EmployeePayroll.payroll_year == payroll_year,
            )
            .first()
        )

        if existing:
            return existing

        structure = (
            db.query(EmployeeSalaryStructure)
            .filter(
                EmployeeSalaryStructure.employee_id == employee_id,
                EmployeeSalaryStructure.active == True,
            )
            .first()
        )

        if not structure:
            raise ValueError("Employee has no active salary structure")

        salary = EmployeePayrollService.calculate_salary(structure)

        payroll = EmployeePayroll(
            employee_id=employee_id,
            payroll_month=payroll_month,
            payroll_year=payroll_year,
            basic_salary=salary["basic_salary"],
            allowances=salary["allowances"],
            deductions=salary["deductions"],
            gross_salary=salary["gross_salary"],
            net_salary=salary["net_salary"],
            amount_paid=Decimal("0"),
            balance=salary["net_salary"],
            status="unpaid",
        )

        db.add(payroll)
        db.commit()
        db.refresh(payroll)

        return payroll