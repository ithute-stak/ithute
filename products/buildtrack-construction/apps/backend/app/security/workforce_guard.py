from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import CompanySetting, EmploymentContract, PayrollPeriod, PayrollRun, Permission, Role, RolePermission
from app.security.access import Principal, build_principal, current_principal


ROLE_PERMISSION_REQUIREMENTS: dict[str, set[str]] = {
    "SYSTEM_ADMIN": {
        "people.view", "people.manage", "people.approve", "people.export", "people.sensitive",
        "leave.view", "leave.manage", "leave.approve",
        "attendance.view", "attendance.manage", "attendance.approve",
        "timesheets.view", "timesheets.manage", "timesheets.approve",
        "payroll.view", "payroll.manage", "payroll.approve", "payroll.export",
    },
    "HQ_EXECUTIVE": {
        "people.view", "people.approve", "people.export",
        "leave.view", "leave.approve", "attendance.view", "attendance.approve",
        "timesheets.view", "timesheets.approve", "payroll.view", "payroll.approve", "payroll.export",
    },
    "BRANCH_MANAGER": {
        "people.view", "people.manage", "leave.view", "leave.manage", "leave.approve",
        "attendance.view", "attendance.manage", "attendance.approve",
        "timesheets.view", "timesheets.manage", "timesheets.approve",
    },
    "SITE_MANAGER": {"people.view", "leave.view", "attendance.view", "attendance.manage", "timesheets.view", "timesheets.manage", "timesheets.approve"},
    "APPROVER": {"people.approve", "leave.approve", "attendance.approve", "timesheets.approve", "payroll.approve"},
    "AUDITOR": {"people.view", "people.export", "leave.view", "attendance.view", "timesheets.view", "payroll.view", "payroll.export"},
    "HR_MANAGER": {
        "people.view", "people.manage", "people.approve", "people.export", "people.sensitive",
        "leave.view", "leave.manage", "leave.approve",
        "attendance.view", "attendance.manage", "attendance.approve",
        "timesheets.view", "timesheets.manage", "timesheets.approve", "payroll.view",
    },
    "PAYROLL_OFFICER": {"people.view", "people.sensitive", "attendance.view", "timesheets.view", "payroll.view", "payroll.manage", "payroll.export"},
}


