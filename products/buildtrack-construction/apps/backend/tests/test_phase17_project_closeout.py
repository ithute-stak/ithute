from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_phase17_closeout_contract_is_wired() -> None:
    migration = (ROOT / "apps/backend/alembic/versions/0018_phase17_closeout.py").read_text(encoding="utf-8")
    api = (ROOT / "apps/backend/app/api/v1/closeout.py").read_text(encoding="utf-8")
    page = (ROOT / "apps/frontend/app/closeout/page.tsx").read_text(encoding="utf-8")
    assert 'down_revision = "0017_phase16_rollout"' in migration
    assert len("0018_phase17_closeout") <= 32
    for table in ("project_closeouts", "closeout_checklist_items", "closeout_defects", "closeout_audit_events"):
        assert f'"{table}"' in migration
    for safeguard in (
        "High or critical defects must be closed before closeout approval",
        "Practical-completion handover controls are frozen after closeout approval",
        "Retention release and final archive controls must be completed or formally waived before final project closure",
        "The configured defects-liability period has not ended",
    ):
        assert safeguard in api
    assert "Project Closeout" in page and "Defects-liability register" in page


def test_controlled_project_closeout_to_final_closure() -> None:
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app import models  # noqa: F401
    from app.db.base import Base
    from app.db.session import get_db
    from app.main import app
    from app.models import Branch, Company, CompanySetting, CostCentre, Document, Project, ProjectCloseout, Site

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
        assert admin.post("/api/v1/foundation/bootstrap", json={"name": "Nthane Brothers", "code": "NTHANE", "head_office_name": "Head Office", "head_office_code": "HO", "head_office_district": "Maseru"}).status_code == 201
        assert admin.post("/api/v1/access/bootstrap-admin", json={"username": "phase17admin", "email": "phase17admin@nthane.example", "full_name": "Phase 17 Administrator", "password": "Nthane!Secure2026X"}).status_code == 201
        assert admin.post("/api/v1/projects/bootstrap").status_code == 200
        assert admin.post("/api/v1/closeout/bootstrap").status_code == 200

        db = TestingSession()
        try:
            company = db.scalar(select(Company))
            branch_row = db.scalar(select(Branch).where(Branch.company_id == company.id))
            site = Site(company_id=company.id, branch_id=branch_row.id, code="P17SITE", name="Phase 17 Site", site_type="project_site", district="Maseru", is_active=True)
            db.add(site)
            db.flush()
            centre = CostCentre(company_id=company.id, branch_id=branch_row.id, site_id=site.id, code="P17-CC", name="Phase 17 Cost Centre", cost_centre_type="project", is_active=True)
            db.add(centre)
            db.flush()
            project = Project(company_id=company.id, branch_id=branch_row.id, primary_site_id=site.id, cost_centre_id=centre.id, project_number="PRJ-P17-001", name="Phase 17 Test Project", client_name="Test Client", contract_start_date=date.today() - timedelta(days=120), contract_completion_date=date.today(), mobilisation_date=date.today() - timedelta(days=120), currency="LSL", contract_amount=Decimal("100000"), baseline_budget=Decimal("80000"), contingency_budget=Decimal("5000"), status="active", readiness_status="ready", created_by="Phase 17 Administrator")
            db.add(project)
            db.flush()
            documents: dict[str, int] = {}
            for key in ("practical", "client", "final", "retention", "asbuilt", "manual", "warranty", "demobilisation", "archive", "defect"):
                document = Document(company_id=company.id, branch_id=branch_row.id, site_id=site.id, document_number=f"P17-{key.upper()}", title=f"Phase 17 {key} evidence", category="project_closeout", status="active", confidentiality="internal", created_by="Phase 17 Administrator")
                db.add(document)
                db.flush()
                documents[key] = document.id
            db.commit()
            project_id, branch_id, company_id = project.id, branch_row.id, company.id
        finally:
            db.close()

        roles = admin.get("/api/v1/access/assignment-catalog").json()["roles"]
        branch_role = next(row for row in roles if row["code"] == "BRANCH_MANAGER")
        hq_role = next(row for row in roles if row["code"] == "HQ_EXECUTIVE")
        assert admin.post("/api/v1/access/users", json={"username": "phase17branch", "email": "phase17branch@nthane.example", "full_name": "Phase 17 Branch Reviewer", "temporary_password": "Phase17!Branch", "must_change_password": False, "assignments": [{"role_id": branch_role["id"], "branch_id": branch_id, "is_primary": True}]}).status_code == 201
        assert admin.post("/api/v1/access/users", json={"username": "phase17hq", "email": "phase17hq@nthane.example", "full_name": "Phase 17 HQ Reviewer", "temporary_password": "Phase17!HQ2026", "must_change_password": False, "assignments": [{"role_id": hq_role["id"], "is_primary": True}]}).status_code == 201
        assert branch.post("/api/v1/access/login", json={"username": "phase17branch", "password": "Phase17!Branch"}).status_code == 200
        assert hq.post("/api/v1/access/login", json={"username": "phase17hq", "password": "Phase17!HQ2026"}).status_code == 200

        created = admin.post("/api/v1/closeout/cases", json={"project_id": project_id, "practical_completion_date": date.today().isoformat(), "defects_liability_end_date": (date.today() + timedelta(days=1)).isoformat(), "final_account_value": "100000", "retention_release_amount": "5000", "practical_completion_document_id": documents["practical"], "client_acceptance_document_id": documents["client"], "final_account_document_id": documents["final"], "retention_release_document_id": documents["retention"]})
        assert created.status_code == 201, created.text
        closeout_id = created.json()["id"]
        detail = admin.get(f"/api/v1/closeout/cases/{closeout_id}").json()
        for item in detail["checklist"]:
            if item["item_type"] in {"as_builts", "operations_manuals", "warranties", "demobilisation"}:
                key = {"as_builts": "asbuilt", "operations_manuals": "manual", "warranties": "warranty", "demobilisation": "demobilisation"}[item["item_type"]]
                completed = admin.put(f"/api/v1/closeout/checklist/{item['id']}", json={"status": "completed", "evidence_document_id": documents[key]})
                assert completed.status_code == 200, completed.text

        defect = admin.post(f"/api/v1/closeout/cases/{closeout_id}/defects", json={"category": "roofing", "title": "Roof flashing leak", "description": "Water penetration recorded after completion inspection.", "priority": "high", "raised_date": date.today().isoformat(), "due_date": date.today().isoformat(), "evidence_document_id": documents["defect"]})
        assert defect.status_code == 201, defect.text
        assert admin.post(f"/api/v1/closeout/cases/{closeout_id}/submit").status_code == 409
        closed_defect = admin.put(f"/api/v1/closeout/defects/{defect.json()['id']}", json={"status": "closed", "closeout_document_id": documents["defect"]})
        assert closed_defect.status_code == 200, closed_defect.text

        request = admin.post(f"/api/v1/closeout/cases/{closeout_id}/submit")
        assert request.status_code == 200, request.text
        assert branch.post(f"/api/v1/closeout/approvals/{request.json()['id']}/decision", json={"decision": "approve", "comment": "Branch completion evidence verified"}).status_code == 200
        final_approval = hq.post(f"/api/v1/closeout/approvals/{request.json()['id']}/decision", json={"decision": "approve", "comment": "Head office handover approved"})
        assert final_approval.status_code == 200, final_approval.text
        assert admin.post(f"/api/v1/closeout/cases/{closeout_id}/close").status_code == 409

        db = TestingSession()
        try:
            policy = db.scalar(select(CompanySetting).where(CompanySetting.company_id == company_id, CompanySetting.key == "closeout_policy"))
            assert policy is not None
            closeout = db.get(ProjectCloseout, closeout_id)
            closeout.defects_liability_end_date = date.today()
            db.commit()
        finally:
            db.close()
        assert hq.post(f"/api/v1/closeout/cases/{closeout_id}/close").status_code == 409
        detail = hq.get(f"/api/v1/closeout/cases/{closeout_id}").json()
        archive = next(item for item in detail["checklist"] if item["item_type"] == "archive")
        assert hq.put(f"/api/v1/closeout/checklist/{archive['id']}", json={"status": "completed", "evidence_document_id": documents["archive"]}).status_code == 200
        final_close = hq.post(f"/api/v1/closeout/cases/{closeout_id}/close")
        assert final_close.status_code == 200, final_close.text
        assert final_close.json()["status"] == "closed"
    finally:
        admin.close()
        branch.close()
        hq.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
