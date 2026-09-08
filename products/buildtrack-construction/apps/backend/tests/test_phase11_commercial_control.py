from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class Phase11CommercialContractTests(unittest.TestCase):
    def test_migration_routes_models_and_workspace_are_wired(self) -> None:
        migration = (ROOT / "apps/backend/alembic/versions/0013_phase11_commercial.py").read_text(encoding="utf-8")
        api = (ROOT / "apps/backend/app/api/v1/commercial.py").read_text(encoding="utf-8")
        router = (ROOT / "apps/backend/app/api/v1/router.py").read_text(encoding="utf-8")
        page = (ROOT / "apps/frontend/app/commercial/page.tsx").read_text(encoding="utf-8")
        self.assertIn('revision = "0013_phase11_commercial"', migration)
        self.assertIn('down_revision = "0012_algorithmic_assist"', migration)
        self.assertLessEqual(len("0013_phase11_commercial"), 32)
        for table in ("client_contracts", "project_cost_transactions", "client_valuations", "client_invoices", "client_claims", "project_cash_flow_forecasts"):
            self.assertIn(f'"{table}"', migration)
        for endpoint in ("/contracts", "/costs", "/valuations", "/invoices", "/claims", "/cash-flow", "/dashboard/projects"):
            self.assertIn(endpoint, api)
        for safeguard in ("Only an active client contract may be valued", "Valuation exceeds the approved client contract ceiling", "Receipt exceeds the outstanding invoice value", "System-controlled reversal", "Self-approval is disabled"):
            self.assertIn(safeguard, api)
        self.assertIn("commercial_router", router)
        self.assertIn("Cost &amp; Commercial Control", page)


