from __future__ import annotations

import csv
import io
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import (
    AttendanceRecord,
    Branch,
    CompanySetting,
    CostCentre,
    Department,
    Employee,
    EmployeePayComponent,
    EmployeeShiftAssignment,
    EmploymentContract,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
    NumberSequence,
    PayComponent,
    PayrollLine,
    PayrollPeriod,
    PayrollRun,
    Permission,
    Role,
    RolePermission,
    Shift,
    Site,
    TimesheetEntry,
    User,
    WorkforceAuditEvent,
)
from app.security.access import Principal, current_principal

router = APIRouter(prefix="/workforce", tags=["Phase 3 - Workforce & Payroll"])
MONEY = Decimal("0.01")

PHASE3_PERMISSIONS: dict[str, tuple[str, str, str]] = {
    "people.export": ("people", "export", "Export employee records"),
    "people.sensitive": ("people", "sensitive", "View identity and banking-sensitive employee fields"),
    "leave.view": ("leave", "view", "View leave records and balances"),
    "leave.manage": ("leave", "manage", "Create and maintain leave records"),
    "leave.approve": ("leave", "approve", "Approve or reject leave"),
    "attendance.view": ("attendance", "view", "View attendance"),
    "attendance.manage": ("attendance", "manage", "Capture and correct attendance"),
    "attendance.approve": ("attendance", "approve", "Approve attendance controls"),
    "timesheets.view": ("timesheets", "view", "View timesheets"),
    "timesheets.manage": ("timesheets", "manage", "Capture and submit timesheets"),
    "timesheets.approve": ("timesheets", "approve", "Approve timesheets"),
    "payroll.view": ("payroll", "view", "View payroll preparation data"),
    "payroll.manage": ("payroll", "manage", "Prepare and recalculate payroll"),
    "payroll.approve": ("payroll", "approve", "Review and approve payroll"),
    "payroll.export": ("payroll", "export", "Export approved payroll preparation data"),
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def row_dict(row: Any) -> dict[str, Any]:
    return {column.name: json_value(getattr(row, column.name)) for column in row.__table__.columns}


def money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def commit(db: Session, detail: str = "The workforce record conflicts with existing data") -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=detail) from error


def require_company(principal: Principal, permission: str) -> None:
    if not principal.has_company_permission(permission):
        raise HTTPException(status_code=403, detail=f"Company-level permission required: {permission}")


def require_scope(principal: Principal, permission: str, branch_id: int | None, site_id: int | None = None) -> None:
    if not principal.can(permission, branch_id=branch_id, site_id=site_id):
        raise HTTPException(status_code=403, detail=f"Permission required in this branch/site: {permission}")


def ensure_org_scope(db: Session, principal: Principal, branch_id: int, site_id: int | None = None, department_id: int | None = None, cost_centre_id: int | None = None) -> None:
    branch = db.get(Branch, branch_id)
    if not branch or branch.company_id != principal.user.company_id:
        raise HTTPException(status_code=422, detail="Branch does not belong to the active company")
    if site_id is not None:
        site = db.get(Site, site_id)
        if not site or site.company_id != principal.user.company_id or site.branch_id != branch_id:
            raise HTTPException(status_code=422, detail="Site does not belong to the selected branch")
    if department_id is not None:
        department = db.get(Department, department_id)
        if not department or department.company_id != principal.user.company_id or (department.branch_id is not None and department.branch_id != branch_id):
            raise HTTPException(status_code=422, detail="Department is outside the selected branch scope")
    if cost_centre_id is not None:
        centre = db.get(CostCentre, cost_centre_id)
        if not centre or centre.company_id != principal.user.company_id:
            raise HTTPException(status_code=422, detail="Cost centre does not belong to the active company")
        if centre.branch_id is not None and centre.branch_id != branch_id:
            raise HTTPException(status_code=422, detail="Cost centre is outside the selected branch scope")
        if site_id is not None and centre.site_id is not None and centre.site_id != site_id:
            raise HTTPException(status_code=422, detail="Cost centre is outside the selected site scope")


def employee_or_404(db: Session, principal: Principal, employee_id: int, permission: str) -> Employee:
    row = db.get(Employee, employee_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Employee not found")
    require_scope(principal, permission, row.branch_id, row.site_id)
    return row


def audit(db: Session, principal: Principal, action: str, entity_type: str, entity_id: str | int | None, *, employee_id: int | None = None, branch_id: int | None = None, detail: dict[str, Any] | None = None) -> None:
    db.add(WorkforceAuditEvent(
        company_id=principal.user.company_id,
        employee_id=employee_id,
        branch_id=branch_id,
        actor=principal.user.full_name,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        detail=detail or {},
    ))


def issue_reference(db: Session, company_id: int, code: str, fallback_prefix: str) -> str:
    sequence = db.scalar(select(NumberSequence).where(NumberSequence.company_id == company_id, NumberSequence.code == code))
    if not sequence:
        sequence = NumberSequence(company_id=company_id, code=code, name=code.replace("_", " ").title(), prefix=fallback_prefix, next_number=1, padding=5, reset_period="yearly")
        db.add(sequence)
        db.flush()
    now = utcnow()
    reset_key = str(now.year) if sequence.reset_period == "yearly" else (now.strftime("%Y-%m") if sequence.reset_period == "monthly" else "never")
    if sequence.reset_period != "never" and sequence.last_reset_key != reset_key:
        sequence.next_number = 1
        sequence.last_reset_key = reset_key
    number = sequence.next_number
    sequence.next_number += 1
    suffix = f"-{reset_key}" if sequence.reset_period == "yearly" else (f"-{reset_key.replace('-', '')}" if sequence.reset_period == "monthly" else "")
    return f"{sequence.prefix}{suffix}-{number:0{sequence.padding}d}"


def can_see_sensitive(principal: Principal, employee: Employee) -> bool:
    return principal.can("people.sensitive", branch_id=employee.branch_id, site_id=employee.site_id) or principal.can("payroll.view", branch_id=employee.branch_id, site_id=employee.site_id)


def employee_dict(principal: Principal, row: Employee) -> dict[str, Any]:
    result = row_dict(row)
    result["full_name"] = " ".join(part for part in [row.first_name, row.middle_names, row.last_name] if part)
    if not can_see_sensitive(principal, row):
        for field in ("national_id", "passport_number", "date_of_birth", "bank_name", "bank_account_name", "bank_account_number", "bank_branch_code"):
            result[field] = None
    return result


def configured_overtime_multiplier(db: Session, company_id: int) -> tuple[Decimal, bool]:
    setting = db.scalar(select(CompanySetting).where(CompanySetting.company_id == company_id, CompanySetting.key == "workforce_policy"))
    if setting and isinstance(setting.value, dict) and "overtime_multiplier" in setting.value:
        try:
            return Decimal(str(setting.value["overtime_multiplier"])), True
        except Exception:
            pass
    return Decimal("1.0"), False


class EmployeeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: int | None = None
    employee_number: str | None = Field(default=None, max_length=64)
    branch_id: int
    site_id: int | None = None
    department_id: int | None = None
    cost_centre_id: int | None = None
    title: str | None = Field(default=None, max_length=32)
    first_name: str = Field(min_length=1, max_length=120)
    middle_names: str | None = Field(default=None, max_length=180)
    last_name: str = Field(min_length=1, max_length=120)
    preferred_name: str | None = Field(default=None, max_length=120)
    national_id: str | None = Field(default=None, max_length=100)
    passport_number: str | None = Field(default=None, max_length=100)
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, max_length=32)
    nationality: str = Field(default="Lesotho", max_length=80)
    phone: str | None = Field(default=None, max_length=64)
    alternate_phone: str | None = Field(default=None, max_length=64)
    personal_email: EmailStr | None = None
    work_email: EmailStr | None = None
    physical_address: str | None = None
    postal_address: str | None = None
    job_title: str = Field(min_length=2, max_length=160)
    employment_type: Literal["permanent", "fixed_term", "temporary", "casual", "intern", "consultant"] = "permanent"
    employment_status: Literal["active", "on_leave", "suspended", "terminated", "inactive"] = "active"
    hire_date: date
    termination_date: date | None = None
    probation_end_date: date | None = None
    pay_basis: Literal["monthly", "hourly", "daily"] = "monthly"
    basic_rate: Decimal = Field(ge=0)
    standard_hours_per_week: Decimal = Field(default=Decimal("45"), gt=0, le=168)
    overtime_eligible: bool = True
    bank_name: str | None = Field(default=None, max_length=160)
    bank_account_name: str | None = Field(default=None, max_length=200)
    bank_account_number: str | None = Field(default=None, max_length=120)
    bank_branch_code: str | None = Field(default=None, max_length=64)
    emergency_contact_name: str | None = Field(default=None, max_length=200)
    emergency_contact_relationship: str | None = Field(default=None, max_length=80)
    emergency_contact_phone: str | None = Field(default=None, max_length=64)
    notes: str | None = None


class ContractInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_number: str | None = Field(default=None, max_length=80)
    contract_type: str = Field(default="permanent", max_length=40)
    start_date: date
    end_date: date | None = None
    job_title: str = Field(min_length=2, max_length=160)
    branch_id: int
    site_id: int | None = None
    department_id: int | None = None
    cost_centre_id: int | None = None
    pay_basis: Literal["monthly", "hourly", "daily"]
    basic_rate: Decimal = Field(ge=0)
    hours_per_week: Decimal = Field(default=Decimal("45"), gt=0, le=168)
    probation_end_date: date | None = None
    notice_period_days: int | None = Field(default=None, ge=0, le=3650)
    status: Literal["draft", "active", "expired", "terminated"] = "draft"
    notes: str | None = None


class ContractStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["draft", "active", "expired", "terminated"]
    employee_signed: bool = False
    company_signed: bool = False


class LeaveTypeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=120)
    paid: bool = True
    annual_entitlement_days: Decimal = Field(default=Decimal("0"), ge=0, le=366)
    accrual_method: Literal["annual", "monthly", "manual"] = "manual"
    carry_forward_limit_days: Decimal | None = Field(default=None, ge=0, le=366)
    requires_attachment: bool = False
    is_active: bool = True


class LeaveBalanceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employee_id: int
    leave_type_id: int
    year: int = Field(ge=2000, le=2200)
    opening_days: Decimal = Field(default=Decimal("0"), ge=0)
    accrued_days: Decimal = Field(default=Decimal("0"), ge=0)
    adjusted_days: Decimal = Decimal("0")


class LeaveRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employee_id: int
    leave_type_id: int
    start_date: date
    end_date: date
    days_requested: Decimal = Field(gt=0, le=366)
    reason: str | None = None


class DecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]
    comment: str | None = None


class ShiftInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=2, max_length=120)
    start_time: str
    end_time: str
    break_minutes: int = Field(default=60, ge=0, le=720)
    work_days: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5])
    is_active: bool = True


class ShiftAssignmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employee_id: int
    shift_id: int
    effective_from: date
    effective_to: date | None = None


class AttendanceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employee_id: int
    work_date: date
    branch_id: int | None = None
    site_id: int | None = None
    shift_id: int | None = None
    clock_in: datetime | None = None
    clock_out: datetime | None = None
    status: Literal["present", "absent", "leave", "sick", "off", "holiday"] = "present"
    regular_hours: Decimal = Field(default=Decimal("0"), ge=0, le=24)
    overtime_hours: Decimal = Field(default=Decimal("0"), ge=0, le=24)
    source: Literal["manual", "import", "clock", "site_diary"] = "manual"
    notes: str | None = None


class TimesheetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employee_id: int
    work_date: date
    branch_id: int | None = None
    site_id: int | None = None
    cost_centre_id: int | None = None
    regular_hours: Decimal = Field(default=Decimal("0"), ge=0, le=24)
    overtime_hours: Decimal = Field(default=Decimal("0"), ge=0, le=24)
    task_description: str | None = None


class PayComponentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=2, max_length=48)
    name: str = Field(min_length=2, max_length=160)
    component_type: Literal["earning", "deduction"]
    calculation_type: Literal["fixed", "percentage_basic", "per_hour"] = "fixed"
    default_value: Decimal = Field(default=Decimal("0"), ge=0)
    taxable: bool = False
    pensionable: bool = False
    affects_net_pay: bool = True
    is_active: bool = True


class EmployeePayComponentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employee_id: int
    component_id: int
    value: Decimal = Field(ge=0)
    effective_from: date
    effective_to: date | None = None
    notes: str | None = None


class PayrollPeriodInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=120)
    start_date: date
    end_date: date
    pay_date: date


class PayrollRunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period_id: int
    branch_id: int | None = None


class WorkforcePolicyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    overtime_multiplier: Decimal = Field(default=Decimal("1"), ge=0, le=10)
    require_approved_timesheets_for_hourly_pay: bool = True
    require_bank_details_before_approval: bool = False
    payroll_notes: str | None = None


