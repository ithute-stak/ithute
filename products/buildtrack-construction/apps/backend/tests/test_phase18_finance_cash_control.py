from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_phase18_finance_contract_is_wired() -> None:
    migration = (ROOT / "apps/backend/alembic/versions/0019_phase18_finance.py").read_text(encoding="utf-8")
    api = (ROOT / "apps/backend/app/api/v1/finance.py").read_text(encoding="utf-8")
    page = (ROOT / "apps/frontend/app/finance/page.tsx").read_text(encoding="utf-8")
    assert 'down_revision = "0018_phase17_closeout"' in migration
    assert len("0019_phase18_finance") <= 32
    for table in ("financial_periods", "chart_of_accounts", "finance_journals", "finance_journal_lines", "supplier_invoices", "supplier_payments", "finance_audit_events"):
        assert f'"{table}"' in migration
    for safeguard in (
        "Finance journal debit and credit totals must balance exactly before approval",
        "Only independently approved finance journals can be posted",
        "Supplier payment request exceeds the uncommitted approved invoice balance",
        "Controlled payment evidence is required before recording a supplier payment",
        "BuildTrack does not send money or connect to a bank",
    ):
        assert safeguard in api or safeguard in page
    assert "Finance &amp; Cash Control" in page and "Accounts-payable register" in page


