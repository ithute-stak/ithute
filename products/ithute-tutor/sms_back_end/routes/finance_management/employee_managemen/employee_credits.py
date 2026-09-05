from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database.employee_management.schemas.employee_management import EmployeeCreditResponse
from database.session import get_db

router = APIRouter(
    prefix="/employee-credits",
    tags=["Employee Credits"],
)


@router.get(
    "/employee/{employee_id}",
    response_model=list[EmployeeCreditResponse],
)
def get_employee_credits(
    employee_id: str,
    db: Session = Depends(get_db),
):
    from database.employee_management.model.employee_credit import EmployeeCredit
    return (
        db.query(EmployeeCredit)
        .filter(EmployeeCredit.employee_id == employee_id)
        .order_by(EmployeeCredit.created_at.desc())
        .all()
    )