@router.post("/bootstrap")
def bootstrap_phase3(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_company(principal, "roles.manage")
    company_id = principal.user.company_id
    permissions: dict[str, Permission] = {}
    for code, (module, action, description) in PHASE3_PERMISSIONS.items():
        row = db.scalar(select(Permission).where(Permission.code == code))
        if not row:
            row = Permission(code=code, module=module, action=action, description=description)
            db.add(row); db.flush()
        permissions[code] = row

    roles = {role.code: role for role in db.scalars(select(Role).where(Role.company_id == company_id)).all()}
    if "HR_MANAGER" not in roles:
        roles["HR_MANAGER"] = Role(company_id=company_id, code="HR_MANAGER", name="Human Resources Manager", description="Company workforce records, leave, attendance and employee controls", scope_level="company", is_system=True, is_active=True)
        db.add(roles["HR_MANAGER"]); db.flush()
    if "PAYROLL_OFFICER" not in roles:
        roles["PAYROLL_OFFICER"] = Role(company_id=company_id, code="PAYROLL_OFFICER", name="Payroll Officer", description="Payroll preparation and controlled workforce pay data", scope_level="company", is_system=True, is_active=True)
        db.add(roles["PAYROLL_OFFICER"]); db.flush()

    role_permissions: dict[str, set[str]] = {
        "SYSTEM_ADMIN": set(PHASE3_PERMISSIONS),
        "HQ_EXECUTIVE": {code for code, (_, action, _) in PHASE3_PERMISSIONS.items() if action in {"view", "approve", "export"}},
        "BRANCH_MANAGER": {"people.view", "people.manage", "leave.view", "leave.manage", "leave.approve", "attendance.view", "attendance.manage", "attendance.approve", "timesheets.view", "timesheets.manage", "timesheets.approve", "payroll.view"},
        "SITE_MANAGER": {"people.view", "leave.view", "attendance.view", "attendance.manage", "timesheets.view", "timesheets.manage", "timesheets.approve"},
        "APPROVER": {code for code, (_, action, _) in PHASE3_PERMISSIONS.items() if action == "approve"},
        "AUDITOR": {code for code, (_, action, _) in PHASE3_PERMISSIONS.items() if action in {"view", "export"}},
        "HR_MANAGER": {"people.view", "people.manage", "people.export", "people.sensitive", "leave.view", "leave.manage", "leave.approve", "attendance.view", "attendance.manage", "attendance.approve", "timesheets.view", "timesheets.manage", "timesheets.approve", "payroll.view"},
        "PAYROLL_OFFICER": {"people.view", "people.sensitive", "attendance.view", "timesheets.view", "payroll.view", "payroll.manage", "payroll.export"},
    }
    for role_code, permission_codes in role_permissions.items():
        role = roles.get(role_code)
        if not role:
            continue
        existing = set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id == role.id)).all())
        for permission_code in permission_codes:
            permission = permissions.get(permission_code)
            if permission and permission.id not in existing:
                db.add(RolePermission(role_id=role.id, permission_id=permission.id))

    for code, name, prefix in (("CONTRACT", "Employment Contract", "CTR"), ("PAYROLL", "Payroll Run", "PAY")):
        if not db.scalar(select(NumberSequence).where(NumberSequence.company_id == company_id, NumberSequence.code == code)):
            db.add(NumberSequence(company_id=company_id, code=code, name=name, prefix=prefix, padding=5, reset_period="yearly"))

    if not db.scalar(select(CompanySetting).where(CompanySetting.company_id == company_id, CompanySetting.key == "workforce_policy")):
        db.add(CompanySetting(company_id=company_id, key="workforce_policy", value={"overtime_multiplier": 1.0, "require_approved_timesheets_for_hourly_pay": True, "require_bank_details_before_approval": False, "payroll_notes": "Configure company overtime and statutory payroll policy before production payroll approval."}, description="Phase 3 workforce and payroll preparation controls"))

    if not db.scalar(select(Shift).where(Shift.company_id == company_id, Shift.code == "DAY")):
        db.add(Shift(company_id=company_id, code="DAY", name="Standard Day Shift", start_time=datetime.strptime("08:00", "%H:%M").time(), end_time=datetime.strptime("17:00", "%H:%M").time(), break_minutes=60, work_days=[1,2,3,4,5]))
    for code, name, paid in (("ANNUAL", "Annual Leave", True), ("SICK", "Sick Leave", True), ("UNPAID", "Unpaid Leave", False)):
        if not db.scalar(select(LeaveType).where(LeaveType.company_id == company_id, LeaveType.code == code)):
            db.add(LeaveType(company_id=company_id, code=code, name=name, paid=paid, annual_entitlement_days=Decimal("0"), accrual_method="manual", is_active=True))
    for code, name, kind in (("OTHER_EARNING", "Other Earning", "earning"), ("OTHER_DEDUCTION", "Other Deduction", "deduction")):
        if not db.scalar(select(PayComponent).where(PayComponent.company_id == company_id, PayComponent.code == code)):
            db.add(PayComponent(company_id=company_id, code=code, name=name, component_type=kind, calculation_type="fixed", default_value=Decimal("0"), taxable=False, pensionable=False, affects_net_pay=True, is_active=True))
    audit(db, principal, "phase3.bootstrap", "workforce", company_id, detail={"permissions": len(PHASE3_PERMISSIONS)})
    commit(db)
    return {"status": "operational", "phase": 3, "message": "Workforce and payroll controls initialised. Configure leave, overtime and statutory payroll policy before production use."}


