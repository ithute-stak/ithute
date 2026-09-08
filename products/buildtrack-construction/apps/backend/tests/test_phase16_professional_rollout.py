from __future__ import annotations
from datetime import date
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]

def test_phase16_rollout_contract_is_wired() -> None:
    migration=(ROOT/"apps/backend/alembic/versions/0017_phase16_rollout.py").read_text(encoding="utf-8")
    api=(ROOT/"apps/backend/app/api/v1/rollout.py").read_text(encoding="utf-8")
    page=(ROOT/"apps/frontend/app/rollout/page.tsx").read_text(encoding="utf-8")
    assert 'down_revision="0016_phase15_development"' in migration
    assert len("0017_phase16_rollout")<=32
    for token in ("rollout_waves","rollout_control_items","rollout_audit_events"):assert token in migration
    for token in ("Verified backup and restore point","Recovery test evidence","The rollout creator cannot complete","Only independently approved rollout waves can be launched"):assert token in api
    assert "Professional Rollout" in page and "Readiness controls" in page

def test_rollout_requires_controls_and_independent_review() -> None:
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine,select
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app import models  # noqa
    from app.db.base import Base
    from app.db.session import get_db
    from app.main import app
    from app.models import Company,CompanySetting
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);Session=sessionmaker(bind=engine)
    def override():
        db=Session()
        try:yield db
        finally:db.close()
    app.dependency_overrides[get_db]=override;client=TestClient(app)
    try:
        assert client.post("/api/v1/foundation/bootstrap",json={"name":"Nthane Brothers","code":"NTHANE","head_office_name":"Head Office","head_office_code":"HO","head_office_district":"Maseru"}).status_code==201
        assert client.post("/api/v1/access/bootstrap-admin",json={"username":"phase16admin","email":"phase16admin@nthane.example","full_name":"Phase 16 Administrator","password":"Nthane!Secure2026X"}).status_code==201
        assert client.post("/api/v1/rollout/bootstrap").status_code==200
        branch=client.get("/api/v1/rollout/branches").json()[0]
        wave=client.post("/api/v1/rollout/waves",json={"branch_id":branch["id"],"name":"Head Office pilot","planned_go_live_date":date.today().isoformat(),"owner":"Rollout Lead"});assert wave.status_code==201,wave.text
        wid=wave.json()["id"];controls=client.get(f"/api/v1/rollout/waves/{wid}/controls").json();assert len(controls)==7
        assert client.post(f"/api/v1/rollout/controls/{controls[0]['id']}/complete",json={}).status_code==409
        db=Session();company=db.scalar(select(Company));policy=db.scalar(select(CompanySetting).where(CompanySetting.company_id==company.id,CompanySetting.key=="rollout_policy"));policy.value={"require_control_evidence":False,"minimum_required_controls":7};db.commit();db.close()
        for control in controls:assert client.post(f"/api/v1/rollout/controls/{control['id']}/complete",json={"result_notes":"Controlled pre-production check completed"}).status_code==200
        assert client.post(f"/api/v1/rollout/waves/{wid}/submit").json()["status"]=="pending_review"
        assert client.post(f"/api/v1/rollout/waves/{wid}/review",json={"decision":"approve"}).status_code==422
    finally:
        client.close();app.dependency_overrides.clear();Base.metadata.drop_all(engine)
