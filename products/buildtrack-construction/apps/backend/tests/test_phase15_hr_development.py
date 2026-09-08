from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

def test_hr_development_contract_is_wired() -> None:
    migration=(ROOT/"apps/backend/alembic/versions/0016_phase15_development.py").read_text(encoding="utf-8")
    api=(ROOT/"apps/backend/app/api/v1/development.py").read_text(encoding="utf-8")
    page=(ROOT/"apps/frontend/app/development/page.tsx").read_text(encoding="utf-8")
    assert 'down_revision="0015_phase14_mobile"' in migration
    assert len("0016_phase15_development") <= 32
    for token in ("recruitment_candidates", "employee_onboarding_items", "employee_credentials", "employee_training_records", "employee_performance_reviews"):
        assert token in migration
    for token in ("RECRUITMENT_CANDIDATE", "onboarding_overdue", "acknowledge_review", "EmployeeOnboardingItem"):
        assert token in api
    assert "HR Development &amp; Compliance" in page and "Recruitment pipeline" in page

def test_hr_candidate_and_employee_compliance_flow() -> None:
    from decimal import Decimal
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app import models  # noqa
    from app.db.base import Base
    from app.db.session import get_db
    from app.main import app
    from app.models import Branch, Company, Employee
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);Session=sessionmaker(bind=engine)
    def override():
        db=Session()
        try: yield db
        finally: db.close()
    app.dependency_overrides[get_db]=override;client=TestClient(app)
    try:
        assert client.post("/api/v1/foundation/bootstrap",json={"name":"Nthane Brothers","code":"NTHANE","head_office_name":"Head Office","head_office_code":"HO","head_office_district":"Maseru"}).status_code==201
        assert client.post("/api/v1/access/bootstrap-admin",json={"username":"phase15admin","email":"phase15admin@nthane.example","full_name":"Phase 15 Administrator","password":"Nthane!Secure2026X"}).status_code==201
        assert client.post("/api/v1/development/bootstrap").status_code==200
        candidate=client.post("/api/v1/development/candidates",json={"full_name":"Mpho Worker","position":"Site Supervisor","application_date":date.today().isoformat()});assert candidate.status_code==201,candidate.text
        assert candidate.json()["candidate_number"].startswith("CAN")
        assert client.post(f"/api/v1/development/candidates/{candidate.json()['id']}/status",json={"status":"interview"}).json()["status"]=="interview"
        db=Session();company=db.scalar(select(Company));branch=db.scalar(select(Branch).where(Branch.company_id==company.id));employee=Employee(company_id=company.id,employee_number="EMP-P15",branch_id=branch.id,first_name="Mpho",last_name="Worker",job_title="Site Supervisor",hire_date=date.today(),basic_rate=Decimal("0"),created_by="Phase 15 Administrator");db.add(employee);db.commit();eid=employee.id;db.close()
        credential=client.post(f"/api/v1/development/employees/{eid}/credentials",json={"credential_type":"First Aid","expiry_date":(date.today()+timedelta(days=5)).isoformat()});assert credential.status_code==201,credential.text
        item=client.post(f"/api/v1/development/employees/{eid}/onboarding",json={"title":"Complete site induction","due_date":date.today().isoformat()});assert item.status_code==201,item.text
        assert client.post(f"/api/v1/development/employees/{eid}/onboarding/{item.json()['id']}/complete").json()["status"]=="completed"
        review=client.post(f"/api/v1/development/employees/{eid}/performance",json={"review_period_start":date.today().isoformat(),"review_period_end":date.today().isoformat(),"delivery_score":4,"quality_score":4,"safety_score":5,"conduct_score":4,"development_plan":"Complete supervisor refresher"});assert review.status_code==201,review.text
        assert client.post(f"/api/v1/development/employees/{eid}/performance/{review.json()['id']}/acknowledge").json()["status"]=="acknowledged"
        dashboard=client.get("/api/v1/development/dashboard");assert dashboard.status_code==200 and dashboard.json()["credentials_expiring_30_days"]==1 and dashboard.json()["onboarding_open"]==0
    finally:
        client.close();app.dependency_overrides.clear();Base.metadata.drop_all(engine)
