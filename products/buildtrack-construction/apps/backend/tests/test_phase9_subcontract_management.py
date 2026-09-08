from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class Phase9SubcontractManagementContractTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_migration_is_ordered_and_revision_safe(self) -> None:
        migration = self.read("apps/backend/alembic/versions/0011_phase9_subcontracts.py")
        self.assertIn('revision = "0011_phase9_subcontracts"', migration)
        self.assertIn('down_revision = "0010_phase8_procurement"', migration)
        self.assertLessEqual(len("0011_phase9_subcontracts"), 32)
        for table in (
            "subcontractors", "subcontract_packages", "subcontract_bids",
            "subcontract_contracts", "subcontract_certificates", "subcontract_payments",
        ):
            self.assertIn(f'"{table}"', migration)

    def test_commercial_controls_are_not_bypassable(self) -> None:
        api = self.read("apps/backend/app/api/v1/subcontracts.py")
        safeguards = self.read("apps/backend/app/api/v1/subcontracts_safe.py")
        approvals = self.read("apps/backend/app/api/v1/subcontracts_approval_safe.py")
        for token in (
            "SUBCONTRACT_AWARD", "SUBCONTRACT_CONTRACT", "SUBCONTRACT_VARIATION",
            "SUBCONTRACT_CERTIFICATE", "minimum_bids", "retention_release",
            "payment_total", "approved_snapshot", "subcontract.payment.recorded",
        ):
            self.assertIn(token, api)
        for token in (
            "subcontractor must remain active", "controlled invitation", "Minimum subcontract bid count",
            "award evidence", "controlled contract document", "payment proof",
        ):
            self.assertIn(token, safeguards)
        self.assertIn("submitted subcontract certificate needs controlled measurement evidence", approvals)

    def test_models_router_and_browser_workspaces_are_wired(self) -> None:
        models = self.read("apps/backend/app/models/__init__.py")
        router = self.read("apps/backend/app/api/v1/router.py")
        workspace = self.read("apps/frontend/app/subcontracts/page.tsx")
        control = self.read("apps/frontend/app/subcontracts/control/page.tsx")
        for model in ("Subcontractor", "SubcontractPackage", "SubcontractContract", "SubcontractCertificate"):
            self.assertIn(model, models)
        self.assertIn("subcontract_safe_router", router)
        self.assertIn("subcontract_approval_safe_router", router)
        self.assertIn("Subcontract Management", workspace)
        self.assertIn("award_document_id", workspace)
        self.assertIn("submitCertificate", workspace)
        self.assertIn("Subcontract Control", control)
        self.assertIn("/subcontracts/approvals/", control)


if __name__ == "__main__":
    unittest.main()


