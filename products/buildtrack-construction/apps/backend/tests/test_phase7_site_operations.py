from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import ApprovalRequest, ApprovalWorkflow, Branch, Company, CostCentre, Project, ProjectReadinessSnapshot, ProjectSiteLink, Site

ADMIN_PASSWORD = "Nthane!Secure2026X"
BRANCH_PASSWORD = "Site!Branch2026X"
HQ_PASSWORD = "Site!HQ2026X"


@pytest.fixture()
def clients():
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
    admin, branch, hq = TestClient(app), TestClient(app), TestClient(app)
    try:
        yield admin, branch, hq, TestingSession
    finally:
        admin.close(); branch.close(); hq.close(); app.dependency_overrides.clear(); Base.metadata.drop_all(engine)


def bootstrap(admin: TestClient) -> None:
    assert admin.post("/api/v1/foundation/bootstrap", json={"name":"Nthane Brothers","code":"NTHANE","head_office_name":"Head Office","head_office_code":"HO","head_office_district":"Maseru"}).status_code == 201
    assert admin.post("/api/v1/access/bootstrap-admin", json={"username":"admin","email":"admin@nthane.example","full_name":"System Administrator","password":ADMIN_PASSWORD}).status_code == 201
    assert admin.post("/api/v1/projects/bootstrap").status_code == 200
    response = admin.post("/api/v1/site-ops/bootstrap")
    assert response.status_code == 200, response.text


def seed_ready_project(TestingSession) -> tuple[int, int, int]:
    db = TestingSession()
    try:
        company = db.scalar(select(Company))
        branch = db.scalar(select(Branch).where(Branch.company_id == company.id))
        site = Site(company_id=company.id, branch_id=branch.id, code="P7SITE", name="Phase 7 Test Site", site_type="project_site", district="Maseru", is_active=True)
        db.add(site); db.flush()
        centre = CostCentre(company_id=company.id, branch_id=branch.id, site_id=site.id, code="P7-CC", name="Phase 7 Project", cost_centre_type="project", is_active=True)
        db.add(centre); db.flush()
        project = Project(
            company_id=company.id, branch_id=branch.id, primary_site_id=site.id, cost_centre_id=centre.id,
            project_number="PRJ-P7-001", name="Phase 7 Integration Project", client_name="Test Client",
            contract_start_date=date.today()-timedelta(days=7), contract_completion_date=date.today()+timedelta(days=365),
            mobilisation_date=date.today()-timedelta(days=1), currency="LSL", contract_amount=Decimal("1000000"),
            baseline_budget=Decimal("800000"), contingency_budget=Decimal("50000"), status="ready", readiness_status="ready",
            created_by="System Administrator",
        )
        db.add(project); db.flush()
        db.add(ProjectSiteLink(company_id=company.id, project_id=project.id, site_id=site.id, site_role="work_site", is_primary=True, linked_by="System Administrator"))
        workflow = db.scalar(select(ApprovalWorkflow).where(ApprovalWorkflow.company_id == company.id, ApprovalWorkflow.code == "PROJECT_MOBILISATION"))
        approval = ApprovalRequest(company_id=company.id, workflow_id=workflow.id, branch_id=branch.id, site_id=site.id, entity_type="project_mobilisation", entity_id=str(project.id), reference="APR-P7-READY", title="Phase 7 readiness seed", status="approved", current_step_order=2, requested_by="System Administrator", completed_at=datetime.now(timezone.utc))
        db.add(approval); db.flush()
        db.add(ProjectReadinessSnapshot(company_id=company.id, project_id=project.id, version=1, approval_request_id=approval.id, snapshot={"phase":6,"ready":True}, created_by="System Administrator"))
        db.commit()
        return project.id, branch.id, site.id
    finally:
        db.close()


def create_approvers(admin: TestClient, branch_client: TestClient, hq_client: TestClient, branch_id: int) -> None:
    roles = admin.get("/api/v1/access/assignment-catalog").json()["roles"]
    branch_role = next(row for row in roles if row["code"] == "BRANCH_MANAGER")
    hq_role = next(row for row in roles if row["code"] == "HQ_EXECUTIVE")
    response = admin.post("/api/v1/access/users", json={"username":"sitebranch","email":"sitebranch@nthane.example","full_name":"Site Branch Approver","temporary_password":BRANCH_PASSWORD,"must_change_password":False,"assignments":[{"role_id":branch_role["id"],"branch_id":branch_id,"is_primary":True}]})
    assert response.status_code == 201, response.text
    response = admin.post("/api/v1/access/users", json={"username":"sitehq","email":"sitehq@nthane.example","full_name":"Site HQ Approver","temporary_password":HQ_PASSWORD,"must_change_password":False,"assignments":[{"role_id":hq_role["id"],"is_primary":True}]})
    assert response.status_code == 201, response.text
    assert branch_client.post("/api/v1/access/login", json={"username":"sitebranch","password":BRANCH_PASSWORD}).status_code == 200
    assert hq_client.post("/api/v1/access/login", json={"username":"sitehq","password":HQ_PASSWORD}).status_code == 200