def test_finance_journal_and_supplier_payment_control() -> None:
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app import models  # noqa: F401
    from app.db.base import Base
    from app.db.session import get_db
    from app.main import app
    from app.models import Branch, Company, Document, Supplier

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
        assert admin.post("/api/v1/access/bootstrap-admin", json={"username": "phase18admin", "email": "phase18admin@nthane.example", "full_name": "Phase 18 Administrator", "password": "Nthane!Secure2026X"}).status_code == 201
        assert admin.post("/api/v1/finance/bootstrap").status_code == 200
        db = TestingSession()
        try:
            company = db.scalar(select(Company))
            branch_row = db.scalar(select(Branch).where(Branch.company_id == company.id))
            supplier = Supplier(company_id=company.id, supplier_code="SUP-P18", name="Phase 18 Supplier", status="active", categories=[], payment_terms_days=30, created_by="Phase 18 Administrator")
            journal_evidence = Document(company_id=company.id, branch_id=branch_row.id, document_number="P18-JRN", title="Phase 18 journal evidence", category="finance", status="active", confidentiality="internal", created_by="Phase 18 Administrator")
            invoice_evidence = Document(company_id=company.id, branch_id=branch_row.id, document_number="P18-INV", title="Phase 18 supplier invoice evidence", category="finance", status="active", confidentiality="internal", created_by="Phase 18 Administrator")
            payment_evidence = Document(company_id=company.id, branch_id=branch_row.id, document_number="P18-PAY", title="Phase 18 payment evidence", category="finance", status="active", confidentiality="internal", created_by="Phase 18 Administrator")
            db.add_all([supplier, journal_evidence, invoice_evidence, payment_evidence])
            db.commit()
            branch_id, supplier_id, journal_document, invoice_document, payment_document = branch_row.id, supplier.id, journal_evidence.id, invoice_evidence.id, payment_evidence.id
        finally:
            db.close()

        roles = admin.get("/api/v1/access/assignment-catalog").json()["roles"]
        branch_role = next(row for row in roles if row["code"] == "BRANCH_MANAGER")
        hq_role = next(row for row in roles if row["code"] == "HQ_EXECUTIVE")
        assert admin.post("/api/v1/access/users", json={"username": "phase18branch", "email": "phase18branch@nthane.example", "full_name": "Phase 18 Branch Reviewer", "temporary_password": "Phase18!Branch", "must_change_password": False, "assignments": [{"role_id": branch_role["id"], "branch_id": branch_id, "is_primary": True}]}).status_code == 201
        assert admin.post("/api/v1/access/users", json={"username": "phase18hq", "email": "phase18hq@nthane.example", "full_name": "Phase 18 HQ Reviewer", "temporary_password": "Phase18!HQ2026", "must_change_password": False, "assignments": [{"role_id": hq_role["id"], "is_primary": True}]}).status_code == 201
        assert branch.post("/api/v1/access/login", json={"username": "phase18branch", "password": "Phase18!Branch"}).status_code == 200
        assert hq.post("/api/v1/access/login", json={"username": "phase18hq", "password": "Phase18!HQ2026"}).status_code == 200

        period = admin.post("/api/v1/finance/periods", json={"period_code": "P18-TEST", "name": "Phase 18 Test Period", "start_date": (date.today() - timedelta(days=1)).isoformat(), "end_date": (date.today() + timedelta(days=30)).isoformat()})
        assert period.status_code == 201, period.text
        accounts = admin.get("/api/v1/finance/accounts").json()
        cash = next(row for row in accounts if row["account_code"] == "1000")
        payable = next(row for row in accounts if row["account_code"] == "2000")
        journal = admin.post("/api/v1/finance/journals", json={"branch_id": branch_id, "period_id": period.json()["id"], "journal_date": date.today().isoformat(), "description": "Supplier accrual", "supporting_document_id": journal_document})
        assert journal.status_code == 201, journal.text
        journal_id = journal.json()["id"]
        assert admin.post(f"/api/v1/finance/journals/{journal_id}/lines", json={"account_id": cash["id"], "debit": "100"}).status_code == 201
        assert admin.post(f"/api/v1/finance/journals/{journal_id}/submit").status_code == 409
        assert admin.post(f"/api/v1/finance/journals/{journal_id}/lines", json={"account_id": payable["id"], "credit": "100"}).status_code == 201
        approval = admin.post(f"/api/v1/finance/journals/{journal_id}/submit")
        assert approval.status_code == 200, approval.text
        assert branch.post(f"/api/v1/finance/approvals/{approval.json()['id']}/decision", json={"decision": "approve", "comment": "Branch balanced journal review"}).status_code == 200
        assert hq.post(f"/api/v1/finance/approvals/{approval.json()['id']}/decision", json={"decision": "approve", "comment": "HQ balanced journal approval"}).status_code == 200
        assert hq.post(f"/api/v1/finance/journals/{journal_id}/post").json()["status"] == "posted"

        invoice = admin.post("/api/v1/finance/supplier-invoices", json={"branch_id": branch_id, "supplier_id": supplier_id, "supplier_invoice_reference": "SUP-INV-18", "invoice_date": date.today().isoformat(), "due_date": (date.today() + timedelta(days=7)).isoformat(), "amount": "125", "invoice_document_id": invoice_document})
        assert invoice.status_code == 201, invoice.text
        invoice_id = invoice.json()["id"]
        invoice_approval = admin.post(f"/api/v1/finance/supplier-invoices/{invoice_id}/submit")
        assert invoice_approval.status_code == 200, invoice_approval.text
        for client in (branch, hq):
            assert client.post(f"/api/v1/finance/approvals/{invoice_approval.json()['id']}/decision", json={"decision": "approve", "comment": "Supplier invoice review"}).status_code == 200
        payment = admin.post(f"/api/v1/finance/supplier-invoices/{invoice_id}/payments", json={"requested_date": date.today().isoformat(), "amount": "125", "payment_reference": "PAY-P18"})
        assert payment.status_code == 201, payment.text
        payment_approval = admin.post(f"/api/v1/finance/supplier-payments/{payment.json()['id']}/submit")
        assert payment_approval.status_code == 200, payment_approval.text
        for client in (branch, hq):
            assert client.post(f"/api/v1/finance/approvals/{payment_approval.json()['id']}/decision", json={"decision": "approve", "comment": "Supplier payment review"}).status_code == 200
        assert hq.post(f"/api/v1/finance/supplier-payments/{payment.json()['id']}/record", json={}).status_code == 409
        recorded = hq.post(f"/api/v1/finance/supplier-payments/{payment.json()['id']}/record", json={"payment_document_id": payment_document})
        assert recorded.status_code == 200, recorded.text
        final_invoice = next(row for row in hq.get("/api/v1/finance/supplier-invoices").json() if row["id"] == invoice_id)
        assert final_invoice["status"] == "paid"
    finally:
        admin.close()
        branch.close()
        hq.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
