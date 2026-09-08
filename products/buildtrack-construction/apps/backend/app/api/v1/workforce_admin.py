from __future__ import annotations

import csv
import io
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.workforce import audit, can_see_sensitive, commit, row_dict, utcnow
from app.db.session import get_db
from app.models import (
    Employee,
    EmployeeShiftAssignment,
    EmploymentContract,
    PayrollPeriod,
    PayrollRun,
    Shift,
    User,
)
from app.security.access import Principal, current_principal, revoke_user_sessions

router = APIRouter(prefix="/workforce", tags=["Phase 3 - Workforce Administration"])


class EmployeeLinkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: int | None = None


class EmployeeLifecycleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employment_status: Literal["active", "on_leave", "suspended", "terminated", "inactive"]
    termination_date: date | None = None
    reason: str | None = Field(default=None, max_length=1000)
    revoke_linked_user_access: bool = False


class ContractActivationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employee_signed: bool
    company_signed: bool


def employee_in_scope(db: Session, principal: Principal, employee_id: int, permission: str) -> Employee:
    employee = db.get(Employee, employee_id)
    if not employee or employee.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Employee not found")
    if not principal.can(permission, branch_id=employee.branch_id, site_id=employee.site_id):
        raise HTTPException(status_code=403, detail=f"Permission required in employee scope: {permission}")
    return employee