def test_controlled_contract_to_receipt_and_cost_flow() -> None:
    from datetime import date, timedelta
    from decimal import Decimal

    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app import models  # noqa: F401
    from app.db.base import Base
    from app.db.session import get_db
    from app.main import app
    from app.models import Branch, Company, CostCentre, Document, Project, Site

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
        password = "Nthane!Secure2026X"
        assert admin.post("/api/v1/foundation/bootstrap", json={"name": "Nthane Brothers", "code": "NTHANE", "head_office_name": "Head Office", "head_office_code": "HO", "head_office_district": "Maseru"}).status_code == 201
        assert admin.post("/api/v1/access/bootstrap-admin", json={"username": "phase11admin", "email": "phase11admin@nthane.example", "full_name": "Phase 11 Administrator", "password": password}).status_code == 201
        assert admin.post("/api/v1/projects/bootstrap").status_code == 200
        assert admin.post("/api/v1/commercial/bootstrap").status_code == 200

        db = TestingSession()
        try:
            company = db.scalar(select(Company))
            branch_row = db.scalar(select(Branch).where(Branch.company_id == company.id))
            site = Site(company_id=company.id, branch_id=branch_row.id, code="P11SITE", name="Phase 11 Site", site_type="project_site", district="Maseru", is_active=True)
            db.add(site); db.flush()
            centre = CostCentre(company_id=company.id, branch_id=branch_row.id, site_id=site.id, code="P11-CC", name="Phase 11 Cost Centre", cost_centre_type="project", is_active=True)
            db.add(centre); db.flush()
            project = Project(company_id=company.id, branch_id=branch_row.id, primary_site_id=site.id, cost_centre_id=centre.id, project_number="PRJ-P11-001", name="Phase 11 Test Project", client_name="Test Client", contract_start_date=date.today(), contract_completion_date=date.today() + timedelta(days=365), mobilisation_date=date.today(), currency="LSL", contract_amount=Decimal("100000"), baseline_budget=Decimal("80000"), contingency_budget=Decimal("5000"), status="ready", readiness_status="ready", created_by="Phase 11 Administrator")
            db.add(project); db.flush()
            documents: dict[str, int] = {}
            for key in ("contract", "variation", "valuation", "invoice", "receipt", "claim"):
                document = Document(company_id=company.id, branch_id=branch_row.id, site_id=site.id, document_number="P11-" + key.upper(), title="Phase 11 " + key + " evidence", category="commercial", status="active", confidentiality="internal", created_by="Phase 11 Administrator")
                db.add(document); db.flush(); documents[key] = document.id
            db.commit()
            project_id, branch_id = project.id, branch_row.id
        finally:
            db.close()

        roles = admin.get("/api/v1/access/assignment-catalog").json()["roles"]
        branch_role = next(row for row in roles if row["code"] == "BRANCH_MANAGER")
        hq_role = next(row for row in roles if row["code"] == "HQ_EXECUTIVE")
        assert admin.post("/api/v1/access/users", json={"username": "phase11branch", "email": "phase11branch@nthane.example", "full_name": "Phase 11 Branch Approver", "temporary_password": "Phase11!Branch", "must_change_password": False, "assignments": [{"role_id": branch_role["id"], "branch_id": branch_id, "is_primary": True}]}).status_code == 201
        assert admin.post("/api/v1/access/users", json={"username": "phase11hq", "email": "phase11hq@nthane.example", "full_name": "Phase 11 HQ Approver", "temporary_password": "Phase11!HQ2026", "must_change_password": False, "assignments": [{"role_id": hq_role["id"], "is_primary": True}]}).status_code == 201
        assert branch.post("/api/v1/access/login", json={"username": "phase11branch", "password": "Phase11!Branch"}).status_code == 200
        assert hq.post("/api/v1/access/login", json={"username": "phase11hq", "password": "Phase11!HQ2026"}).status_code == 200

        contract = admin.post("/api/v1/commercial/contracts", json={"project_id": project_id, "title": "Client Works Contract", "client_name": "Test Client", "start_date": date.today().isoformat(), "completion_date": (date.today() + timedelta(days=180)).isoformat(), "original_contract_sum": "100000", "retention_pct": "5", "contract_document_id": documents["contract"]})
        assert contract.status_code == 201, contract.text
        contract_id = contract.json()["id"]
        approval = admin.post(f"/api/v1/commercial/contracts/{contract_id}/submit")
        assert approval.status_code == 200, approval.text
        for client in (branch, hq):
            decision = client.post(f"/api/v1/commercial/approvals/{approval.json()['id']}/decision", json={"decision": "approve", "comment": "Controlled commercial approval"})
            assert decision.status_code == 200, decision.text

        valuation = admin.post(f"/api/v1/commercial/contracts/{contract_id}/valuations", json={"period_start": date.today().isoformat(), "period_end": date.today().isoformat(), "gross_value": "20000", "other_deductions": "0", "evidence_document_id": documents["valuation"]})
        assert valuation.status_code == 201, valuation.text
        valuation_id = valuation.json()["id"]
        valuation_approval = admin.post(f"/api/v1/commercial/valuations/{valuation_id}/submit")
        assert valuation_approval.status_code == 200, valuation_approval.text
        for client in (branch, hq):
            assert client.post(f"/api/v1/commercial/approvals/{valuation_approval.json()['id']}/decision", json={"decision": "approve", "comment": "Controlled commercial approval"}).status_code == 200

        invoice = admin.post(f"/api/v1/commercial/valuations/{valuation_id}/invoices", json={"invoice_date": date.today().isoformat(), "due_date": (date.today() + timedelta(days=7)).isoformat(), "invoice_document_id": documents["invoice"]})
        assert invoice.status_code == 201, invoice.text
        invoice_id = invoice.json()["id"]
        invoice_approval = admin.post(f"/api/v1/commercial/invoices/{invoice_id}/submit")
        assert invoice_approval.status_code == 200, invoice_approval.text
        for client in (branch, hq):
            assert client.post(f"/api/v1/commercial/approvals/{invoice_approval.json()['id']}/decision", json={"decision": "approve", "comment": "Controlled commercial approval"}).status_code == 200
        receipt = admin.post(f"/api/v1/commercial/invoices/{invoice_id}/receipts", json={"receipt_reference": "P11-REC-001", "receipt_date": date.today().isoformat(), "amount": "19000", "payment_document_id": documents["receipt"]})
        assert receipt.status_code == 201, receipt.text

        cost = admin.post("/api/v1/commercial/costs", json={"project_id": project_id, "transaction_date": date.today().isoformat(), "cost_type": "materials", "description": "Controlled materials cost", "amount": "12000"})
        assert cost.status_code == 201, cost.text
        reversal = admin.post(f"/api/v1/commercial/costs/{cost.json()['id']}/reverse")
        assert reversal.status_code == 201, reversal.text
        claim = admin.post("/api/v1/commercial/claims", json={"project_id": project_id, "contract_id": contract_id, "claim_type": "extension_of_time", "title": "Weather delay claim", "basis": "Controlled weather records and notices", "claimed_amount": "5000", "document_id": documents["claim"]})
        assert claim.status_code == 201, claim.text
        cashflow = admin.post("/api/v1/commercial/cash-flow", json={"project_id": project_id, "forecast_month": date.today().replace(day=1).isoformat(), "expected_inflow": "20000", "expected_outflow": "10000"})
        assert cashflow.status_code == 201, cashflow.text
        dashboard = admin.get(f"/api/v1/commercial/dashboard/projects/{project_id}")
        assert dashboard.status_code == 200, dashboard.text
        assert dashboard.json()["receipts"] == "19000.00"
        assert dashboard.json()["actual_cost"] == "0.00"
    finally:
        admin.close(); branch.close(); hq.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
