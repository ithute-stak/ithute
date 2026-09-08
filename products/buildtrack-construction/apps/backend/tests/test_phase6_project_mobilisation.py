from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Branch, CostCentre, Document, Employee, FleetAsset, Project, Site, Tender, TenderEstimateItem, TenderOutcome, TenderSubmission

ADMIN_PASSWORD = "Nthane!Secure2026X"
BRANCH_PASSWORD = "Project!Branch2026X"
EXEC_PASSWORD = "Project!Executive2026X"


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
    branch_approver = TestClient(app)
    executive = TestClient(app)
    scoped_user = TestClient(app)
    try:
        yield admin, branch_approver, executive, scoped_user, TestingSession
    finally:
        admin.close(); branch_approver.close(); executive.close(); scoped_user.close()
        app.dependency_overrides.clear(); Base.metadata.drop_all(engine)


def bootstrap(admin: TestClient) -> None:
    assert admin.post("/api/v1/foundation/bootstrap", json={"name":"Nthane Brothers","code":"NTHANE","head_office_name":"Head Office","head_office_code":"HO","head_office_district":"Maseru"}).status_code == 201
    assert admin.post("/api/v1/access/bootstrap-admin", json={"username":"admin","email":"admin@nthane.example","full_name":"System Administrator","password":ADMIN_PASSWORD}).status_code == 201
    response = admin.post("/api/v1/projects/bootstrap")
    assert response.status_code == 200, response.text


def seed_awarded_tender(SessionFactory, branch_id: int, ref: str = "MOPW-ROAD-001") -> dict[str, int]:
    now = datetime.now(timezone.utc)
    with SessionFactory() as db:
        branch = db.get(Branch, branch_id)
        company_id = branch.company_id
        manager = Employee(
            company_id=company_id, employee_number=f"EMP-{branch_id}-001", branch_id=branch_id,
            first_name="Mpho", last_name=f"Manager{branch_id}", job_title="Project Manager",
            hire_date=date.today() - timedelta(days=200), created_by="test",
        )
        db.add(manager); db.flush()
        documents = []
        for idx, title in enumerate(("Award Contract", "Tender Submission", "Priced BOQ", "Drawings and Specs", "Client HSE"), start=1):
            doc = Document(company_id=company_id, branch_id=branch_id, document_number=f"DOC-{branch_id}-{idx}", title=title, category="Project", status="active", confidentiality="internal", created_by="test")
            db.add(doc); documents.append(doc)
        db.flush()
        tender = Tender(
            company_id=company_id, branch_id=branch_id, tender_number=f"TND-{branch_id}-001", external_reference=ref,
            title=f"Construction Project {branch_id}", client_name="Ministry of Public Works", category="roads", location="Maseru",
            issue_date=date.today() - timedelta(days=60), submission_deadline=now - timedelta(days=30), currency="LSL",
            direct_cost_total=Decimal("80.00"), tender_price=Decimal("100.00"), gross_margin=Decimal("20.00"), gross_margin_pct=Decimal("20.000"),
            win_probability=100, priority="high", status="awarded", bid_decision="bid", lead_employee_id=manager.id, created_by="test",
        )
        db.add(tender); db.flush()
        estimate = TenderEstimateItem(
            company_id=company_id, tender_id=tender.id, item_code="EW-001", description="Earthworks", unit="m3", quantity=Decimal("10"),
            material_unit_cost=Decimal("5"), labour_unit_cost=Decimal("3"), plant_unit_cost=Decimal("0"), subcontract_unit_cost=Decimal("0"), other_unit_cost=Decimal("0"),
            direct_unit_cost=Decimal("8"), direct_total=Decimal("80"), markup_pct=Decimal("25"), selling_rate=Decimal("10"), selling_total=Decimal("100"), created_by="test",
        )
        db.add(estimate)
        submission = TenderSubmission(company_id=company_id, tender_id=tender.id, version=1, submission_method="portal", submitted_at=now - timedelta(days=30), submitted_by="test", acknowledgement_reference="ACK-001", acknowledgement_document_id=documents[1].id, tender_price=Decimal("100.00"))
        db.add(submission); db.flush()
        outcome = TenderOutcome(company_id=company_id, tender_id=tender.id, outcome="awarded", decision_date=date.today() - timedelta(days=5), awarded_amount=Decimal("100.00"), award_document_id=documents[0].id, recorded_by="test")
        db.add(outcome)
        asset = FleetAsset(company_id=company_id, branch_id=branch_id, asset_number=f"FLT-{branch_id}-001", asset_type="plant", make="Caterpillar", model="320", meter_type="engine_hours", status="active", serviceability="serviceable", created_by="test")
        db.add(asset); db.commit()
        return {"tender_id": tender.id, "manager_id": manager.id, "asset_id": asset.id, "doc1": documents[0].id, "doc2": documents[1].id, "doc3": documents[2].id, "doc4": documents[3].id, "doc5": documents[4].id}


