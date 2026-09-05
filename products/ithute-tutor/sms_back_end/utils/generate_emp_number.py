from sqlalchemy.orm import Session
from datetime import datetime

from database.employee_management.model.employee import Employee


def generate_employee_number(
    db: Session,
    employment_date: datetime | None = None
) -> str:

    prefix = "IS-"

    # =====================================================
    # YEAR LOGIC
    # =====================================================
    year = (employment_date or datetime.now()).year

    # =====================================================
    # BASE PATTERN
    # IS-202600001
    # =====================================================
    year_prefix = f"{prefix}{year}"

    # =====================================================
    # GET LAST EMPLOYEE FOR THIS YEAR
    # =====================================================
    last_employee = (
        db.query(Employee)
        .filter(
            Employee.employee_number.like(f"{year_prefix}%")
        )
        .order_by(Employee.employee_number.desc())
        .first()
    )

    # =====================================================
    # DETERMINE NEXT NUMBER
    # =====================================================
    if not last_employee or not last_employee.employee_number:
        next_seq = 1
    else:
        try:
            last_seq = int(
                last_employee.employee_number.replace(year_prefix, "")
            )
            next_seq = last_seq + 1
        except:
            next_seq = 1

    # =====================================================
    # FORMAT FINAL NUMBER
    # =====================================================
    employee_number = f"{year_prefix}{str(next_seq).zfill(5)}"

    # =====================================================
    # SAFETY CHECK (UNIQUE GUARANTEE)
    # =====================================================
    exists = (
        db.query(Employee)
        .filter(Employee.employee_number == employee_number)
        .first()
    )

    while exists:
        next_seq += 1
        employee_number = f"{year_prefix}{str(next_seq).zfill(5)}"

        exists = (
            db.query(Employee)
            .filter(Employee.employee_number == employee_number)
            .first()
        )

    return employee_number