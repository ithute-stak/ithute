from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
APPROVER_PASSWORD = "Tender!Approve2026X"
EXEC_PASSWORD = "Tender!Executive2026X"


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
    admin = TestClient(app); approver = TestClient(app); executive = TestClient(app); branch_user = TestClient(app)
    try:
        yield admin, approver, executive, branch_user
    finally:
        admin.close(); approver.close(); executive.close(); branch_user.close(); app.dependency_overrides.clear(); Base.metadata.drop_all(engine)


def bootstrap(admin: TestClient) -> dict:
    assert admin.post("/api/v1/foundation/bootstrap", json={"name":"Nthane Brothers","code":"NTHANE","head_office_name":"Head Office","head_office_code":"HO","head_office_district":"Maseru"}).status_code == 201
    assert admin.post("/api/v1/access/bootstrap-admin", json={"username":"admin","email":"admin@nthane.example","full_name":"System Administrator","password":ADMIN_PASSWORD}).status_code == 201
    assert admin.post("/api/v1/workforce/bootstrap").status_code == 200
    response = admin.post("/api/v1/tenders/bootstrap")
    assert response.status_code == 200, response.text
    catalog = admin.get("/api/v1/tenders/catalog")
    assert catalog.status_code == 200, catalog.text
    return catalog.json()


def create_approval_users(admin: TestClient, approver: TestClient, executive: TestClient) -> None:
    roles = admin.get("/api/v1/access/assignment-catalog").json()["roles"]
    approver_role = next(role for role in roles if role["code"] == "APPROVER")
    executive_role = next(role for role in roles if role["code"] == "HQ_EXECUTIVE")
    response = admin.post("/api/v1/access/users", json={"username":"tenderapprover","email":"tenderapprover@nthane.example","full_name":"Tender Approver","temporary_password":APPROVER_PASSWORD,"must_change_password":False,"assignments":[{"role_id":approver_role["id"],"is_primary":True}]})
    assert response.status_code == 201, response.text
    response = admin.post("/api/v1/access/users", json={"username":"tenderexec","email":"tenderexec@nthane.example","full_name":"Tender Executive","temporary_password":EXEC_PASSWORD,"must_change_password":False,"assignments":[{"role_id":executive_role["id"],"is_primary":True}]})
    assert response.status_code == 201, response.text
    assert approver.post("/api/v1/access/login", json={"username":"tenderapprover","password":APPROVER_PASSWORD}).status_code == 200
    assert executive.post("/api/v1/access/login", json={"username":"tenderexec","password":EXEC_PASSWORD}).status_code == 200


def create_tender(admin: TestClient, branch_id: int, reference: str = "MOPW-001") -> dict:
    now = datetime.now(timezone.utc)
    response = admin.post("/api/v1/tenders", json={
        "branch_id": branch_id, "external_reference": reference, "title": "Construction of district access road",
        "client_name": "Ministry of Public Works", "procurement_method": "open_tender", "category": "roads", "location": "Maseru",
        "issue_date": now.date().isoformat(), "site_visit_required": True, "site_visit_date": (now + timedelta(days=2)).isoformat(),
        "clarification_deadline": (now + timedelta(days=7)).isoformat(), "submission_deadline": (now + timedelta(days=30)).isoformat(),
        "validity_days": 90, "estimated_contract_value": "1000000.00", "win_probability": 40, "priority": "high",
    })
    assert response.status_code == 201, response.text
    return response.json()


def approve_two_steps(request_id: int, approver: TestClient, executive: TestClient) -> None:
    first = approver.post(f"/api/v1/tenders/approvals/{request_id}/decision", json={"decision":"approve","comment":"Reviewed"})
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "pending"
    second = executive.post(f"/api/v1/tenders/approvals/{request_id}/decision", json={"decision":"approve","comment":"Approved by HQ"})
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "approved"