def test_site_operations_daily_report_to_immutable_approval(clients) -> None:
    admin, branch_client, hq_client, TestingSession = clients
    bootstrap(admin)
    project_id, branch_id, _ = seed_ready_project(TestingSession)
    create_approvers(admin, branch_client, hq_client, branch_id)

    activated = admin.post(f"/api/v1/site-ops/activations/{project_id}", json={"notes":"Controlled handoff from Phase 6"})
    assert activated.status_code == 201, activated.text
    activation_id = activated.json()["id"]

    created = admin.post(f"/api/v1/site-ops/activations/{activation_id}/reports", json={"report_date":date.today().isoformat(),"shift":"day","weather_summary":"Clear","rain_hours":"0","work_summary":"Earthworks and drainage","planned_work":"Continue formation","safety_summary":"Toolbox talk completed"})
    assert created.status_code == 201, created.text
    report_id = created.json()["id"]

    empty_submit = admin.post(f"/api/v1/site-ops/reports/{report_id}/submit")
    assert empty_submit.status_code == 409

    serious_without_action = admin.post(f"/api/v1/site-ops/activations/{activation_id}/incidents", json={"daily_report_id":report_id,"incident_type":"safety","occurred_at":datetime.now(timezone.utc).isoformat(),"severity":"critical","description":"Test critical incident","lost_time":False,"status":"open"})
    assert serious_without_action.status_code == 422

    labour = admin.post(f"/api/v1/site-ops/reports/{report_id}/labour", json={"crew_name":"Earthworks Crew","worker_count":5,"regular_hours":"8","overtime_hours":"1","activity":"Formation trimming","work_area":"Chainage 0+000 - 0+500"})
    assert labour.status_code == 201, labour.text

    waste_without_reason = admin.post(f"/api/v1/site-ops/reports/{report_id}/materials", json={"movement_type":"waste","description":"Concrete","unit":"m3","quantity":"1","unit_cost":"100"})
    assert waste_without_reason.status_code == 422
    material = admin.post(f"/api/v1/site-ops/reports/{report_id}/materials", json={"movement_type":"received","description":"Cement","unit":"bag","quantity":"2","unit_cost":"50","source_reference":"DN-001"})
    assert material.status_code == 201, material.text
    assert material.json()["total_cost"] == "100.00"

    quality_without_action = admin.post(f"/api/v1/site-ops/activations/{activation_id}/quality", json={"daily_report_id":report_id,"check_type":"inspection","work_item":"Formation level","inspected_at":datetime.now(timezone.utc).isoformat(),"result":"fail","status":"action_required"})
    assert quality_without_action.status_code == 422
    quality = admin.post(f"/api/v1/site-ops/activations/{activation_id}/quality", json={"daily_report_id":report_id,"check_type":"inspection","work_item":"Formation level","inspected_at":datetime.now(timezone.utc).isoformat(),"result":"fail","corrective_action":"Regrade and recompact","status":"action_required"})
    assert quality.status_code == 201, quality.text

    submitted = admin.post(f"/api/v1/site-ops/reports/{report_id}/submit")
    assert submitted.status_code == 200, submitted.text
    request_id = submitted.json()["id"]

    first = branch_client.post(f"/api/v1/site-ops/approvals/{request_id}/decision", json={"decision":"approve","comment":"Branch reviewed"})
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "pending"
    second = hq_client.post(f"/api/v1/site-ops/approvals/{request_id}/decision", json={"decision":"approve","comment":"HQ approved"})
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "approved"

    detail = admin.get(f"/api/v1/site-ops/reports/{report_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "approved"
    assert body["approved_snapshot"]["totals"]["workers"] == 5
    assert body["approved_snapshot"]["totals"]["material_cost"] == "100.00"

    locked = admin.post(f"/api/v1/site-ops/reports/{report_id}/labour", json={"crew_name":"Late Crew","worker_count":1,"regular_hours":"1","overtime_hours":"0","activity":"Late edit"})
    assert locked.status_code == 409

    exported = admin.get("/api/v1/site-ops/exports/daily-reports.csv")
    assert exported.status_code == 200
    assert "Earthworks and drainage" in exported.text and "100.00" in exported.text