async def reconcile_workforce_access(request: Request, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> Principal:
    # Phase 3 bootstrap creates payroll.manage. Before that there is nothing to reconcile.
    if not db.scalar(select(Permission.id).where(Permission.code == "payroll.manage")):
        return principal

    company_id = principal.user.company_id
    permissions = {row.code: row for row in db.scalars(select(Permission)).all()}
    roles = {row.code: row for row in db.scalars(select(Role).where(Role.company_id == company_id)).all()}
    changed = False

    for role_code, required_codes in ROLE_PERMISSION_REQUIREMENTS.items():
        role = roles.get(role_code)
        if not role:
            continue
        existing = set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id == role.id)).all())
        for code in required_codes:
            permission = permissions.get(code)
            if permission and permission.id not in existing:
                db.add(RolePermission(role_id=role.id, permission_id=permission.id))
                existing.add(permission.id)
                changed = True

    # Branch operational managers do not receive payroll/bank-sensitive visibility by default.
    branch_manager = roles.get("BRANCH_MANAGER")
    payroll_view = permissions.get("payroll.view")
    sensitive = permissions.get("people.sensitive")
    if branch_manager:
        remove_ids = {item.id for item in (payroll_view, sensitive) if item is not None}
        if remove_ids:
            matches = db.scalars(select(RolePermission).where(RolePermission.role_id == branch_manager.id, RolePermission.permission_id.in_(remove_ids))).all()
            for match in matches:
                db.delete(match)
                changed = True

    path = request.url.path
    method = request.method.upper()
    body: dict = {}
    if method in {"POST", "PUT", "PATCH"}:
        try:
            payload = await request.json()
            body = payload if isinstance(payload, dict) else {}
        except Exception:
            body = {}

    # Prevent impossible 24+ hour attendance/timesheet records at the API boundary.
    if method in {"POST", "PUT"} and (path.endswith("/workforce/attendance") or path.endswith("/workforce/timesheets")):
        regular = float(body.get("regular_hours") or 0)
        overtime = float(body.get("overtime_hours") or 0)
        if regular + overtime > 24:
            raise HTTPException(status_code=422, detail="Regular plus overtime hours cannot exceed 24 hours in one day")

    # A contract becomes active only after both signature confirmations and within the approver's target scope.
    if method == "POST" and "/workforce/contracts/" in path and path.endswith("/status") and body.get("status") == "active":
        try:
            contract_id = int(path.split("/contracts/", 1)[1].split("/", 1)[0])
        except (ValueError, IndexError):
            contract_id = 0
        contract = db.get(EmploymentContract, contract_id) if contract_id else None
        if contract and contract.company_id == company_id:
            if not principal.can("people.approve", branch_id=contract.branch_id, site_id=contract.site_id):
                raise HTTPException(status_code=403, detail="people.approve is required in the contract branch/site")
            employee_signed = bool(contract.signed_employee_at) or bool(body.get("employee_signed"))
            company_signed = bool(contract.signed_company_at) or bool(body.get("company_signed"))
            if not employee_signed or not company_signed:
                raise HTTPException(status_code=422, detail="Employee and company signature confirmations are required before activating a contract")

    # Honour the Phase 1 self-approval policy for leave and timesheet decisions.
    if method == "POST" and ("/leave-requests/" in path or "/timesheets/" in path) and path.endswith("/decision") and body.get("decision") == "approve":
        approval_setting = db.scalar(select(CompanySetting).where(CompanySetting.company_id == company_id, CompanySetting.key == "approval_control"))
        allow_self = bool(approval_setting.value.get("allow_self_approval")) if approval_setting and isinstance(approval_setting.value, dict) else False
        if not allow_self:
            from app.models import LeaveRequest, TimesheetEntry
            if "/leave-requests/" in path:
                try: entity_id = int(path.split("/leave-requests/", 1)[1].split("/", 1)[0])
                except (ValueError, IndexError): entity_id = 0
                entity = db.get(LeaveRequest, entity_id) if entity_id else None
                if entity and entity.requested_by == principal.user.full_name:
                    raise HTTPException(status_code=422, detail="Self-approval is disabled by company approval policy")
            else:
                try: entity_id = int(path.split("/timesheets/", 1)[1].split("/", 1)[0])
                except (ValueError, IndexError): entity_id = 0
                entity = db.get(TimesheetEntry, entity_id) if entity_id else None
                if entity and entity.created_by == principal.user.full_name:
                    raise HTTPException(status_code=422, detail="Self-approval is disabled by company approval policy")

    # PostgreSQL allows multiple NULL values in the branch column of the unique constraint;
    # explicitly protect consolidated payroll runs from duplication. Re-open a period that
    # was auto-closed by a branch approval when another branch run is being prepared.
    if method == "POST" and path.endswith("/workforce/payroll-runs") and body.get("period_id"):
        period_id = int(body["period_id"])
        branch_id = body.get("branch_id")
        existing_statement = select(PayrollRun).where(PayrollRun.company_id == company_id, PayrollRun.period_id == period_id)
        existing_statement = existing_statement.where(PayrollRun.branch_id.is_(None)) if branch_id is None else existing_statement.where(PayrollRun.branch_id == int(branch_id))
        if db.scalar(existing_statement):
            raise HTTPException(status_code=409, detail="A payroll run already exists for this period and branch scope")
        period = db.get(PayrollPeriod, period_id)
        if period and period.status == "closed" and branch_id is not None:
            consolidated_approved = db.scalar(select(PayrollRun.id).where(PayrollRun.company_id == company_id, PayrollRun.period_id == period_id, PayrollRun.branch_id.is_(None), PayrollRun.status == "approved"))
            if not consolidated_approved:
                period.status = "open"
                changed = True

    if changed:
        db.commit()
    # Rebuild so permissions reconciled in this same request are immediately effective.
    refreshed = build_principal(db, principal.user, principal.session)
    request.state.principal = refreshed
    return refreshed