def create_approval_users(admin: TestClient, branch_approver: TestClient, executive: TestClient, branch_id: int) -> None:
    roles = admin.get("/api/v1/access/assignment-catalog").json()["roles"]
    branch_role = next(role for role in roles if role["code"] == "BRANCH_MANAGER")
    exec_role = next(role for role in roles if role["code"] == "HQ_EXECUTIVE")
    first = admin.post("/api/v1/access/users", json={"username":"projectbranch","email":"projectbranch@nthane.example","full_name":"Project Branch Approver","temporary_password":BRANCH_PASSWORD,"must_change_password":False,"assignments":[{"role_id":branch_role["id"],"branch_id":branch_id,"is_primary":True}]})
    assert first.status_code == 201, first.text
    second = admin.post("/api/v1/access/users", json={"username":"projectexec","email":"projectexec@nthane.example","full_name":"Project Executive","temporary_password":EXEC_PASSWORD,"must_change_password":False,"assignments":[{"role_id":exec_role["id"],"is_primary":True}]})
    assert second.status_code == 201, second.text
    assert branch_approver.post("/api/v1/access/login", json={"username":"projectbranch","password":BRANCH_PASSWORD}).status_code == 200
    assert executive.post("/api/v1/access/login", json={"username":"projectexec","password":EXEC_PASSWORD}).status_code == 200


def approve_two_steps(request_id: int, branch_approver: TestClient, executive: TestClient) -> None:
    first = branch_approver.post(f"/api/v1/projects/approvals/{request_id}/decision", json={"decision":"approve","comment":"Branch checked"})
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "pending"
    second = executive.post(f"/api/v1/projects/approvals/{request_id}/decision", json={"decision":"approve","comment":"HQ approved"})
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "approved"


