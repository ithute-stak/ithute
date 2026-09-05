from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.employee_management.model.empliyee_payrol import EmployeePayroll
from database.employee_management.model.employee import Employee
from database.employee_management.schemas.employee_payroll_schema import EmployeePayrollResponse
from database.employee_management.schemas.generate_payroll import GeneratePayrollRequest
from database.session import get_db
from utils.school_context import SchoolContext, get_school_context, require_school_roles

router = APIRouter(prefix="/employee-payrolls", tags=["Employee Payrolls"])


def _school_payroll_query(db: Session, school_id: UUID):
    return (
        db.query(EmployeePayroll)
        .join(Employee, Employee.id == EmployeePayroll.employee_id)
        .filter(Employee.school_id == school_id)
    )


@router.post("/generate", response_model=EmployeePayrollResponse)
def generate_employee_payroll(
    payload: GeneratePayrollRequest,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(
        require_school_roles("school_admin", "principal", "hr_manager", "payroll_officer", "accountant")
    ),
):
    employee = (
        db.query(Employee)
        .filter(Employee.id == payload.employee_id, Employee.school_id == context.school_id)
        .first()
    )
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found in this school")

    try:
        from routes.finance_management.employee_managemen.service.payrol_service import EmployeePayrollService
        return EmployeePayrollService.generate_payroll(
            db=db,
            employee_id=payload.employee_id,
            payroll_month=payload.payroll_month,
            payroll_year=payload.payroll_year,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/", response_model=list[EmployeePayrollResponse])
def get_all_payrolls(
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    return (
        _school_payroll_query(db, context.school_id)
        .order_by(EmployeePayroll.payroll_year.desc(), EmployeePayroll.created_at.desc())
        .all()
    )


@router.get("/employee/{employee_id}", response_model=list[EmployeePayrollResponse])
def get_employee_payrolls(
    employee_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    employee = (
        db.query(Employee)
        .filter(Employee.id == employee_id, Employee.school_id == context.school_id)
        .first()
    )
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found in this school")

    return (
        _school_payroll_query(db, context.school_id)
        .filter(EmployeePayroll.employee_id == employee_id)
        .order_by(EmployeePayroll.payroll_year.desc(), EmployeePayroll.created_at.desc())
        .all()
    )
