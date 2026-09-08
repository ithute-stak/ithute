from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.db.base import Base
from app.db.session import get_db
from app.main import app

ADMIN_PASSWORD = "Nthane!Secure2026X"


@pytest.fixture()
def clients(tmp_path: Path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    admin = TestClient(app)
    branch_client = TestClient(app)
    try:
        yield admin, branch_client
    finally:
        admin.close(); branch_client.close(); app.dependency_overrides.clear(); Base.metadata.drop_all(engine)


def initialise(admin: TestClient) -> None:
    phase1 = admin.post("/api/v1/foundation/bootstrap", json={"name": "Nthane Brothers", "code": "NTHANE", "head_office_name": "Head Office", "head_office_code": "HO", "head_office_district": "Maseru"})
    assert phase1.status_code == 201, phase1.text
    phase2 = admin.post("/api/v1/access/bootstrap-admin", json={"username": "admin", "email": "admin@nthane.example", "full_name": "System Administrator", "password": ADMIN_PASSWORD})
    assert phase2.status_code == 201, phase2.text
    phase3 = admin.post("/api/v1/workforce/bootstrap")
    assert phase3.status_code == 200, phase3.text
    assert phase3.json()["status"] == "operational"


def make_employee(client: TestClient, branch_id: int, *, first: str = "Mpho", last: str = "Mokoena", rate: str = "10000.00") -> dict:
    response = client.post("/api/v1/workforce/employees", json={
        "branch_id": branch_id,
        "first_name": first,
        "last_name": last,
        "job_title": "Site Administrator",
        "employment_type": "permanent",
        "employment_status": "active",
        "hire_date": "2026-01-01",
        "pay_basis": "monthly",
        "basic_rate": rate,
        "standard_hours_per_week": "45",
        "overtime_eligible": True,
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_phase3_bootstrap_employee_contract_and_sensitive_fields(clients) -> None:
    admin, _ = clients
    initialise(admin)
    status = admin.get("/api/v1/workforce/status")
    assert status.status_code == 200 and status.json()["initialized"] is True
    catalog = admin.get("/api/v1/workforce/catalog").json()
    permission_codes = set(catalog["permissions"])
    assert {"people.sensitive", "leave.approve", "timesheets.approve", "payroll.manage", "payroll.export"}.issubset(permission_codes)
    assert {role["code"] for role in admin.get("/api/v1/access/assignment-catalog").json()["roles"]} >= {"HR_MANAGER", "PAYROLL_OFFICER"}

    head_office = catalog["branches"][0]
    employee = admin.post("/api/v1/workforce/employees", json={
        "branch_id": head_office["id"], "first_name": "Lerato", "last_name": "Thabane", "job_title": "HR Officer",
        "hire_date": "2026-02-01", "pay_basis": "monthly", "basic_rate": "12500.00", "standard_hours_per_week": "45",
        "national_id": "999999999999", "bank_name": "Example Bank", "bank_account_number": "123456789"
    })
    assert employee.status_code == 201, employee.text
    employee_id = employee.json()["id"]
    assert employee.json()["employee_number"].startswith("EMP-")
    assert employee.json()["bank_account_number"] == "123456789"

    contract = admin.post(f"/api/v1/workforce/employees/{employee_id}/contracts", json={
        "start_date": "2026-02-01", "job_title": "HR Officer", "branch_id": head_office["id"], "pay_basis": "monthly", "basic_rate": "12500", "hours_per_week": "45", "status": "draft"
    })
    assert contract.status_code == 201, contract.text
    assert contract.json()["contract_number"].startswith("CTR-")
    missing_signature = admin.post(f"/api/v1/workforce/contracts/{contract.json()['id']}/status", json={"status": "active", "employee_signed": False, "company_signed": True})
    assert missing_signature.status_code == 422
    activate = admin.post(f"/api/v1/workforce/contracts/{contract.json()['id']}/status", json={"status": "active", "employee_signed": True, "company_signed": True})
    assert activate.status_code == 200, activate.text
    assert activate.json()["status"] == "active"


def test_branch_scoping_leave_attendance_and_timesheet_controls(clients) -> None:
    admin, branch_client = clients
    initialise(admin)
    bb = admin.post("/api/v1/foundation/branches", json={"code": "BB", "name": "Butha-Buthe Branch", "district": "Butha-Buthe"}).json()
    lr = admin.post("/api/v1/foundation/branches", json={"code": "LR", "name": "Leribe Branch", "district": "Leribe"}).json()
    bb_employee = make_employee(admin, bb["id"], first="Mpho", last="BB")
    make_employee(admin, lr["id"], first="Lineo", last="LR")

    role_catalog = admin.get("/api/v1/access/assignment-catalog").json()
    branch_role = next(role for role in role_catalog["roles"] if role["code"] == "BRANCH_MANAGER")
    user = admin.post("/api/v1/access/users", json={
        "username": "bbmanager", "email": "bbmanager@nthane.example", "full_name": "Butha-Buthe Manager", "temporary_password": "Branch!Secure2026X",
        "must_change_password": False,
        "assignments": [{"role_id": branch_role["id"], "branch_id": bb["id"], "is_primary": True}],
    })
    assert user.status_code == 201, user.text
    login = branch_client.post("/api/v1/access/login", json={"username": "bbmanager", "password": "Branch!Secure2026X"})
    assert login.status_code == 200, login.text

    visible = branch_client.get("/api/v1/workforce/employees")
    assert visible.status_code == 200
    assert [row["id"] for row in visible.json()] == [bb_employee["id"]]
    # Branch Manager deliberately does not receive payroll-sensitive visibility.
    assert visible.json()[0]["bank_account_number"] is None
    cross_branch = branch_client.post("/api/v1/workforce/employees", json={"branch_id": lr["id"], "first_name": "Bad", "last_name": "Scope", "job_title": "Worker", "hire_date": "2026-03-01", "pay_basis": "monthly", "basic_rate": "1000"})
    assert cross_branch.status_code == 403

    leave_type = next(item for item in admin.get("/api/v1/workforce/leave-types").json() if item["code"] == "ANNUAL")
    balance = branch_client.put("/api/v1/workforce/leave-balances", json={"employee_id": bb_employee["id"], "leave_type_id": leave_type["id"], "year": 2026, "opening_days": "10", "accrued_days": "0", "adjusted_days": "0"})
    assert balance.status_code == 200
    request = branch_client.post("/api/v1/workforce/leave-requests", json={"employee_id": bb_employee["id"], "leave_type_id": leave_type["id"], "start_date": "2026-04-06", "end_date": "2026-04-07", "days_requested": "2", "reason": "Annual leave"})
    assert request.status_code == 201
    self_approval = branch_client.post(f"/api/v1/workforce/leave-requests/{request.json()['id']}/decision", json={"decision": "approve"})
    assert self_approval.status_code == 422
    decision = admin.post(f"/api/v1/workforce/leave-requests/{request.json()['id']}/decision", json={"decision": "approve"})
    assert decision.status_code == 200 and decision.json()["status"] == "approved"
    updated_balance = branch_client.get(f"/api/v1/workforce/leave-balances?employee_id={bb_employee['id']}&year=2026").json()[0]
    assert updated_balance["available_days"] == "8.00"

    too_many_hours = branch_client.put("/api/v1/workforce/attendance", json={"employee_id": bb_employee["id"], "work_date": "2026-04-08", "status": "present", "regular_hours": "20", "overtime_hours": "8"})
    assert too_many_hours.status_code == 422
    attendance = branch_client.put("/api/v1/workforce/attendance", json={"employee_id": bb_employee["id"], "work_date": "2026-04-08", "status": "present", "regular_hours": "8", "overtime_hours": "1"})
    assert attendance.status_code == 200
    timesheet = branch_client.post("/api/v1/workforce/timesheets", json={"employee_id": bb_employee["id"], "work_date": "2026-04-08", "regular_hours": "8", "overtime_hours": "1", "task_description": "Site administration"})
    assert timesheet.status_code == 201
    submitted = branch_client.post(f"/api/v1/workforce/timesheets/{timesheet.json()['id']}/submit")
    assert submitted.status_code == 200 and submitted.json()["status"] == "submitted"
    self_timesheet = branch_client.post(f"/api/v1/workforce/timesheets/{timesheet.json()['id']}/decision", json={"decision": "approve"})
    assert self_timesheet.status_code == 422
    approved = admin.post(f"/api/v1/workforce/timesheets/{timesheet.json()['id']}/decision", json={"decision": "approve"})
    assert approved.status_code == 200 and approved.json()["status"] == "approved"


def test_payroll_calculation_review_approval_and_csv_export(clients) -> None:
    admin, _ = clients
    initialise(admin)
    catalog = admin.get("/api/v1/workforce/catalog").json()
    branch = catalog["branches"][0]
    employee = make_employee(admin, branch["id"], first="Payroll", last="Employee", rate="10000.00")

    earning = admin.post("/api/v1/workforce/pay-components", json={"code": "ALLOWANCE", "name": "Fixed Allowance", "component_type": "earning", "calculation_type": "fixed", "default_value": "1000"})
    deduction = admin.post("/api/v1/workforce/pay-components", json={"code": "DEDUCT", "name": "Manual Deduction", "component_type": "deduction", "calculation_type": "fixed", "default_value": "500"})
    assert earning.status_code == 201 and deduction.status_code == 201
    for component, value in ((earning.json(), "1000"), (deduction.json(), "500")):
        assigned = admin.put("/api/v1/workforce/employee-pay-components", json={"employee_id": employee["id"], "component_id": component["id"], "value": value, "effective_from": "2026-08-01"})
        assert assigned.status_code == 200, assigned.text

    period = admin.post("/api/v1/workforce/payroll-periods", json={"code": "2026-08", "name": "August 2026", "start_date": "2026-08-01", "end_date": "2026-08-31", "pay_date": "2026-08-31"})
    assert period.status_code == 201, period.text
    run = admin.post("/api/v1/workforce/payroll-runs", json={"period_id": period.json()["id"], "branch_id": branch["id"]})
    assert run.status_code == 201, run.text
    duplicate = admin.post("/api/v1/workforce/payroll-runs", json={"period_id": period.json()["id"], "branch_id": branch["id"]})
    assert duplicate.status_code == 409
    run_id = run.json()["id"]

    calculate = admin.post(f"/api/v1/workforce/payroll-runs/{run_id}/calculate")
    assert calculate.status_code == 200, calculate.text
    assert calculate.json()["status"] == "calculated"
    line = calculate.json()["lines"][0]
    assert line["basic_pay"] == "10000.00"
    assert line["earnings"] == "1000.00"
    assert line["deductions"] == "500.00"
    assert line["gross_pay"] == "11000.00"
    assert line["net_pay"] == "10500.00"

    premature = admin.post(f"/api/v1/workforce/payroll-runs/{run_id}/approve")
    assert premature.status_code == 409
    review = admin.post(f"/api/v1/workforce/payroll-runs/{run_id}/review")
    assert review.status_code == 200 and review.json()["status"] == "reviewed"
    export_reviewed = admin.get(f"/api/v1/workforce/payroll-runs/{run_id}/export.csv")
    assert export_reviewed.status_code == 200
    assert b"Employee Number" in export_reviewed.content
    approve = admin.post(f"/api/v1/workforce/payroll-runs/{run_id}/approve")
    assert approve.status_code == 200 and approve.json()["status"] == "approved"
    assert admin.post(f"/api/v1/workforce/payroll-runs/{run_id}/calculate").status_code == 409

    audit = admin.get("/api/v1/workforce/audit")
    assert audit.status_code == 200
    actions = {row["action"] for row in audit.json()}
    assert {"employee.create", "payroll.run.calculate", "payroll.run.review", "payroll.run.approve"}.issubset(actions)
