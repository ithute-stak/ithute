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
    second = TestClient(app)
    branch_client = TestClient(app)
    try:
        yield admin, second, branch_client
    finally:
        admin.close(); second.close(); branch_client.close(); app.dependency_overrides.clear(); Base.metadata.drop_all(engine)


def initialise(admin: TestClient) -> dict:
    assert admin.post("/api/v1/foundation/bootstrap", json={"name":"Nthane Brothers","code":"NTHANE","head_office_name":"Head Office","head_office_code":"HO","head_office_district":"Maseru"}).status_code == 201
    assert admin.post("/api/v1/access/bootstrap-admin", json={"username":"admin","email":"admin@nthane.example","full_name":"System Administrator","password":ADMIN_PASSWORD}).status_code == 201
    assert admin.post("/api/v1/workforce/bootstrap").status_code == 200
    phase4 = admin.post("/api/v1/fleet/bootstrap")
    assert phase4.status_code == 200, phase4.text
    catalog = admin.get("/api/v1/fleet/catalog")
    assert catalog.status_code == 200, catalog.text
    return catalog.json()


def create_asset(admin: TestClient, branch_id: int, *, site_id: int | None = None, registration: str = "A123ABC", asset_type: str = "truck") -> dict:
    response = admin.post("/api/v1/fleet/assets", json={
        "branch_id": branch_id, "site_id": site_id, "asset_type": asset_type, "registration_number": registration,
        "make": "Mercedes-Benz", "model": "Actros", "manufacture_year": 2022, "fuel_type": "diesel",
        "ownership_type": "owned", "meter_type": "both", "current_odometer_km": "10000", "current_engine_hours": "750",
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_phase4_asset_fuel_inspection_maintenance_and_alerts(clients) -> None:
    admin, approver, _ = clients
    catalog = initialise(admin)
    head = catalog["branches"][0]
    asset = create_asset(admin, head["id"])
    assert asset["asset_number"].startswith("FLT-")

    backwards = admin.post(f"/api/v1/fleet/assets/{asset['id']}/meters", json={"odometer_km":"9999"})
    assert backwards.status_code == 422

    fuel = admin.post(f"/api/v1/fleet/assets/{asset['id']}/fuel", json={"fuel_type":"diesel","litres":"100","unit_cost":"22.50","odometer_km":"10150","engine_hours":"755","receipt_reference":"FUEL-001"})
    assert fuel.status_code == 201, fuel.text
    assert fuel.json()["total_cost"] == "2250.00"

    compliance = admin.post(f"/api/v1/fleet/assets/{asset['id']}/compliance", json={"compliance_type":"licence","reference_number":"LIC-001","issue_date":"2025-01-01","expiry_date":"2026-01-01","reminder_days":365,"cost":"500"})
    assert compliance.status_code == 201, compliance.text

    inspection = admin.post(f"/api/v1/fleet/assets/{asset['id']}/inspections", json={
        "inspection_date":"2026-08-24", "inspection_type":"pre_start", "odometer_km":"10160", "engine_hours":"756",
        "safe_to_operate":True, "checklist":{"brakes":False,"tyres":True}, "defects":[{"severity":"critical","description":"Brake pressure failure"}]
    })
    assert inspection.status_code == 201, inspection.text
    inspection_json = inspection.json()
    assert inspection_json["safe_to_operate"] is False
    defect = inspection_json["defects"][0]
    detail = admin.get(f"/api/v1/fleet/assets/{asset['id']}").json()
    assert detail["status"] == "out_of_service"
    assert detail["serviceability"] == "unserviceable"

    job = admin.post(f"/api/v1/fleet/assets/{asset['id']}/maintenance-jobs", json={"defect_id":defect["id"],"maintenance_type":"repair","description":"Repair braking system","vendor":"Fleet Workshop","labour_cost":"800","parts_cost":"1200","other_cost":"50"})
    assert job.status_code == 201, job.text
    job_id = job.json()["id"]
    self_approve = admin.post(f"/api/v1/fleet/maintenance-jobs/{job_id}/status", json={"status":"approved"})
    assert self_approve.status_code == 422

    role_catalog = admin.get("/api/v1/access/assignment-catalog").json()
    approver_role = next(role for role in role_catalog["roles"] if role["code"] == "APPROVER")
    created = admin.post("/api/v1/access/users", json={"username":"fleetapprover","email":"fleetapprover@nthane.example","full_name":"Fleet Approver","temporary_password":"Fleet!Approve2026X","must_change_password":False,"assignments":[{"role_id":approver_role["id"],"is_primary":True}]})
    assert created.status_code == 201, created.text
    assert approver.post("/api/v1/access/login", json={"username":"fleetapprover","password":"Fleet!Approve2026X"}).status_code == 200
    approved = approver.post(f"/api/v1/fleet/maintenance-jobs/{job_id}/status", json={"status":"approved"})
    assert approved.status_code == 200, approved.text
    assert admin.post(f"/api/v1/fleet/maintenance-jobs/{job_id}/status", json={"status":"in_progress"}).status_code == 200
    completed = admin.post(f"/api/v1/fleet/maintenance-jobs/{job_id}/status", json={"status":"completed","odometer_km":"10175","engine_hours":"758","labour_cost":"850","parts_cost":"1200","other_cost":"50","invoice_reference":"INV-001"})
    assert completed.status_code == 200, completed.text
    assert completed.json()["total_cost"] == "2100.00"
    restored = admin.get(f"/api/v1/fleet/assets/{asset['id']}").json()
    assert restored["status"] == "standby"
    assert restored["serviceability"] == "serviceable"

    alerts = admin.get("/api/v1/fleet/alerts").json()
    assert any(row["type"] == "compliance" and row["asset_id"] == asset["id"] for row in alerts)
    costs = admin.get("/api/v1/fleet/costs").json()
    row = next(item for item in costs if item["asset_id"] == asset["id"])
    assert row["fuel_cost"] == "2250.00" and row["maintenance_cost"] == "2100.00" and row["compliance_cost"] == "500.00"
    exported = admin.get("/api/v1/fleet/export.csv")
    assert exported.status_code == 200 and "FLT-" in exported.text and "A123ABC" in exported.text


def test_branch_fleet_scope_and_assignment_control(clients) -> None:
    admin, _, branch_client = clients
    initialise(admin)
    bb = admin.post("/api/v1/foundation/branches", json={"code":"BB","name":"Butha-Buthe Branch","district":"Butha-Buthe"}).json()
    lr = admin.post("/api/v1/foundation/branches", json={"code":"LR","name":"Leribe Branch","district":"Leribe"}).json()
    bb_asset = create_asset(admin, bb["id"], registration="BB100")
    create_asset(admin, lr["id"], registration="LR100")

    employee = admin.post("/api/v1/workforce/employees", json={"branch_id":bb["id"],"first_name":"Mpho","last_name":"Mokoena","job_title":"Driver","hire_date":"2026-01-01","pay_basis":"monthly","basic_rate":"5000","standard_hours_per_week":"45"})
    assert employee.status_code == 201, employee.text

    roles = admin.get("/api/v1/access/assignment-catalog").json()["roles"]
    branch_role = next(role for role in roles if role["code"] == "BRANCH_MANAGER")
    user = admin.post("/api/v1/access/users", json={"username":"bbfleet","email":"bbfleet@nthane.example","full_name":"BB Fleet Manager","temporary_password":"Branch!Fleet2026X","must_change_password":False,"assignments":[{"role_id":branch_role["id"],"branch_id":bb["id"],"is_primary":True}]})
    assert user.status_code == 201, user.text
    assert branch_client.post("/api/v1/access/login", json={"username":"bbfleet","password":"Branch!Fleet2026X"}).status_code == 200

    catalog = branch_client.get("/api/v1/fleet/catalog")
    assert catalog.status_code == 200, catalog.text
    assert {row["id"] for row in catalog.json()["branches"]} == {bb["id"]}
    visible = branch_client.get("/api/v1/fleet/assets").json()
    assert {row["registration_number"] for row in visible} == {"BB100"}

    assignment = branch_client.post(f"/api/v1/fleet/assets/{bb_asset['id']}/assignments", json={"employee_id":employee.json()["id"],"branch_id":bb["id"],"purpose":"Delivery work"})
    assert assignment.status_code == 201, assignment.text
    duplicate = branch_client.post(f"/api/v1/fleet/assets/{bb_asset['id']}/assignments", json={"employee_id":employee.json()["id"],"branch_id":bb["id"],"purpose":"Second assignment"})
    assert duplicate.status_code == 409

    denied = branch_client.get("/api/v1/fleet/costs")
    assert denied.status_code == 200  # branch managers have branch-scoped fleet.costs
    audit = branch_client.get("/api/v1/fleet/audit")
    assert audit.status_code == 200
