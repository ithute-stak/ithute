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
def client(tmp_path: Path):
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
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        test_client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)


def initialise(client: TestClient) -> dict:
    foundation = client.post(
        "/api/v1/foundation/bootstrap",
        json={"name": "Nthane Brothers", "code": "NTHANE", "head_office_name": "Head Office", "head_office_code": "HO", "head_office_district": "Maseru"},
    )
    assert foundation.status_code == 201, foundation.text
    admin = client.post(
        "/api/v1/access/bootstrap-admin",
        json={"username": "admin", "email": "admin@nthane.example", "full_name": "System Administrator", "password": ADMIN_PASSWORD},
    )
    assert admin.status_code == 201, admin.text
    phase3 = client.post("/api/v1/workforce/bootstrap")
    assert phase3.status_code == 200, phase3.text
    return client.get("/api/v1/workforce/catalog").json()


def create_employee(client: TestClient, branch_id: int) -> dict:
    response = client.post(
        "/api/v1/workforce/employees",
        json={
            "branch_id": branch_id,
            "first_name": "Masechaba",
            "last_name": "Molefe",
            "job_title": "Site Clerk",
            "hire_date": "2026-01-15",
            "pay_basis": "monthly",
            "basic_rate": "7500.00",
            "standard_hours_per_week": "45",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_workforce_setup_leave_shift_export_and_lifecycle(client: TestClient) -> None:
    catalog = initialise(client)
    branch = catalog["branches"][0]
    employee = create_employee(client, branch["id"])
    employee_id = employee["id"]

    annual = next(item for item in catalog["leave_types"] if item["code"] == "ANNUAL")
    balance = client.put(
        "/api/v1/workforce/leave-balances",
        json={"employee_id": employee_id, "leave_type_id": annual["id"], "year": 2026, "opening_days": "12", "accrued_days": "3", "adjusted_days": "-1"},
    )
    assert balance.status_code == 200, balance.text
    assert balance.json()["available_days"] == "14.00"

    day_shift = next(item for item in catalog["shifts"] if item["code"] == "DAY")
    assignment = client.post(
        "/api/v1/workforce/shift-assignments",
        json={"employee_id": employee_id, "shift_id": day_shift["id"], "effective_from": "2026-01-15"},
    )
    assert assignment.status_code == 201, assignment.text
    listed = client.get(f"/api/v1/workforce/shift-assignments?employee_id={employee_id}")
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["shift_code"] == "DAY"

    exported = client.get("/api/v1/workforce/employees/export.csv")
    assert exported.status_code == 200, exported.text
    assert b"Employee Number" in exported.content
    assert employee["employee_number"].encode() in exported.content

    lifecycle = client.post(
        f"/api/v1/workforce/employees/{employee_id}/lifecycle",
        json={"employment_status": "terminated", "termination_date": "2026-08-24", "reason": "Contract completed", "revoke_linked_user_access": False},
    )
    assert lifecycle.status_code == 200, lifecycle.text
    assert lifecycle.json()["employee"]["employment_status"] == "terminated"
    assert lifecycle.json()["employee"]["termination_date"] == "2026-08-24"


def test_signed_contract_activation_and_payroll_period_close_guard(client: TestClient) -> None:
    catalog = initialise(client)
    branch = catalog["branches"][0]
    employee = create_employee(client, branch["id"])
    contract = client.post(
        f"/api/v1/workforce/employees/{employee['id']}/contracts",
        json={
            "start_date": "2026-01-15",
            "job_title": "Senior Site Clerk",
            "branch_id": branch["id"],
            "pay_basis": "monthly",
            "basic_rate": "8000.00",
            "hours_per_week": "45",
            "status": "draft",
        },
    )
    assert contract.status_code == 201, contract.text

    incomplete = client.post(
        f"/api/v1/workforce/contracts/{contract.json()['id']}/activate-signed",
        json={"employee_signed": True, "company_signed": False},
    )
    assert incomplete.status_code == 422
    activated = client.post(
        f"/api/v1/workforce/contracts/{contract.json()['id']}/activate-signed",
        json={"employee_signed": True, "company_signed": True},
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "active"

    period = client.post(
        "/api/v1/workforce/payroll-periods",
        json={"code": "2026-08", "name": "August 2026", "start_date": "2026-08-01", "end_date": "2026-08-31", "pay_date": "2026-08-31"},
    )
    assert period.status_code == 201, period.text
    close_without_run = client.post(f"/api/v1/workforce/payroll-periods/{period.json()['id']}/close-reviewed")
    assert close_without_run.status_code == 422