@router.get("/status")
def phase3_status(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    initialized = bool(db.scalar(select(Permission.id).where(Permission.code == "payroll.manage")))
    return {"phase": 3, "initialized": initialized, "can_initialize": principal.has_company_permission("roles.manage")}


@router.get("/summary")
def workforce_summary(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if not principal.has_permission_anywhere("people.view"):
        raise HTTPException(status_code=403, detail="Permission required: people.view")
    employees = [e for e in db.scalars(select(Employee).where(Employee.company_id == principal.user.company_id)).all() if principal.can("people.view", branch_id=e.branch_id, site_id=e.site_id)]
    employee_ids = {e.id for e in employees}
    today = date.today()
    leave_pending = [r for r in db.scalars(select(LeaveRequest).where(LeaveRequest.company_id == principal.user.company_id, LeaveRequest.status == "pending")).all() if r.employee_id in employee_ids]
    attendance_today = [r for r in db.scalars(select(AttendanceRecord).where(AttendanceRecord.company_id == principal.user.company_id, AttendanceRecord.work_date == today)).all() if r.employee_id in employee_ids]
    payroll_runs = db.scalars(select(PayrollRun).where(PayrollRun.company_id == principal.user.company_id).order_by(PayrollRun.id.desc()).limit(10)).all() if principal.has_permission_anywhere("payroll.view") else []
    return {"counts": {"employees": len(employees), "active_employees": sum(1 for e in employees if e.employment_status == "active"), "pending_leave": len(leave_pending), "attendance_today": len(attendance_today), "payroll_runs": len(payroll_runs)}, "latest_payroll_runs": [row_dict(r) for r in payroll_runs]}


@router.get("/catalog")
def workforce_catalog(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    company_id = principal.user.company_id
    branches = [row_dict(r) for r in db.scalars(select(Branch).where(Branch.company_id == company_id, Branch.is_active.is_(True))).all() if principal.can("people.view", branch_id=r.id)]
    sites = [row_dict(r) for r in db.scalars(select(Site).where(Site.company_id == company_id, Site.is_active.is_(True))).all() if principal.can("people.view", branch_id=r.branch_id, site_id=r.id)]
    return {"branches": branches, "sites": sites, "departments": [row_dict(r) for r in db.scalars(select(Department).where(Department.company_id == company_id, Department.is_active.is_(True))).all()], "cost_centres": [row_dict(r) for r in db.scalars(select(CostCentre).where(CostCentre.company_id == company_id, CostCentre.is_active.is_(True))).all()], "users": [row_dict(r) for r in db.scalars(select(User).where(User.company_id == company_id, User.is_active.is_(True))).all()] if principal.has_company_permission("users.view") else [], "leave_types": [row_dict(r) for r in db.scalars(select(LeaveType).where(LeaveType.company_id == company_id)).all()], "shifts": [row_dict(r) for r in db.scalars(select(Shift).where(Shift.company_id == company_id)).all()], "pay_components": [row_dict(r) for r in db.scalars(select(PayComponent).where(PayComponent.company_id == company_id)).all()] if principal.has_permission_anywhere("payroll.view") else [], "permissions": sorted(principal.permission_codes)}


@router.get("/employees")
def list_employees(branch_id: int | None = None, status_filter: str | None = Query(default=None, alias="status"), db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    statement = select(Employee).where(Employee.company_id == principal.user.company_id)
    if branch_id is not None: statement = statement.where(Employee.branch_id == branch_id)
    if status_filter: statement = statement.where(Employee.employment_status == status_filter)
    rows = db.scalars(statement.order_by(Employee.employee_number)).all()
    return [employee_dict(principal, row) for row in rows if principal.can("people.view", branch_id=row.branch_id, site_id=row.site_id)]


@router.get("/employees/{employee_id}")
def get_employee(employee_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = employee_or_404(db, principal, employee_id, "people.view")
    contracts = db.scalars(select(EmploymentContract).where(EmploymentContract.employee_id == row.id).order_by(EmploymentContract.start_date.desc())).all()
    balances = db.scalars(select(LeaveBalance).where(LeaveBalance.employee_id == row.id).order_by(LeaveBalance.year.desc())).all()
    pay_components = db.scalars(select(EmployeePayComponent).where(EmployeePayComponent.employee_id == row.id)).all() if principal.can("payroll.view", branch_id=row.branch_id, site_id=row.site_id) else []
    return {**employee_dict(principal, row), "contracts": [row_dict(item) for item in contracts], "leave_balances": [row_dict(item) for item in balances], "pay_components": [row_dict(item) for item in pay_components]}


@router.post("/employees", status_code=201)
def create_employee(payload: EmployeeInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_scope(principal, "people.manage", payload.branch_id, payload.site_id)
    ensure_org_scope(db, principal, payload.branch_id, payload.site_id, payload.department_id, payload.cost_centre_id)
    if payload.user_id is not None:
        user = db.get(User, payload.user_id)
        if not user or user.company_id != principal.user.company_id: raise HTTPException(status_code=422, detail="Linked user does not belong to the active company")
    values = payload.model_dump()
    values["employee_number"] = (payload.employee_number or issue_reference(db, principal.user.company_id, "EMPLOYEE", "EMP")).strip().upper()
    row = Employee(company_id=principal.user.company_id, created_by=principal.user.full_name, **values)
    db.add(row); db.flush()
    current_year = date.today().year
    for leave_type in db.scalars(select(LeaveType).where(LeaveType.company_id == principal.user.company_id, LeaveType.is_active.is_(True))).all():
        db.add(LeaveBalance(employee_id=row.id, leave_type_id=leave_type.id, year=current_year, accrued_days=leave_type.annual_entitlement_days))
    audit(db, principal, "employee.create", "employee", row.id, employee_id=row.id, branch_id=row.branch_id, detail={"employee_number": row.employee_number, "job_title": row.job_title})
    commit(db, "Employee number or linked user is already assigned")
    db.refresh(row)
    return employee_dict(principal, row)


@router.put("/employees/{employee_id}")
def update_employee(employee_id: int, payload: EmployeeInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = employee_or_404(db, principal, employee_id, "people.manage")
    require_scope(principal, "people.manage", payload.branch_id, payload.site_id)
    ensure_org_scope(db, principal, payload.branch_id, payload.site_id, payload.department_id, payload.cost_centre_id)
    values = payload.model_dump(exclude={"employee_number"})
    for key, value in values.items(): setattr(row, key, value)
    if payload.employee_number: row.employee_number = payload.employee_number.strip().upper()
    audit(db, principal, "employee.update", "employee", row.id, employee_id=row.id, branch_id=row.branch_id, detail={"employment_status": row.employment_status, "job_title": row.job_title})
    commit(db)
    return employee_dict(principal, row)


@router.post("/employees/{employee_id}/contracts", status_code=201)
def create_contract(employee_id: int, payload: ContractInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    employee = employee_or_404(db, principal, employee_id, "people.manage")
    require_scope(principal, "people.manage", payload.branch_id, payload.site_id)
    ensure_org_scope(db, principal, payload.branch_id, payload.site_id, payload.department_id, payload.cost_centre_id)
    if payload.end_date and payload.end_date < payload.start_date: raise HTTPException(status_code=422, detail="Contract end date cannot be before start date")
    values = payload.model_dump()
    values["contract_number"] = payload.contract_number or issue_reference(db, principal.user.company_id, "CONTRACT", "CTR")
    row = EmploymentContract(company_id=principal.user.company_id, employee_id=employee.id, created_by=principal.user.full_name, **values)
    db.add(row); db.flush()
    audit(db, principal, "contract.create", "employment_contract", row.id, employee_id=employee.id, branch_id=row.branch_id, detail={"contract_number": row.contract_number, "status": row.status})
    commit(db)
    return row_dict(row)


@router.post("/contracts/{contract_id}/status")
def contract_status(contract_id: int, payload: ContractStatusInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = db.get(EmploymentContract, contract_id)
    if not row or row.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Contract not found")
    employee = employee_or_404(db, principal, row.employee_id, "people.approve" if payload.status == "active" else "people.manage")
    now = utcnow()
    row.status = payload.status
    if payload.employee_signed: row.signed_employee_at = row.signed_employee_at or now
    if payload.company_signed: row.signed_company_at = row.signed_company_at or now
    if payload.status == "active":
        if not row.signed_company_at: raise HTTPException(status_code=422, detail="Company signature confirmation is required before activating a contract")
        employee.job_title = row.job_title; employee.branch_id = row.branch_id; employee.site_id = row.site_id; employee.department_id = row.department_id; employee.cost_centre_id = row.cost_centre_id; employee.pay_basis = row.pay_basis; employee.basic_rate = row.basic_rate; employee.standard_hours_per_week = row.hours_per_week
    audit(db, principal, "contract.status", "employment_contract", row.id, employee_id=employee.id, branch_id=row.branch_id, detail={"status": row.status})
    commit(db)
    return row_dict(row)


@router.get("/leave-types")
def list_leave_types(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    if not principal.has_permission_anywhere("leave.view"): raise HTTPException(status_code=403, detail="Permission required: leave.view")
    return [row_dict(r) for r in db.scalars(select(LeaveType).where(LeaveType.company_id == principal.user.company_id).order_by(LeaveType.code)).all()]


@router.post("/leave-types", status_code=201)
def create_leave_type(payload: LeaveTypeInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_company(principal, "leave.manage")
    row = LeaveType(company_id=principal.user.company_id, **payload.model_dump()); row.code = row.code.strip().upper(); db.add(row); commit(db); return row_dict(row)


@router.put("/leave-types/{leave_type_id}")
def update_leave_type(leave_type_id: int, payload: LeaveTypeInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_company(principal, "leave.manage")
    row = db.get(LeaveType, leave_type_id)
    if not row or row.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Leave type not found")
    for key, value in payload.model_dump().items(): setattr(row, key, value)
    row.code = row.code.strip().upper(); commit(db); return row_dict(row)


@router.get("/leave-balances")
def list_leave_balances(employee_id: int | None = None, year: int | None = None, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    statement = select(LeaveBalance).join(Employee, Employee.id == LeaveBalance.employee_id).where(Employee.company_id == principal.user.company_id)
    if employee_id is not None: statement = statement.where(LeaveBalance.employee_id == employee_id)
    if year is not None: statement = statement.where(LeaveBalance.year == year)
    result = []
    for balance, employee in [(b, db.get(Employee, b.employee_id)) for b in db.scalars(statement.order_by(LeaveBalance.year.desc())).all()]:
        if employee and principal.can("leave.view", branch_id=employee.branch_id, site_id=employee.site_id):
            item = row_dict(balance); item["available_days"] = str(balance.opening_days + balance.accrued_days + balance.adjusted_days - balance.taken_days); result.append(item)
    return result


@router.put("/leave-balances")
def set_leave_balance(payload: LeaveBalanceInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    employee = employee_or_404(db, principal, payload.employee_id, "leave.manage")
    leave_type = db.get(LeaveType, payload.leave_type_id)
    if not leave_type or leave_type.company_id != principal.user.company_id: raise HTTPException(status_code=422, detail="Leave type is invalid")
    row = db.scalar(select(LeaveBalance).where(LeaveBalance.employee_id == employee.id, LeaveBalance.leave_type_id == leave_type.id, LeaveBalance.year == payload.year))
    if not row:
        row = LeaveBalance(employee_id=employee.id, leave_type_id=leave_type.id, year=payload.year); db.add(row)
    row.opening_days = payload.opening_days; row.accrued_days = payload.accrued_days; row.adjusted_days = payload.adjusted_days
    audit(db, principal, "leave.balance.adjust", "leave_balance", row.id, employee_id=employee.id, branch_id=employee.branch_id, detail={"year": payload.year, "leave_type": leave_type.code})
    commit(db); db.refresh(row)
    result = row_dict(row); result["available_days"] = str(row.opening_days + row.accrued_days + row.adjusted_days - row.taken_days); return result


@router.get("/leave-requests")
def list_leave_requests(status_filter: str | None = Query(default=None, alias="status"), db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    statement = select(LeaveRequest).where(LeaveRequest.company_id == principal.user.company_id)
    if status_filter: statement = statement.where(LeaveRequest.status == status_filter)
    output = []
    for row in db.scalars(statement.order_by(LeaveRequest.id.desc())).all():
        employee = db.get(Employee, row.employee_id)
        if employee and principal.can("leave.view", branch_id=employee.branch_id, site_id=employee.site_id): output.append(row_dict(row))
    return output


@router.post("/leave-requests", status_code=201)
def create_leave_request(payload: LeaveRequestInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    employee = employee_or_404(db, principal, payload.employee_id, "leave.manage")
    leave_type = db.get(LeaveType, payload.leave_type_id)
    if not leave_type or leave_type.company_id != principal.user.company_id or not leave_type.is_active: raise HTTPException(status_code=422, detail="Leave type is invalid")
    if payload.end_date < payload.start_date: raise HTTPException(status_code=422, detail="Leave end date cannot be before start date")
    row = LeaveRequest(company_id=principal.user.company_id, requested_by=principal.user.full_name, **payload.model_dump()); db.add(row); db.flush()
    audit(db, principal, "leave.request", "leave_request", row.id, employee_id=employee.id, branch_id=employee.branch_id, detail={"days": str(row.days_requested), "leave_type_id": row.leave_type_id})
    commit(db); return row_dict(row)


@router.post("/leave-requests/{request_id}/decision")
def decide_leave(request_id: int, payload: DecisionInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = db.get(LeaveRequest, request_id)
    if not row or row.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Leave request not found")
    employee = employee_or_404(db, principal, row.employee_id, "leave.approve")
    if row.status != "pending": raise HTTPException(status_code=409, detail="Leave request has already been decided")
    leave_type = db.get(LeaveType, row.leave_type_id)
    if payload.decision == "approve" and leave_type and leave_type.paid:
        balance = db.scalar(select(LeaveBalance).where(LeaveBalance.employee_id == employee.id, LeaveBalance.leave_type_id == row.leave_type_id, LeaveBalance.year == row.start_date.year))
        available = (balance.opening_days + balance.accrued_days + balance.adjusted_days - balance.taken_days) if balance else Decimal("0")
        if available < row.days_requested: raise HTTPException(status_code=422, detail=f"Insufficient leave balance: {available} day(s) available")
        balance.taken_days += row.days_requested
    row.status = "approved" if payload.decision == "approve" else "rejected"; row.decided_by = principal.user.full_name; row.decided_at = utcnow(); row.decision_comment = payload.comment
    audit(db, principal, f"leave.{row.status}", "leave_request", row.id, employee_id=employee.id, branch_id=employee.branch_id)
    commit(db); return row_dict(row)


@router.get("/shifts")
def list_shifts(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    if not principal.has_permission_anywhere("attendance.view"): raise HTTPException(status_code=403, detail="Permission required: attendance.view")
    return [row_dict(r) for r in db.scalars(select(Shift).where(Shift.company_id == principal.user.company_id).order_by(Shift.code)).all()]


@router.post("/shifts", status_code=201)
def create_shift(payload: ShiftInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_company(principal, "attendance.manage")
    try: start = datetime.strptime(payload.start_time, "%H:%M").time(); end = datetime.strptime(payload.end_time, "%H:%M").time()
    except ValueError as error: raise HTTPException(status_code=422, detail="Shift times must use HH:MM") from error
    if any(day < 1 or day > 7 for day in payload.work_days): raise HTTPException(status_code=422, detail="work_days must use ISO weekday numbers 1-7")
    row = Shift(company_id=principal.user.company_id, code=payload.code.strip().upper(), name=payload.name, start_time=start, end_time=end, break_minutes=payload.break_minutes, work_days=payload.work_days, is_active=payload.is_active); db.add(row); commit(db); return row_dict(row)


@router.post("/shift-assignments", status_code=201)
def assign_shift(payload: ShiftAssignmentInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    employee = employee_or_404(db, principal, payload.employee_id, "attendance.manage")
    shift = db.get(Shift, payload.shift_id)
    if not shift or shift.company_id != principal.user.company_id: raise HTTPException(status_code=422, detail="Shift is invalid")
    if payload.effective_to and payload.effective_to < payload.effective_from: raise HTTPException(status_code=422, detail="Shift assignment end date is invalid")
    row = EmployeeShiftAssignment(**payload.model_dump()); db.add(row); audit(db, principal, "shift.assign", "employee_shift_assignment", row.id, employee_id=employee.id, branch_id=employee.branch_id); commit(db); db.refresh(row); return row_dict(row)


@router.get("/attendance")
def list_attendance(start: date | None = None, end: date | None = None, employee_id: int | None = None, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    statement = select(AttendanceRecord).where(AttendanceRecord.company_id == principal.user.company_id)
    if start: statement = statement.where(AttendanceRecord.work_date >= start)
    if end: statement = statement.where(AttendanceRecord.work_date <= end)
    if employee_id: statement = statement.where(AttendanceRecord.employee_id == employee_id)
    return [row_dict(r) for r in db.scalars(statement.order_by(AttendanceRecord.work_date.desc())).all() if principal.can("attendance.view", branch_id=r.branch_id, site_id=r.site_id)]


@router.put("/attendance")
def upsert_attendance(payload: AttendanceInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    employee = employee_or_404(db, principal, payload.employee_id, "attendance.manage")
    branch_id = payload.branch_id or employee.branch_id; site_id = payload.site_id if payload.site_id is not None else employee.site_id
    require_scope(principal, "attendance.manage", branch_id, site_id); ensure_org_scope(db, principal, branch_id, site_id)
    row = db.scalar(select(AttendanceRecord).where(AttendanceRecord.employee_id == employee.id, AttendanceRecord.work_date == payload.work_date))
    values = payload.model_dump(exclude={"employee_id", "branch_id", "site_id"})
    if not row:
        row = AttendanceRecord(company_id=principal.user.company_id, employee_id=employee.id, branch_id=branch_id, site_id=site_id, recorded_by=principal.user.full_name, **values); db.add(row)
    else:
        row.branch_id = branch_id; row.site_id = site_id
        for key, value in values.items(): setattr(row, key, value)
        row.recorded_by = principal.user.full_name
    audit(db, principal, "attendance.upsert", "attendance", row.id, employee_id=employee.id, branch_id=branch_id, detail={"date": str(payload.work_date), "status": payload.status})
    commit(db); db.refresh(row); return row_dict(row)


@router.get("/timesheets")
def list_timesheets(start: date | None = None, end: date | None = None, status_filter: str | None = Query(default=None, alias="status"), db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    statement = select(TimesheetEntry).where(TimesheetEntry.company_id == principal.user.company_id)
    if start: statement = statement.where(TimesheetEntry.work_date >= start)
    if end: statement = statement.where(TimesheetEntry.work_date <= end)
    if status_filter: statement = statement.where(TimesheetEntry.status == status_filter)
    return [row_dict(r) for r in db.scalars(statement.order_by(TimesheetEntry.work_date.desc(), TimesheetEntry.id.desc())).all() if principal.can("timesheets.view", branch_id=r.branch_id, site_id=r.site_id)]


@router.post("/timesheets", status_code=201)
def create_timesheet(payload: TimesheetInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    employee = employee_or_404(db, principal, payload.employee_id, "timesheets.manage")
    branch_id = payload.branch_id or employee.branch_id; site_id = payload.site_id if payload.site_id is not None else employee.site_id; cost_centre_id = payload.cost_centre_id if payload.cost_centre_id is not None else employee.cost_centre_id
    require_scope(principal, "timesheets.manage", branch_id, site_id); ensure_org_scope(db, principal, branch_id, site_id, cost_centre_id=cost_centre_id)
    row = TimesheetEntry(company_id=principal.user.company_id, employee_id=employee.id, branch_id=branch_id, site_id=site_id, cost_centre_id=cost_centre_id, regular_hours=payload.regular_hours, overtime_hours=payload.overtime_hours, work_date=payload.work_date, task_description=payload.task_description, created_by=principal.user.full_name); db.add(row); db.flush()
    audit(db, principal, "timesheet.create", "timesheet", row.id, employee_id=employee.id, branch_id=branch_id); commit(db); return row_dict(row)


@router.post("/timesheets/{entry_id}/submit")
def submit_timesheet(entry_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = db.get(TimesheetEntry, entry_id)
    if not row or row.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Timesheet not found")
    require_scope(principal, "timesheets.manage", row.branch_id, row.site_id)
    if row.status != "draft": raise HTTPException(status_code=409, detail="Only draft timesheets can be submitted")
    row.status = "submitted"; row.submitted_at = utcnow(); commit(db); return row_dict(row)


@router.post("/timesheets/{entry_id}/decision")
def decide_timesheet(entry_id: int, payload: DecisionInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = db.get(TimesheetEntry, entry_id)
    if not row or row.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Timesheet not found")
    require_scope(principal, "timesheets.approve", row.branch_id, row.site_id)
    if row.status != "submitted": raise HTTPException(status_code=409, detail="Only submitted timesheets can be decided")
    row.status = "approved" if payload.decision == "approve" else "rejected"; row.approved_by = principal.user.full_name; row.approved_at = utcnow(); audit(db, principal, f"timesheet.{row.status}", "timesheet", row.id, employee_id=row.employee_id, branch_id=row.branch_id); commit(db); return row_dict(row)


@router.get("/pay-components")
def list_pay_components(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    if not principal.has_permission_anywhere("payroll.view"): raise HTTPException(status_code=403, detail="Permission required: payroll.view")
    return [row_dict(r) for r in db.scalars(select(PayComponent).where(PayComponent.company_id == principal.user.company_id).order_by(PayComponent.code)).all()]


@router.post("/pay-components", status_code=201)
def create_pay_component(payload: PayComponentInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_company(principal, "payroll.manage")
    row = PayComponent(company_id=principal.user.company_id, **payload.model_dump()); row.code = row.code.strip().upper(); db.add(row); commit(db); return row_dict(row)


@router.put("/employee-pay-components")
def set_employee_pay_component(payload: EmployeePayComponentInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    employee = employee_or_404(db, principal, payload.employee_id, "payroll.manage")
    component = db.get(PayComponent, payload.component_id)
    if not component or component.company_id != principal.user.company_id: raise HTTPException(status_code=422, detail="Pay component is invalid")
    row = db.scalar(select(EmployeePayComponent).where(EmployeePayComponent.employee_id == employee.id, EmployeePayComponent.component_id == component.id))
    values = payload.model_dump(exclude={"employee_id", "component_id"})
    if not row: row = EmployeePayComponent(employee_id=employee.id, component_id=component.id, **values); db.add(row)
    else:
        for key, value in values.items(): setattr(row, key, value)
    audit(db, principal, "pay_component.assign", "employee_pay_component", row.id, employee_id=employee.id, branch_id=employee.branch_id, detail={"component": component.code}); commit(db); db.refresh(row); return row_dict(row)


@router.get("/payroll-periods")
def list_payroll_periods(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    if not principal.has_permission_anywhere("payroll.view"): raise HTTPException(status_code=403, detail="Permission required: payroll.view")
    return [row_dict(r) for r in db.scalars(select(PayrollPeriod).where(PayrollPeriod.company_id == principal.user.company_id).order_by(PayrollPeriod.start_date.desc())).all()]


@router.post("/payroll-periods", status_code=201)
def create_payroll_period(payload: PayrollPeriodInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_company(principal, "payroll.manage")
    if payload.end_date < payload.start_date: raise HTTPException(status_code=422, detail="Payroll period end date cannot be before start date")
    row = PayrollPeriod(company_id=principal.user.company_id, status="open", **payload.model_dump()); row.code = row.code.strip().upper(); db.add(row); commit(db); return row_dict(row)


@router.get("/payroll-runs")
def list_payroll_runs(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    rows = db.scalars(select(PayrollRun).where(PayrollRun.company_id == principal.user.company_id).order_by(PayrollRun.id.desc())).all()
    return [row_dict(r) for r in rows if principal.can("payroll.view", branch_id=r.branch_id)]


@router.post("/payroll-runs", status_code=201)
def create_payroll_run(payload: PayrollRunInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    period = db.get(PayrollPeriod, payload.period_id)
    if not period or period.company_id != principal.user.company_id: raise HTTPException(status_code=422, detail="Payroll period is invalid")
    if period.status != "open": raise HTTPException(status_code=409, detail="Payroll period is not open")
    if payload.branch_id is None: require_company(principal, "payroll.manage")
    else: require_scope(principal, "payroll.manage", payload.branch_id)
    row = PayrollRun(company_id=principal.user.company_id, period_id=period.id, branch_id=payload.branch_id, status="draft", prepared_by=principal.user.full_name); db.add(row); db.flush(); audit(db, principal, "payroll.run.create", "payroll_run", row.id, branch_id=row.branch_id); commit(db); return row_dict(row)


def component_amount(component: PayComponent, assigned: EmployeePayComponent, basic_pay: Decimal, total_hours: Decimal) -> Decimal:
    value = Decimal(assigned.value)
    if component.calculation_type == "percentage_basic": return money(basic_pay * value / Decimal("100"))
    if component.calculation_type == "per_hour": return money(total_hours * value)
    return money(value)


@router.post("/payroll-runs/{run_id}/calculate")
def calculate_payroll(run_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    run = db.get(PayrollRun, run_id)
    if not run or run.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Payroll run not found")
    require_scope(principal, "payroll.manage", run.branch_id)
    if run.status not in {"draft", "calculated"}: raise HTTPException(status_code=409, detail="Reviewed or approved payroll cannot be recalculated")
    period = db.get(PayrollPeriod, run.period_id)
    if not period: raise HTTPException(status_code=422, detail="Payroll period is missing")
    db.execute(delete(PayrollLine).where(PayrollLine.run_id == run.id))
    employees_statement = select(Employee).where(Employee.company_id == principal.user.company_id, Employee.employment_status.in_(["active", "on_leave"]), Employee.hire_date <= period.end_date)
    if run.branch_id is not None: employees_statement = employees_statement.where(Employee.branch_id == run.branch_id)
    employees = [e for e in db.scalars(employees_statement.order_by(Employee.employee_number)).all() if principal.can("payroll.manage", branch_id=e.branch_id, site_id=e.site_id)]
    overtime_multiplier, overtime_configured = configured_overtime_multiplier(db, principal.user.company_id)
    setting = db.scalar(select(CompanySetting).where(CompanySetting.company_id == principal.user.company_id, CompanySetting.key == "workforce_policy"))
    policy = setting.value if setting and isinstance(setting.value, dict) else {}
    require_timesheets = bool(policy.get("require_approved_timesheets_for_hourly_pay", True))
    total_gross = total_deductions = total_net = Decimal("0")
    for employee in employees:
        timesheets = db.scalars(select(TimesheetEntry).where(TimesheetEntry.employee_id == employee.id, TimesheetEntry.work_date >= period.start_date, TimesheetEntry.work_date <= period.end_date, TimesheetEntry.status == "approved")).all()
        regular_hours = sum((Decimal(item.regular_hours) for item in timesheets), Decimal("0")); overtime_hours = sum((Decimal(item.overtime_hours) for item in timesheets), Decimal("0"))
        attendance_days = db.scalar(select(func.count()).select_from(AttendanceRecord).where(AttendanceRecord.employee_id == employee.id, AttendanceRecord.work_date >= period.start_date, AttendanceRecord.work_date <= period.end_date, AttendanceRecord.status == "present")) or 0
        warnings: list[str] = []
        if employee.pay_basis == "monthly": basic_pay = money(employee.basic_rate)
        elif employee.pay_basis == "hourly":
            basic_pay = money(regular_hours * Decimal(employee.basic_rate))
            if require_timesheets and not timesheets: warnings.append("No approved timesheets for hourly-paid employee")
        else:
            basic_pay = money(Decimal(attendance_days) * Decimal(employee.basic_rate))
            if attendance_days == 0: warnings.append("No present attendance days for daily-paid employee")
        overtime_pay = Decimal("0")
        if employee.overtime_eligible and overtime_hours > 0:
            if employee.pay_basis == "hourly": hourly_rate = Decimal(employee.basic_rate)
            elif employee.pay_basis == "daily": hourly_rate = Decimal(employee.basic_rate) / max(Decimal(employee.standard_hours_per_week) / Decimal("5"), Decimal("1"))
            else: hourly_rate = Decimal(employee.basic_rate) / max((Decimal(employee.standard_hours_per_week) * Decimal("52") / Decimal("12")), Decimal("1"))
            overtime_pay = money(overtime_hours * hourly_rate * overtime_multiplier)
            if not overtime_configured: warnings.append("Overtime multiplier is using safe default 1.0; configure workforce policy")
        components = db.scalars(select(EmployeePayComponent).where(EmployeePayComponent.employee_id == employee.id, EmployeePayComponent.effective_from <= period.end_date, (EmployeePayComponent.effective_to.is_(None) | (EmployeePayComponent.effective_to >= period.start_date)))).all()
        earnings = overtime_pay; deductions = Decimal("0"); breakdown: list[dict[str, Any]] = []
        if overtime_pay: breakdown.append({"code": "OVERTIME", "type": "earning", "amount": str(overtime_pay), "hours": str(overtime_hours), "multiplier": str(overtime_multiplier)})
        for assigned in components:
            component = db.get(PayComponent, assigned.component_id)
            if not component or not component.is_active: continue
            amount = component_amount(component, assigned, basic_pay, regular_hours + overtime_hours)
            if component.component_type == "earning": earnings += amount
            elif component.affects_net_pay: deductions += amount
            breakdown.append({"code": component.code, "name": component.name, "type": component.component_type, "amount": str(amount), "taxable": component.taxable})
        gross = money(basic_pay + earnings); net = money(gross - deductions)
        if not employee.bank_account_number: warnings.append("Bank account details are missing")
        approved_unpaid = db.scalar(select(func.count()).select_from(LeaveRequest).join(LeaveType, LeaveType.id == LeaveRequest.leave_type_id).where(LeaveRequest.employee_id == employee.id, LeaveRequest.status == "approved", LeaveType.paid.is_(False), LeaveRequest.start_date <= period.end_date, LeaveRequest.end_date >= period.start_date)) or 0
        if approved_unpaid and employee.pay_basis == "monthly": warnings.append("Approved unpaid leave overlaps this period; apply the company deduction policy before approval")
        line = PayrollLine(run_id=run.id, employee_id=employee.id, branch_id=employee.branch_id, site_id=employee.site_id, cost_centre_id=employee.cost_centre_id, regular_hours=regular_hours, overtime_hours=overtime_hours, basic_pay=basic_pay, earnings=money(earnings), deductions=money(deductions), gross_pay=gross, net_pay=net, component_breakdown=breakdown, warnings=warnings)
        db.add(line); total_gross += gross; total_deductions += money(deductions); total_net += net
    run.employee_count = len(employees); run.total_gross = money(total_gross); run.total_deductions = money(total_deductions); run.total_net = money(total_net); run.status = "calculated"; run.prepared_by = principal.user.full_name; run.prepared_at = utcnow()
    audit(db, principal, "payroll.run.calculate", "payroll_run", run.id, branch_id=run.branch_id, detail={"employees": len(employees), "gross": str(run.total_gross), "net": str(run.total_net)})
    commit(db); return {**row_dict(run), "lines": [row_dict(r) for r in db.scalars(select(PayrollLine).where(PayrollLine.run_id == run.id).order_by(PayrollLine.employee_id)).all()]}


@router.get("/payroll-runs/{run_id}")
def get_payroll_run(run_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    run = db.get(PayrollRun, run_id)
    if not run or run.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Payroll run not found")
    require_scope(principal, "payroll.view", run.branch_id)
    lines = db.scalars(select(PayrollLine).where(PayrollLine.run_id == run.id).order_by(PayrollLine.employee_id)).all()
    enriched = []
    for line in lines:
        employee = db.get(Employee, line.employee_id); item = row_dict(line); item["employee_number"] = employee.employee_number if employee else ""; item["employee_name"] = f"{employee.first_name} {employee.last_name}" if employee else ""; enriched.append(item)
    return {**row_dict(run), "lines": enriched}


@router.post("/payroll-runs/{run_id}/review")
def review_payroll(run_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    run = db.get(PayrollRun, run_id)
    if not run or run.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Payroll run not found")
    require_scope(principal, "payroll.approve", run.branch_id)
    if run.status != "calculated": raise HTTPException(status_code=409, detail="Payroll must be calculated before review")
    run.status = "reviewed"; run.reviewed_by = principal.user.full_name; run.reviewed_at = utcnow(); audit(db, principal, "payroll.run.review", "payroll_run", run.id, branch_id=run.branch_id); commit(db); return row_dict(run)


@router.post("/payroll-runs/{run_id}/approve")
def approve_payroll(run_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    run = db.get(PayrollRun, run_id)
    if not run or run.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Payroll run not found")
    require_scope(principal, "payroll.approve", run.branch_id)
    if run.status != "reviewed": raise HTTPException(status_code=409, detail="Payroll must be reviewed before approval")
    setting = db.scalar(select(CompanySetting).where(CompanySetting.company_id == principal.user.company_id, CompanySetting.key == "workforce_policy")); policy = setting.value if setting and isinstance(setting.value, dict) else {}
    if policy.get("require_bank_details_before_approval"):
        missing = []
        for line in db.scalars(select(PayrollLine).where(PayrollLine.run_id == run.id)).all():
            employee = db.get(Employee, line.employee_id)
            if employee and not employee.bank_account_number: missing.append(employee.employee_number)
        if missing: raise HTTPException(status_code=422, detail=f"Bank details are missing for: {', '.join(missing[:20])}")
    run.status = "approved"; run.approved_by = principal.user.full_name; run.approved_at = utcnow(); period = db.get(PayrollPeriod, run.period_id)
    if period: period.status = "closed"
    audit(db, principal, "payroll.run.approve", "payroll_run", run.id, branch_id=run.branch_id, detail={"net": str(run.total_net)})
    commit(db); return row_dict(run)


@router.get("/payroll-runs/{run_id}/export.csv")
def export_payroll(run_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> StreamingResponse:
    run = db.get(PayrollRun, run_id)
    if not run or run.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Payroll run not found")
    require_scope(principal, "payroll.export", run.branch_id)
    if run.status not in {"reviewed", "approved"}: raise HTTPException(status_code=409, detail="Payroll export is available after review")
    buffer = io.StringIO(); writer = csv.writer(buffer); writer.writerow(["Employee Number", "Employee Name", "Branch", "Regular Hours", "Overtime Hours", "Basic Pay", "Earnings", "Deductions", "Gross Pay", "Net Pay", "Warnings"])
    for line in db.scalars(select(PayrollLine).where(PayrollLine.run_id == run.id).order_by(PayrollLine.employee_id)).all():
        employee = db.get(Employee, line.employee_id); branch = db.get(Branch, line.branch_id)
        writer.writerow([employee.employee_number if employee else "", f"{employee.first_name} {employee.last_name}" if employee else "", branch.name if branch else "", line.regular_hours, line.overtime_hours, line.basic_pay, line.earnings, line.deductions, line.gross_pay, line.net_pay, "; ".join(line.warnings or [])])
    content = buffer.getvalue().encode("utf-8-sig")
    return StreamingResponse(iter([content]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="buildtrack-payroll-{run.id}.csv"'})


@router.get("/policy")
def get_workforce_policy(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_company(principal, "payroll.view")
    row = db.scalar(select(CompanySetting).where(CompanySetting.company_id == principal.user.company_id, CompanySetting.key == "workforce_policy")); return row.value if row and isinstance(row.value, dict) else {}


@router.put("/policy")
def set_workforce_policy(payload: WorkforcePolicyInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_company(principal, "payroll.manage")
    row = db.scalar(select(CompanySetting).where(CompanySetting.company_id == principal.user.company_id, CompanySetting.key == "workforce_policy"))
    if not row: row = CompanySetting(company_id=principal.user.company_id, key="workforce_policy", value={}, description="Phase 3 workforce policy"); db.add(row)
    row.value = {key: json_value(value) for key, value in payload.model_dump().items()}; audit(db, principal, "workforce.policy.update", "company_setting", row.id, detail=row.value); commit(db); return row.value


@router.get("/audit")
def workforce_audit(limit: int = Query(default=250, ge=1, le=1000), db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    if not (principal.has_company_permission("people.manage") or principal.has_company_permission("payroll.view") or principal.has_company_permission("audit.view")): raise HTTPException(status_code=403, detail="Company-level workforce audit permission required")
    rows = db.scalars(select(WorkforceAuditEvent).where(WorkforceAuditEvent.company_id == principal.user.company_id).order_by(WorkforceAuditEvent.id.desc()).limit(limit)).all(); return [row_dict(r) for r in rows]