@router.post("/employees/{employee_id}/link-user")
def link_employee_user(
    employee_id: int,
    payload: EmployeeLinkInput,
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    employee = employee_in_scope(db, principal, employee_id, "people.manage")
    previous_user_id = employee.user_id
    if payload.user_id is not None:
        if not principal.has_company_permission("users.view"):
            raise HTTPException(status_code=403, detail="Company-level users.view is required to link an employee to a system user")
        user = db.get(User, payload.user_id)
        if not user or user.company_id != principal.user.company_id:
            raise HTTPException(status_code=422, detail="Selected user does not belong to the active company")
        existing = db.scalar(
            select(Employee).where(
                Employee.company_id == principal.user.company_id,
                Employee.user_id == user.id,
                Employee.id != employee.id,
            )
        )
        if existing:
            raise HTTPException(status_code=409, detail="Selected user is already linked to another employee")
        employee.user_id = user.id
    else:
        employee.user_id = None
    audit(
        db,
        principal,
        "employee.user_link",
        "employee",
        employee.id,
        employee_id=employee.id,
        branch_id=employee.branch_id,
        detail={"previous_user_id": previous_user_id, "user_id": employee.user_id},
    )
    commit(db)
    return {"employee_id": employee.id, "user_id": employee.user_id}


@router.post("/employees/{employee_id}/lifecycle")
def change_employee_lifecycle(
    employee_id: int,
    payload: EmployeeLifecycleInput,
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    employee = employee_in_scope(db, principal, employee_id, "people.manage")
    if payload.employment_status == "terminated" and payload.termination_date is None:
        raise HTTPException(status_code=422, detail="Termination date is required for a terminated employee")
    if payload.termination_date and payload.termination_date < employee.hire_date:
        raise HTTPException(status_code=422, detail="Termination date cannot be before hire date")

    previous_status = employee.employment_status
    employee.employment_status = payload.employment_status
    employee.termination_date = payload.termination_date if payload.employment_status == "terminated" else None

    revoked_sessions = 0
    if payload.revoke_linked_user_access and employee.user_id is not None:
        if not principal.has_company_permission("sessions.manage"):
            raise HTTPException(status_code=403, detail="Company-level sessions.manage is required to revoke linked user sessions")
        user = db.get(User, employee.user_id)
        if user and user.company_id == principal.user.company_id:
            revoked_sessions = revoke_user_sessions(
                db,
                user.id,
                actor=principal.user.full_name,
                reason=f"Employee lifecycle changed to {payload.employment_status}",
            )

    audit(
        db,
        principal,
        "employee.lifecycle",
        "employee",
        employee.id,
        employee_id=employee.id,
        branch_id=employee.branch_id,
        detail={
            "previous_status": previous_status,
            "employment_status": employee.employment_status,
            "termination_date": employee.termination_date.isoformat() if employee.termination_date else None,
            "reason": payload.reason,
            "revoked_sessions": revoked_sessions,
            "account_status_unchanged": True,
        },
    )
    commit(db)
    return {
        "employee": {
            "id": employee.id,
            "employee_number": employee.employee_number,
            "employment_status": employee.employment_status,
            "termination_date": employee.termination_date.isoformat() if employee.termination_date else None,
            "user_id": employee.user_id,
        },
        "revoked_sessions": revoked_sessions,
        "account_status_unchanged": True,
    }


@router.get("/shift-assignments")
def list_shift_assignments(
    employee_id: int | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> list[dict[str, Any]]:
    statement = select(EmployeeShiftAssignment)
    if employee_id is not None:
        statement = statement.where(EmployeeShiftAssignment.employee_id == employee_id)
    result: list[dict[str, Any]] = []
    for assignment in db.scalars(statement.order_by(EmployeeShiftAssignment.effective_from.desc())).all():
        employee = db.get(Employee, assignment.employee_id)
        if not employee or employee.company_id != principal.user.company_id:
            continue
        if not principal.can("attendance.view", branch_id=employee.branch_id, site_id=employee.site_id):
            continue
        shift = db.get(Shift, assignment.shift_id)
        item = row_dict(assignment)
        item["employee_number"] = employee.employee_number
        item["employee_name"] = f"{employee.first_name} {employee.last_name}"
        item["shift_code"] = shift.code if shift else ""
        item["shift_name"] = shift.name if shift else ""
        result.append(item)
    return result


@router.post("/contracts/{contract_id}/activate-signed")
def activate_signed_contract(
    contract_id: int,
    payload: ContractActivationInput,
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    contract = db.get(EmploymentContract, contract_id)
    if not contract or contract.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Contract not found")
    employee = employee_in_scope(db, principal, contract.employee_id, "people.approve")
    if not principal.can("people.approve", branch_id=contract.branch_id, site_id=contract.site_id):
        raise HTTPException(status_code=403, detail="people.approve is required in the contract target branch/site")
    if contract.status != "draft":
        raise HTTPException(status_code=409, detail="Only a draft contract can be activated")
    if not payload.employee_signed or not payload.company_signed:
        raise HTTPException(status_code=422, detail="Employee and company signature confirmations are both required")

    now = utcnow()
    contract.signed_employee_at = contract.signed_employee_at or now
    contract.signed_company_at = contract.signed_company_at or now
    contract.status = "active"
    employee.job_title = contract.job_title
    employee.branch_id = contract.branch_id
    employee.site_id = contract.site_id
    employee.department_id = contract.department_id
    employee.cost_centre_id = contract.cost_centre_id
    employee.pay_basis = contract.pay_basis
    employee.basic_rate = contract.basic_rate
    employee.standard_hours_per_week = contract.hours_per_week

    audit(
        db,
        principal,
        "contract.activate_signed",
        "employment_contract",
        contract.id,
        employee_id=employee.id,
        branch_id=contract.branch_id,
        detail={"employee_signed": True, "company_signed": True},
    )
    commit(db)
    return row_dict(contract)


@router.get("/employees/export.csv")
def export_employees(
    branch_id: int | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> StreamingResponse:
    if not principal.has_permission_anywhere("people.export"):
        raise HTTPException(status_code=403, detail="Permission required: people.export")
    statement = select(Employee).where(Employee.company_id == principal.user.company_id)
    if branch_id is not None:
        statement = statement.where(Employee.branch_id == branch_id)
    if status_filter:
        statement = statement.where(Employee.employment_status == status_filter)
    employees = [
        row
        for row in db.scalars(statement.order_by(Employee.employee_number)).all()
        if principal.can("people.export", branch_id=row.branch_id, site_id=row.site_id)
    ]

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "Employee Number", "First Name", "Last Name", "Job Title", "Employment Type",
        "Employment Status", "Hire Date", "Termination Date", "Branch ID", "Site ID",
        "Department ID", "Cost Centre ID", "Phone", "Work Email", "Pay Basis", "Basic Rate",
    ])
    for employee in employees:
        show_pay = can_see_sensitive(principal, employee)
        writer.writerow([
            employee.employee_number,
            employee.first_name,
            employee.last_name,
            employee.job_title,
            employee.employment_type,
            employee.employment_status,
            employee.hire_date,
            employee.termination_date or "",
            employee.branch_id,
            employee.site_id or "",
            employee.department_id or "",
            employee.cost_centre_id or "",
            employee.phone or "",
            employee.work_email or "",
            employee.pay_basis if show_pay else "",
            employee.basic_rate if show_pay else "",
        ])
    content = buffer.getvalue().encode("utf-8-sig")
    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="buildtrack-employees.csv"'},
    )


@router.post("/payroll-periods/{period_id}/close-reviewed")
def close_reviewed_payroll_period(
    period_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    if not principal.has_company_permission("payroll.approve"):
        raise HTTPException(status_code=403, detail="Company-level payroll.approve is required to close a payroll period")
    period = db.get(PayrollPeriod, period_id)
    if not period or period.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Payroll period not found")
    runs = db.scalars(
        select(PayrollRun).where(
            PayrollRun.company_id == principal.user.company_id,
            PayrollRun.period_id == period.id,
        )
    ).all()
    if not runs:
        raise HTTPException(status_code=422, detail="At least one payroll run is required before period close")
    incomplete = [run.id for run in runs if run.status != "approved"]
    if incomplete:
        raise HTTPException(status_code=409, detail=f"All payroll runs must be approved before period close: {incomplete[:20]}")
    period.status = "closed"
    audit(db, principal, "payroll.period.close", "payroll_period", period.id, detail={"runs": len(runs)})
    commit(db)
    return row_dict(period)
