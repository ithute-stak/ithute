from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.workforce import audit, can_see_sensitive, commit, employee_dict, row_dict, utcnow
from app.db.session import get_db
from app.models import (
    AttendanceRecord,
    Branch,
    CompanySetting,
    CostCentre,
    Department,
    Employee,
    EmployeePayComponent,
    EmploymentContract,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
    PayComponent,
    PayrollLine,
    PayrollPeriod,
    PayrollRun,
    Shift,
    Site,
    User,
)
from app.security.access import Principal, current_principal

router = APIRouter(prefix="/workforce", tags=["Phase 3 - Workforce & Payroll"])


def company_wide(principal: Principal, permission: str) -> bool:
    return principal.has_company_permission(permission)


def safe_employee(principal: Principal, employee: Employee) -> dict:
    result = employee_dict(principal, employee)
    if not can_see_sensitive(principal, employee):
        result["basic_rate"] = None
    return result


@router.get("/summary")
def safe_summary(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict:
    if not principal.has_permission_anywhere("people.view"):
        raise HTTPException(status_code=403, detail="Permission required: people.view")
    employees = [row for row in db.scalars(select(Employee).where(Employee.company_id == principal.user.company_id)).all() if principal.can("people.view", branch_id=row.branch_id, site_id=row.site_id)]
    employee_ids = {row.id for row in employees}
    from datetime import date
    today = date.today()
    leave_pending = [row for row in db.scalars(select(LeaveRequest).where(LeaveRequest.company_id == principal.user.company_id, LeaveRequest.status == "pending")).all() if row.employee_id in employee_ids]
    attendance_today = [row for row in db.scalars(select(AttendanceRecord).where(AttendanceRecord.company_id == principal.user.company_id, AttendanceRecord.work_date == today)).all() if row.employee_id in employee_ids]
    payroll_runs = []
    if principal.has_permission_anywhere("payroll.view"):
        payroll_runs = [row for row in db.scalars(select(PayrollRun).where(PayrollRun.company_id == principal.user.company_id).order_by(PayrollRun.id.desc()).limit(50)).all() if principal.can("payroll.view", branch_id=row.branch_id)][:10]
    return {
        "counts": {
            "employees": len(employees),
            "active_employees": sum(1 for row in employees if row.employment_status == "active"),
            "pending_leave": len(leave_pending),
            "attendance_today": len(attendance_today),
            "payroll_runs": len(payroll_runs),
        },
        "latest_payroll_runs": [row_dict(row) for row in payroll_runs],
    }


@router.get("/catalog")
def safe_catalog(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict:
    company_id = principal.user.company_id
    branches = [row for row in db.scalars(select(Branch).where(Branch.company_id == company_id, Branch.is_active.is_(True))).all() if principal.can("people.view", branch_id=row.id)]
    branch_ids = {row.id for row in branches}
    sites = [row for row in db.scalars(select(Site).where(Site.company_id == company_id, Site.is_active.is_(True))).all() if row.branch_id in branch_ids and principal.can("people.view", branch_id=row.branch_id, site_id=row.id)]
    site_ids = {row.id for row in sites}
    departments = []
    for row in db.scalars(select(Department).where(Department.company_id == company_id, Department.is_active.is_(True))).all():
        if row.branch_id is None and company_wide(principal, "people.view"):
            departments.append(row)
        elif row.branch_id in branch_ids:
            departments.append(row)
    cost_centres = []
    for row in db.scalars(select(CostCentre).where(CostCentre.company_id == company_id, CostCentre.is_active.is_(True))).all():
        if row.branch_id is None and company_wide(principal, "people.view"):
            cost_centres.append(row)
        elif row.branch_id in branch_ids and (row.site_id is None or row.site_id in site_ids or principal.can("people.view", branch_id=row.branch_id)):
            cost_centres.append(row)

    users = []
    if principal.has_company_permission("users.view"):
        for row in db.scalars(select(User).where(User.company_id == company_id, User.is_active.is_(True))).all():
            users.append({"id": row.id, "username": row.username, "email": row.email, "full_name": row.full_name, "job_title": row.job_title, "status": row.status})

    return {
        "branches": [row_dict(row) for row in branches],
        "sites": [row_dict(row) for row in sites],
        "departments": [row_dict(row) for row in departments],
        "cost_centres": [row_dict(row) for row in cost_centres],
        "users": users,
        "leave_types": [row_dict(row) for row in db.scalars(select(LeaveType).where(LeaveType.company_id == company_id)).all()],
        "shifts": [row_dict(row) for row in db.scalars(select(Shift).where(Shift.company_id == company_id)).all()],
        "pay_components": [row_dict(row) for row in db.scalars(select(PayComponent).where(PayComponent.company_id == company_id)).all()] if principal.has_permission_anywhere("payroll.view") else [],
        "permissions": sorted(principal.permission_codes),
    }


@router.get("/employees")
def safe_list_employees(branch_id: int | None = None, status_filter: str | None = Query(default=None, alias="status"), db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict]:
    statement = select(Employee).where(Employee.company_id == principal.user.company_id)
    if branch_id is not None:
        statement = statement.where(Employee.branch_id == branch_id)
    if status_filter:
        statement = statement.where(Employee.employment_status == status_filter)
    rows = db.scalars(statement.order_by(Employee.employee_number)).all()
    return [safe_employee(principal, row) for row in rows if principal.can("people.view", branch_id=row.branch_id, site_id=row.site_id)]


@router.get("/employees/{employee_id}")
def safe_get_employee(employee_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict:
    employee = db.get(Employee, employee_id)
    if not employee or employee.company_id != principal.user.company_id or not principal.can("people.view", branch_id=employee.branch_id, site_id=employee.site_id):
        raise HTTPException(status_code=404, detail="Employee not found")
    sensitive = can_see_sensitive(principal, employee)
    contracts = []
    for row in db.scalars(select(EmploymentContract).where(EmploymentContract.employee_id == employee.id).order_by(EmploymentContract.start_date.desc())).all():
        item = row_dict(row)
        if not sensitive:
            item["basic_rate"] = None
        contracts.append(item)
    balances = [row_dict(row) for row in db.scalars(select(LeaveBalance).where(LeaveBalance.employee_id == employee.id).order_by(LeaveBalance.year.desc())).all()]
    pay_components = [row_dict(row) for row in db.scalars(select(EmployeePayComponent).where(EmployeePayComponent.employee_id == employee.id)).all()] if principal.can("payroll.view", branch_id=employee.branch_id, site_id=employee.site_id) else []
    return {**safe_employee(principal, employee), "contracts": contracts, "leave_balances": balances, "pay_components": pay_components}


@router.post("/payroll-runs/{run_id}/approve")
def safe_approve_payroll(run_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict:
    run = db.get(PayrollRun, run_id)
    if not run or run.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Payroll run not found")
    if not principal.can("payroll.approve", branch_id=run.branch_id):
        raise HTTPException(status_code=403, detail="payroll.approve is required in this payroll scope")
    if run.status != "reviewed":
        raise HTTPException(status_code=409, detail="Payroll must be reviewed before approval")
    setting = db.scalar(select(CompanySetting).where(CompanySetting.company_id == principal.user.company_id, CompanySetting.key == "workforce_policy"))
    policy = setting.value if setting and isinstance(setting.value, dict) else {}
    if policy.get("require_bank_details_before_approval"):
        missing = []
        for line in db.scalars(select(PayrollLine).where(PayrollLine.run_id == run.id)).all():
            employee = db.get(Employee, line.employee_id)
            if employee and not employee.bank_account_number:
                missing.append(employee.employee_number)
        if missing:
            raise HTTPException(status_code=422, detail=f"Bank details are missing for: {', '.join(missing[:20])}")
    run.status = "approved"
    run.approved_by = principal.user.full_name
    run.approved_at = utcnow()
    period = db.get(PayrollPeriod, run.period_id)
    # Branch approvals must not prevent another branch from preparing the same pay period.
    # A consolidated company run closes the period automatically; branch periods can be
    # closed explicitly after all required runs are approved.
    if period and run.branch_id is None:
        period.status = "closed"
    audit(db, principal, "payroll.run.approve", "payroll_run", run.id, branch_id=run.branch_id, detail={"net": str(run.total_net)})
    commit(db)
    return row_dict(run)


@router.post("/payroll-periods/{period_id}/close")
def close_payroll_period(period_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict:
    if not principal.has_company_permission("payroll.approve"):
        raise HTTPException(status_code=403, detail="Company-level payroll.approve is required to close a payroll period")
    period = db.get(PayrollPeriod, period_id)
    if not period or period.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Payroll period not found")
    runs = db.scalars(select(PayrollRun).where(PayrollRun.company_id == principal.user.company_id, PayrollRun.period_id == period.id)).all()
    if not runs:
        raise HTTPException(status_code=422, detail="A payroll period cannot close before at least one payroll run exists")
    pending = [row.id for row in runs if row.status != "approved"]
    if pending:
        raise HTTPException(status_code=409, detail=f"Payroll runs must be approved before period close: {pending[:20]}")
    period.status = "closed"
    audit(db, principal, "payroll.period.close", "payroll_period", period.id, detail={"runs": len(runs)})
    commit(db)
    return row_dict(period)