def test_subcontract_award_to_certified_payment_flow() -> None:
    """Exercise the controlled Phase 9 commercial chain against an in-memory database."""
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
        assert admin.post("/api/v1/access/bootstrap-admin", json={"username": "phase9admin", "email": "phase9admin@nthane.example", "full_name": "Phase 9 Administrator", "password": password}).status_code == 201
        assert admin.post("/api/v1/projects/bootstrap").status_code == 200
        assert admin.post("/api/v1/subcontracts/bootstrap").status_code == 200

        db = TestingSession()
        try:
            company = db.scalar(select(Company))
            branch_row = db.scalar(select(Branch).where(Branch.company_id == company.id))
            site = Site(company_id=company.id, branch_id=branch_row.id, code="P9SITE", name="Phase 9 Site", site_type="project_site", district="Maseru", is_active=True)
            db.add(site); db.flush()
            centre = CostCentre(company_id=company.id, branch_id=branch_row.id, site_id=site.id, code="P9-CC", name="Phase 9 Cost Centre", cost_centre_type="project", is_active=True)
            db.add(centre); db.flush()
            project = Project(company_id=company.id, branch_id=branch_row.id, primary_site_id=site.id, cost_centre_id=centre.id, project_number="PRJ-P9-001", name="Phase 9 Test Project", client_name="Test Client", contract_start_date=date.today(), contract_completion_date=date.today() + timedelta(days=365), mobilisation_date=date.today(), currency="LSL", contract_amount=Decimal("100000"), baseline_budget=Decimal("80000"), contingency_budget=Decimal("5000"), status="ready", readiness_status="ready", created_by="Phase 9 Administrator")
            db.add(project); db.flush()
            documents: dict[str, int] = {}
            for key in ("award", "contract", "measurement", "payment"):
                document = Document(company_id=company.id, branch_id=branch_row.id, site_id=site.id, document_number="P9-" + key.upper(), title="Phase 9 " + key + " evidence", category="commercial", status="active", confidentiality="internal", created_by="Phase 9 Administrator")
                db.add(document); db.flush(); documents[key] = document.id
            db.commit()
            project_id, branch_id = project.id, branch_row.id
        finally:
            db.close()

        roles = admin.get("/api/v1/access/assignment-catalog").json()["roles"]
        branch_role = next(row for row in roles if row["code"] == "BRANCH_MANAGER")
        hq_role = next(row for row in roles if row["code"] == "HQ_EXECUTIVE")
        assert admin.post("/api/v1/access/users", json={"username": "phase9branch", "email": "phase9branch@nthane.example", "full_name": "Phase 9 Branch Approver", "temporary_password": "Phase9!Branch", "must_change_password": False, "assignments": [{"role_id": branch_role["id"], "branch_id": branch_id, "is_primary": True}]}).status_code == 201
        assert admin.post("/api/v1/access/users", json={"username": "phase9hq", "email": "phase9hq@nthane.example", "full_name": "Phase 9 HQ Approver", "temporary_password": "Phase9!HQ2026", "must_change_password": False, "assignments": [{"role_id": hq_role["id"], "is_primary": True}]}).status_code == 201
        assert branch.post("/api/v1/access/login", json={"username": "phase9branch", "password": "Phase9!Branch"}).status_code == 200
        assert hq.post("/api/v1/access/login", json={"username": "phase9hq", "password": "Phase9!HQ2026"}).status_code == 200

        subcontractor_ids = []
        for index in range(3):
            response = admin.post("/api/v1/subcontracts/subcontractors", json={"legal_name": "Phase 9 Trade " + str(index + 1), "trade_categories": ["civil"], "status": "active"})
            assert response.status_code == 201, response.text
            subcontractor_ids.append(response.json()["id"])
        package = admin.post("/api/v1/subcontracts/packages", json={"branch_id": branch_id, "site_id": None, "project_id": project_id, "package_code": "P9-CIVIL", "title": "Phase 9 Civil Works", "planned_start_date": date.today().isoformat(), "planned_completion_date": (date.today() + timedelta(days=90)).isoformat(), "budget_amount": "30000"})
        assert package.status_code == 201, package.text
        package_id = package.json()["id"]
        line = admin.post(f"/api/v1/subcontracts/packages/{package_id}/lines", json={"description": "Controlled earthworks", "quantity": "10", "unit": "m3", "budget_rate": "1000"})
        assert line.status_code == 201, line.text
        line_id = line.json()["id"]
        for subcontractor_id in subcontractor_ids:
            invite = admin.post(f"/api/v1/subcontracts/packages/{package_id}/invite", json={"subcontractor_id": subcontractor_id, "due_date": (date.today() + timedelta(days=14)).isoformat()})
            assert invite.status_code == 201, invite.text
        bid_ids = []
        for index, subcontractor_id in enumerate(subcontractor_ids):
            bid = admin.post(f"/api/v1/subcontracts/packages/{package_id}/bids", json={"subcontractor_id": subcontractor_id, "bid_reference": "P9-BID-" + str(index + 1), "bid_date": date.today().isoformat(), "valid_until": (date.today() + timedelta(days=30)).isoformat(), "tax_amount": "0", "lines": [{"package_line_id": line_id, "quantity": "10", "unit_rate": str(900 + index * 25)}]})
            assert bid.status_code == 201, bid.text
            bid_ids.append(bid.json()["id"])
            evaluation = admin.post(f"/api/v1/subcontracts/bids/{bid_ids[-1]}/evaluation", json={"technical_score": "80", "commercial_score": "80", "hse_score": "80", "programme_score": "80", "recommendation": "recommended"})
            assert evaluation.status_code == 201, evaluation.text

        award = admin.post(f"/api/v1/subcontracts/packages/{package_id}/award", json={"bid_id": bid_ids[0], "award_document_id": documents["award"]})
        assert award.status_code == 200, award.text
        for client in (branch, hq):
            decision = client.post(f"/api/v1/subcontracts/approvals/{award.json()['id']}/decision", json={"decision": "approve", "comment": "Controlled Phase 9 approval"})
            assert decision.status_code == 200, decision.text

        contract = admin.post("/api/v1/subcontracts/contracts", json={"package_id": package_id, "title": "Phase 9 Civil Subcontract", "start_date": date.today().isoformat(), "completion_date": (date.today() + timedelta(days=90)).isoformat(), "retention_pct": "5", "contract_document_id": documents["contract"]})
        assert contract.status_code == 201, contract.text
        contract_id = contract.json()["id"]
        submitted_contract = admin.post(f"/api/v1/subcontracts/contracts/{contract_id}/submit")
        assert submitted_contract.status_code == 200, submitted_contract.text
        for client in (branch, hq):
            decision = client.post(f"/api/v1/subcontracts/approvals/{submitted_contract.json()['id']}/decision", json={"decision": "approve", "comment": "Controlled Phase 9 approval"})
            assert decision.status_code == 200, decision.text

        certificate = admin.post(f"/api/v1/subcontracts/contracts/{contract_id}/certificates", json={"certificate_type": "interim", "period_start": date.today().isoformat(), "period_end": date.today().isoformat(), "gross_value": "2000", "evidence_document_id": documents["measurement"]})
        assert certificate.status_code == 201, certificate.text
        certificate_id = certificate.json()["id"]
        submitted_certificate = admin.post(f"/api/v1/subcontracts/certificates/{certificate_id}/submit")
        assert submitted_certificate.status_code == 200, submitted_certificate.text
        for client in (branch, hq):
            decision = client.post(f"/api/v1/subcontracts/approvals/{submitted_certificate.json()['id']}/decision", json={"decision": "approve", "comment": "Controlled Phase 9 approval"})
            assert decision.status_code == 200, decision.text
        payment = admin.post(f"/api/v1/subcontracts/certificates/{certificate_id}/payments", json={"payment_reference": "P9-PAY-001", "payment_date": date.today().isoformat(), "amount": "1900", "payment_document_id": documents["payment"]})
        assert payment.status_code == 201, payment.text
        detail = admin.get(f"/api/v1/subcontracts/contracts/{contract_id}")
        assert detail.status_code == 200, detail.text
        assert detail.json()["contract"]["certified_amount"] == "2000.00"
        assert detail.json()["certificates"][0]["status"] == "paid"
    finally:
        admin.close(); branch.close(); hq.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
