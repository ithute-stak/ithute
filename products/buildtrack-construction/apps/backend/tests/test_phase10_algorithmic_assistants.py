from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[3]


class Phase10AlgorithmicAssistantTests(unittest.TestCase):
    def test_source_contract_and_revision_safety(self) -> None:
        migration = (ROOT / "apps/backend/alembic/versions/0012_algorithmic_assist.py").read_text(encoding="utf-8")
        api = (ROOT / "apps/backend/app/api/v1/assistants.py").read_text(encoding="utf-8")
        page = (ROOT / "apps/frontend/app/assistants/page.tsx").read_text(encoding="utf-8")
        router = (ROOT / "apps/backend/app/api/v1/router.py").read_text(encoding="utf-8")
        self.assertIn('revision = "0012_algorithmic_assist"', migration)
        self.assertIn('down_revision = "0011_phase9_subcontracts"', migration)
        self.assertLessEqual(len("0012_algorithmic_assist"), 32)
        for endpoint in ("purchase-order-draft", "supplier-knowledge", "policy-answer", "document-review", "checklist-generate", "deadline-reminders"):
            self.assertIn(endpoint, api)
        self.assertIn("assistant_router", router)
        self.assertIn("Algorithmic Assistants", page)
        self.assertIn("no AI model", page)


def test_deterministic_rules_cover_procurement_and_tender_inputs() -> None:
    from app.api.v1.assistants import category_suggestion, extract_terms, tender_document_review

    category = category_suggestion("Cement, sand and aggregate for drainage works")
    assert category["suggested_category"] == "materials"
    terms = extract_terms("Warranty: 24 months. Delivery within 7 days. Payment terms are 30 days from invoice.")
    assert terms["warranty_days"] == 720
    assert terms["delivery_days_from_document"] == 7
    assert terms["payment_terms_days_from_document"] == 30
    tender = SimpleNamespace(tender_number="TND-TEST", submission_deadline=__import__("datetime").datetime(2026, 12, 15, 10, 0))
    review = tender_document_review("Closing date: 2026-12-15. A bid bond, tax clearance, company registration, method statement and BOQ are mandatory. Submit 3 copies. The contractor must demonstrate previous experience.", tender)
    names = {item["name"] for item in review["required_documents"]}
    assert {"Bid security", "Tax clearance", "Company registration", "Method statement", "Bill of quantities (BOQ)", "Previous experience"}.issubset(names)
    assert review["copies_requested"] == 3
    assert review["bid_security_referenced"] is True


def test_algorithmic_assistant_endpoints_respect_existing_records() -> None:
    from datetime import date, datetime, timedelta, timezone

    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app import models  # noqa: F401
    from app.db.base import Base
    from app.db.session import get_db
    from app.main import app

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
    client = TestClient(app)
    try:
        assert client.post("/api/v1/foundation/bootstrap", json={"name": "Nthane Brothers", "code": "NTHANE", "head_office_name": "Head Office", "head_office_code": "HO", "head_office_district": "Maseru"}).status_code == 201
        assert client.post("/api/v1/access/bootstrap-admin", json={"username": "phase10admin", "email": "phase10admin@nthane.example", "full_name": "Phase 10 Administrator", "password": "Nthane!Secure2026X"}).status_code == 201
        assert client.post("/api/v1/procurement/bootstrap").status_code == 200
        assert client.post("/api/v1/tenders/bootstrap").status_code == 200
        branch_id = client.get("/api/v1/procurement/catalog").json()["branches"][0]["id"]
        requisition = client.post("/api/v1/procurement/requisitions", json={"branch_id": branch_id, "title": "Cement for drainage works", "required_by": (date.today() + timedelta(days=10)).isoformat(), "priority": "normal"})
        assert requisition.status_code == 201, requisition.text
        req_id = requisition.json()["id"]
        assert client.post(f"/api/v1/procurement/requisitions/{req_id}/lines", json={"description": "50kg cement", "specification": "42.5 grade bag", "quantity": "20", "unit": "bag", "estimated_unit_cost": "110"}).status_code == 201
        reviewed = client.post(f"/api/v1/assistants/procurement/requisitions/{req_id}/review")
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["result"]["suggested_category"]["suggested_category"] == "materials"

        tender = client.post("/api/v1/tenders", json={"branch_id": branch_id, "title": "Drainage construction works", "client_name": "Test Client", "submission_deadline": (datetime.now(timezone.utc) + timedelta(days=45)).isoformat()})
        assert tender.status_code == 201, tender.text
        tender_id = tender.json()["id"]
        source = {"source_text": "Closing date: 2026-12-15. Tax clearance, company registration, BOQ and bid bond are mandatory. Submit 3 copies. The contractor must show previous experience and a method statement."}
        review = client.post(f"/api/v1/assistants/tenders/{tender_id}/document-review", json=source)
        assert review.status_code == 200, review.text
        generated = client.post(f"/api/v1/assistants/tenders/{tender_id}/checklist-generate", json=source)
        assert generated.status_code == 200, generated.text
        answer = client.get(f"/api/v1/assistants/tenders/{tender_id}/question", params={"question": "Is a bid bond required?"})
        assert answer.status_code == 200 and "bid-security" in answer.json()["answer"].casefold()
        reminders = client.get(f"/api/v1/assistants/tenders/{tender_id}/deadline-reminders")
        assert reminders.status_code == 200 and [item["days_remaining"] for item in reminders.json()["reminders"]] == [30, 14, 7, 1]
    finally:
        client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