def convert(admin: TestClient, seed: dict[str, int]) -> dict:
    response = admin.post(f"/api/v1/projects/from-tender/{seed['tender_id']}", json={
        "site_name":"Road Project Site", "district":"Maseru", "site_location":"Maseru",
        "project_manager_employee_id":seed["manager_id"], "mobilisation_date":date.today().isoformat(),
        "contract_start_date":(date.today()+timedelta(days=5)).isoformat(), "contract_completion_date":(date.today()+timedelta(days=365)).isoformat(),
        "contract_reference":"CONTRACT-001", "project_type":"roads", "contingency_budget":"5.00", "contract_document_id":seed["doc1"],
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_full_phase6_mobilisation_to_phase7_handoff(clients) -> None:
    admin, branch_approver, executive, _, SessionFactory = clients
    bootstrap(admin)
    branch_id = admin.get("/api/v1/foundation/branches").json()[0]["id"]
    seed = seed_awarded_tender(SessionFactory, branch_id)
    create_approval_users(admin, branch_approver, executive, branch_id)
    project = convert(admin, seed)
    project_id = project["id"]
    assert project["project_number"].startswith("PRJ-")

    detail = admin.get(f"/api/v1/projects/{project_id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["source_tender"]["id"] == seed["tender_id"]
    assert len(body["sites"]) == 1 and body["sites"][0]["is_primary"] is True
    assert body["budgets"][0]["version"] == 1
    assert body["budgets"][0]["total_amount"] == "80.00"
    assert {line["cost_type"] for line in body["budgets"][0]["lines"]} == {"material", "labour"}

    duplicate = admin.post(f"/api/v1/projects/from-tender/{seed['tender_id']}", json={
        "contract_start_date":(date.today()+timedelta(days=5)).isoformat(), "contract_completion_date":(date.today()+timedelta(days=365)).isoformat(), "mobilisation_date":date.today().isoformat()
    })
    assert duplicate.status_code == 409

    budget_request = admin.post(f"/api/v1/projects/{project_id}/budget/submit")
    assert budget_request.status_code == 200, budget_request.text
    self_approval = admin.post(f"/api/v1/projects/approvals/{budget_request.json()['id']}/decision", json={"decision":"approve"})
    assert self_approval.status_code in {403, 422}
    approve_two_steps(budget_request.json()["id"], branch_approver, executive)
    detail = admin.get(f"/api/v1/projects/{project_id}").json()
    assert detail["baseline_budget"] == "80.00"
    assert detail["budgets"][0]["status"] == "approved"

    blocked = admin.post(f"/api/v1/projects/{project_id}/readiness-approval")
    assert blocked.status_code == 409
    assert "blockers" in blocked.json()["detail"]

    milestone = admin.post(f"/api/v1/projects/{project_id}/milestones", json={
        "code":"M1", "name":"Contract works", "planned_start":(date.today()+timedelta(days=5)).isoformat(),
        "planned_finish":(date.today()+timedelta(days=365)).isoformat(), "weight_pct":"100", "predecessor_id":None,
    })
    assert milestone.status_code == 201, milestone.text

    detail = admin.get(f"/api/v1/projects/{project_id}").json()
    for item in detail["mobilisation_items"]:
        response = admin.put(f"/api/v1/projects/mobilisation-items/{item['id']}", json={"status":"ready","owner_employee_id":seed["manager_id"],"due_date":date.today().isoformat(),"document_id":None,"notes":"Completed"})
        assert response.status_code == 200, response.text
    docs = [seed["doc1"], seed["doc2"], seed["doc3"], seed["doc4"], seed["doc5"]]
    for item, doc_id in zip(detail["handover_documents"], docs, strict=True):
        response = admin.put(f"/api/v1/projects/handover-documents/{item['id']}", json={"document_id":doc_id,"status":"verified","notes":"Verified"})
        assert response.status_code == 200, response.text

    risk = admin.post(f"/api/v1/projects/{project_id}/risks", json={"category":"delivery","title":"Critical access risk","likelihood":5,"impact":5,"owner_employee_id":seed["manager_id"],"mitigation":"Alternative access plan","status":"open"})
    assert risk.status_code == 201, risk.text
    assert risk.json()["rating"] == 25
    state = admin.get(f"/api/v1/projects/{project_id}/readiness").json()
    assert state["ready"] is False and state["critical_open_risks"] == 1
    mitigated = admin.put(f"/api/v1/projects/risks/{risk.json()['id']}", json={"category":"delivery","title":"Critical access risk","likelihood":5,"impact":5,"owner_employee_id":seed["manager_id"],"mitigation":"Alternative access secured","status":"mitigated"})
    assert mitigated.status_code == 200, mitigated.text

    site_id = admin.get(f"/api/v1/projects/{project_id}").json()["primary_site_id"]
    allocation = admin.post(f"/api/v1/projects/{project_id}/assets", json={"asset_id":seed["asset_id"],"site_id":site_id,"planned_from":date.today().isoformat(),"planned_to":(date.today()+timedelta(days=30)).isoformat(),"purpose":"Earthworks"})
    assert allocation.status_code == 201, allocation.text
    overlap = admin.post(f"/api/v1/projects/{project_id}/assets", json={"asset_id":seed["asset_id"],"site_id":site_id,"planned_from":date.today().isoformat(),"planned_to":(date.today()+timedelta(days=10)).isoformat()})
    assert overlap.status_code == 409
    state = admin.get(f"/api/v1/projects/{project_id}/readiness").json()
    assert state["planned_assets_unconfirmed"] == 1
    confirmed = admin.post(f"/api/v1/projects/assets/{allocation.json()['id']}/status", json={"status":"confirmed"})
    assert confirmed.status_code == 200, confirmed.text

    state = admin.get(f"/api/v1/projects/{project_id}/readiness")
    assert state.status_code == 200, state.text
    assert state.json()["ready"] is True, state.json()
    ready_request = admin.post(f"/api/v1/projects/{project_id}/readiness-approval")
    assert ready_request.status_code == 200, ready_request.text
    approve_two_steps(ready_request.json()["id"], branch_approver, executive)

    final = admin.get(f"/api/v1/projects/{project_id}").json()
    assert final["status"] == "ready" and final["readiness_status"] == "ready"
    assert final["readiness_snapshot"] is not None
    handoff = admin.get(f"/api/v1/projects/{project_id}/site-operations-handoff")
    assert handoff.status_code == 200, handoff.text
    assert handoff.json()["ready"] is True and handoff.json()["target_phase"] == 7
    assert handoff.json()["snapshot"]["project"]["status"] == "ready"
    assert handoff.json()["snapshot"]["budget"]["baseline"]["status"] == "approved"

    frozen = admin.post(f"/api/v1/projects/{project_id}/milestones", json={"name":"Late change","planned_start":date.today().isoformat(),"planned_finish":(date.today()+timedelta(days=1)).isoformat(),"weight_pct":"0"})
    assert frozen.status_code == 409
    exported = admin.get("/api/v1/projects/exports/projects.csv")
    assert exported.status_code == 200 and project["project_number"] in exported.text


def test_phase6_branch_scope_isolation(clients) -> None:
    admin, _, _, scoped_user, SessionFactory = clients
    bootstrap(admin)
    ho = admin.get("/api/v1/foundation/branches").json()[0]
    other = admin.post("/api/v1/foundation/branches", json={"code":"BB","name":"Butha-Buthe Branch","district":"Butha-Buthe"}).json()
    first_seed = seed_awarded_tender(SessionFactory, ho["id"], "HO-PROJ")
    second_seed = seed_awarded_tender(SessionFactory, other["id"], "BB-PROJ")
    first_project = convert(admin, first_seed)
    second_project = convert(admin, second_seed)

    roles = admin.get("/api/v1/access/assignment-catalog").json()["roles"]
    branch_role = next(role for role in roles if role["code"] == "BRANCH_MANAGER")
    response = admin.post("/api/v1/access/users", json={"username":"hoprojects","email":"hoprojects@nthane.example","full_name":"HO Project User","temporary_password":"Branch!Projects2026X","must_change_password":False,"assignments":[{"role_id":branch_role["id"],"branch_id":ho["id"],"is_primary":True}]})
    assert response.status_code == 201, response.text
    assert scoped_user.post("/api/v1/access/login", json={"username":"hoprojects","password":"Branch!Projects2026X"}).status_code == 200
    visible = scoped_user.get("/api/v1/projects")
    assert visible.status_code == 200
    assert {row["id"] for row in visible.json()} == {first_project["id"]}
    denied = scoped_user.get(f"/api/v1/projects/{second_project['id']}")
    assert denied.status_code == 403
    catalog = scoped_user.get("/api/v1/projects/catalog")
    assert catalog.status_code == 200
    assert {row["id"] for row in catalog.json()["branches"]} == {ho["id"]}

    with SessionFactory() as db:
        project = db.get(Project, first_project["id"])
        assert project is not None
        site = db.get(Site, project.primary_site_id)
        cost = db.get(CostCentre, project.cost_centre_id)
        assert site.branch_id == ho["id"] and cost.branch_id == ho["id"] and cost.site_id == site.id
