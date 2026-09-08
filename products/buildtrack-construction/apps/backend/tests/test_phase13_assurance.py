from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

def test_phase13_contracts_are_wired() -> None:
    migration=(ROOT/"apps/backend/alembic/versions/0014_phase13_assurance.py").read_text(encoding="utf-8")
    api=(ROOT/"apps/backend/app/api/v1/assurance.py").read_text(encoding="utf-8")
    page=(ROOT/"apps/frontend/app/assurance/page.tsx").read_text(encoding="utf-8")
    assert 'down_revision = "0013_phase11_commercial"' in migration
    assert len("0014_phase13_assurance") <= 32
    for value in ("project_document_register", "project_assurance_records", "permit_to_work", "quality_nonconformance", "The record creator cannot complete"):
        assert value in migration or value in api
    assert "Document, HSE &amp; Quality Assurance" in page

def test_assurance_creator_cannot_self_review() -> None:
    from decimal import Decimal
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app import models  # noqa
    from app.db.base import Base
    from app.db.session import get_db
    from app.main import app
    from app.models import Branch, Company, CostCentre, Project, Site
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);Session=sessionmaker(bind=engine)
    def override():
        db=Session()
        try: yield db
        finally: db.close()
    app.dependency_overrides[get_db]=override;client=TestClient(app)
    try:
        assert client.post("/api/v1/foundation/bootstrap",json={"name":"Nthane Brothers","code":"NTHANE","head_office_name":"Head Office","head_office_code":"HO","head_office_district":"Maseru"}).status_code==201
        assert client.post("/api/v1/access/bootstrap-admin",json={"username":"phase13admin","email":"phase13admin@nthane.example","full_name":"Phase 13 Administrator","password":"Nthane!Secure2026X"}).status_code==201
        assert client.post("/api/v1/projects/bootstrap").status_code==200
        assert client.post("/api/v1/assurance/bootstrap").status_code==200
        db=Session();company=db.scalar(select(Company));branch=db.scalar(select(Branch).where(Branch.company_id==company.id));site=Site(company_id=company.id,branch_id=branch.id,code="P13",name="P13 Site",site_type="project_site",district="Maseru",is_active=True);db.add(site);db.flush();centre=CostCentre(company_id=company.id,branch_id=branch.id,site_id=site.id,code="P13CC",name="P13 Centre",cost_centre_type="project",is_active=True);db.add(centre);db.flush();project=Project(company_id=company.id,branch_id=branch.id,primary_site_id=site.id,cost_centre_id=centre.id,project_number="P13-001",name="P13 Project",client_name="Client",contract_start_date=date.today(),contract_completion_date=date.today()+timedelta(days=60),mobilisation_date=date.today(),currency="LSL",contract_amount=Decimal("1"),baseline_budget=Decimal("1"),contingency_budget=Decimal("0"),status="ready",readiness_status="ready",created_by="Phase 13 Administrator");db.add(project);db.commit();pid=project.id;db.close()
        record=client.post("/api/v1/assurance/records",json={"project_id":pid,"record_type":"hse_inspection","title":"Daily HSE inspection","description":"Controlled daily site inspection","record_date":date.today().isoformat()});assert record.status_code==201,record.text
        assert client.post(f"/api/v1/assurance/records/{record.json()['id']}/submit").status_code==200
        review=client.post(f"/api/v1/assurance/records/{record.json()['id']}/review",json={"decision":"close"});assert review.status_code==422
    finally:
        client.close();app.dependency_overrides.clear();Base.metadata.drop_all(engine)