def test_full_tender_lifecycle_to_phase6_handoff(clients) -> None:
    admin, approver, executive, _ = clients
    catalog = bootstrap(admin); create_approval_users(admin, approver, executive)
    tender = create_tender(admin, catalog["branches"][0]["id"]); tender_id = tender["id"]
    assert tender["tender_number"].startswith("TND-")

    detail = admin.get(f"/api/v1/tenders/{tender_id}").json()
    assert len(detail["checklist"]) == 10
    optional_security = next(item for item in detail["checklist"] if "security" in item["name"].lower())
    assert optional_security["required"] is False
    assert admin.post(f"/api/v1/tenders/{tender_id}/estimate-items", json={"description":"Earthworks","quantity":"10","unit":"m3","material_unit_cost":"5","labour_unit_cost":"3","markup_pct":"25"}).status_code == 409

    decision = admin.post(f"/api/v1/tenders/{tender_id}/bid-decision", json={"decision":"bid","reason":"Capacity and experience fit"})
    assert decision.status_code == 200, decision.text
    priced = admin.post(f"/api/v1/tenders/{tender_id}/estimate-items", json={"description":"Earthworks","quantity":"10","unit":"m3","material_unit_cost":"5","labour_unit_cost":"3","markup_pct":"25"})
    assert priced.status_code == 201, priced.text
    assert priced.json()["direct_total"] == "80.00" and priced.json()["selling_total"] == "100.00"
    detail = admin.get(f"/api/v1/tenders/{tender_id}").json()
    assert detail["direct_cost_total"] == "80.00" and detail["tender_price"] == "100.00"
    assert detail["gross_margin"] == "20.00" and detail["gross_margin_pct"] == "20.000"
    assert admin.post(f"/api/v1/tenders/{tender_id}/submission-approval").status_code == 409

    for item in detail["checklist"]:
        payload = {"category":item["category"],"name":item["name"],"required":item["required"],"owner_employee_id":item["owner_employee_id"],"document_id":item["document_id"],"due_date":item["due_date"],"status":"ready" if item["required"] else "not_applicable","notes":item["notes"]}
        response = admin.put(f"/api/v1/tenders/checklist/{item['id']}", json=payload)
        assert response.status_code == 200, response.text

    high_margin_policy = admin.put("/api/v1/tenders/policy/current", json={"deadline_warning_days":7,"minimum_margin_pct":25})
    assert high_margin_policy.status_code == 200, high_margin_policy.text
    margin_block = admin.post(f"/api/v1/tenders/{tender_id}/commercial-approval")
    assert margin_block.status_code == 409
    assert admin.put("/api/v1/tenders/policy/current", json={"deadline_warning_days":7,"minimum_margin_pct":0}).status_code == 200

    commercial = admin.post(f"/api/v1/tenders/{tender_id}/commercial-approval")
    assert commercial.status_code == 200, commercial.text
    pricing_frozen = admin.post(f"/api/v1/tenders/{tender_id}/estimate-items", json={"description":"Late pricing change","quantity":"1","unit":"item","material_unit_cost":"1","markup_pct":"10"})
    assert pricing_frozen.status_code == 409
    assert admin.post(f"/api/v1/tenders/{tender_id}/bid-decision", json={"decision":"no_bid","reason":"Too late"}).status_code == 409
    self_approval = admin.post(f"/api/v1/tenders/approvals/{commercial.json()['id']}/decision", json={"decision":"approve"})
    assert self_approval.status_code in {403, 422}
    approve_two_steps(commercial.json()["id"], approver, executive)

    submission_approval = admin.post(f"/api/v1/tenders/{tender_id}/submission-approval")
    assert submission_approval.status_code == 200, submission_approval.text
    duplicate = admin.post(f"/api/v1/tenders/{tender_id}/submission-approval")
    assert duplicate.status_code == 200 and duplicate.json()["id"] == submission_approval.json()["id"]
    approve_two_steps(submission_approval.json()["id"], approver, executive)

    submitted = admin.post(f"/api/v1/tenders/{tender_id}/submit", json={"submission_method":"portal","submission_location":"Government eTender Portal","acknowledgement_reference":"ACK-001"})
    assert submitted.status_code == 201, submitted.text
    assert submitted.json()["version"] == 1 and submitted.json()["tender_price"] == "100.00"
    assert submitted.json()["approval_request_id"] == submission_approval.json()["id"]
    stale_resubmit = admin.post(f"/api/v1/tenders/{tender_id}/submit", json={"submission_method":"portal","submission_location":"Government eTender Portal","acknowledgement_reference":"ACK-002"})
    assert stale_resubmit.status_code == 409

    decision_date = (datetime.now(timezone.utc) + timedelta(days=45)).date().isoformat()
    awarded = admin.post(f"/api/v1/tenders/{tender_id}/outcome", json={"outcome":"awarded","decision_date":decision_date,"awarded_amount":"100.00"})
    assert awarded.status_code == 200, awarded.text
    handoff = admin.get(f"/api/v1/tenders/{tender_id}/mobilisation-handoff")
    assert handoff.status_code == 200, handoff.text
    assert handoff.json()["ready"] is True and handoff.json()["target_phase"] == 6
    assert handoff.json()["submission"]["approval_request_id"] == submission_approval.json()["id"]
    assert handoff.json()["commercial_totals"]["tender_price"] == "100.00"

    dashboard = admin.get("/api/v1/tenders/dashboard/summary")
    assert dashboard.status_code == 200 and dashboard.json()["awarded"] == 1
    exported = admin.get("/api/v1/tenders/exports/pipeline.csv")
    assert exported.status_code == 200 and tender["tender_number"] in exported.text and "Ministry of Public Works" in exported.text


def test_branch_tender_scope_isolation(clients) -> None:
    admin, _, _, branch_user = clients
    bootstrap(admin)
    bb = admin.post("/api/v1/foundation/branches", json={"code":"BB","name":"Butha-Buthe Branch","district":"Butha-Buthe"}).json()
    lr = admin.post("/api/v1/foundation/branches", json={"code":"LR","name":"Leribe Branch","district":"Leribe"}).json()
    create_tender(admin, bb["id"], "BB-001"); create_tender(admin, lr["id"], "LR-001")
    roles = admin.get("/api/v1/access/assignment-catalog").json()["roles"]
    branch_role = next(role for role in roles if role["code"] == "BRANCH_MANAGER")
    user = admin.post("/api/v1/access/users", json={"username":"bbtenders","email":"bbtenders@nthane.example","full_name":"BB Tender Manager","temporary_password":"Branch!Tender2026X","must_change_password":False,"assignments":[{"role_id":branch_role["id"],"branch_id":bb["id"],"is_primary":True}]})
    assert user.status_code == 201, user.text
    assert branch_user.post("/api/v1/access/login", json={"username":"bbtenders","password":"Branch!Tender2026X"}).status_code == 200
    catalog = branch_user.get("/api/v1/tenders/catalog")
    assert catalog.status_code == 200 and {row["id"] for row in catalog.json()["branches"]} == {bb["id"]}
    visible = branch_user.get("/api/v1/tenders")
    assert visible.status_code == 200 and {row["external_reference"] for row in visible.json()} == {"BB-001"}
